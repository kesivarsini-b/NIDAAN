# -*- coding: utf-8 -*-
"""
run_feature_sweep.py
====================
Live end-to-end feature sweep against a RUNNING NIDAAN server.

Exercises every surface of the released build:
  * static dashboard assets            * health / scenarios / action-plans
  * analyze-text (15/15 tier match)    * analyze-audio (valid + corrupt)
  * upload-audio (valid WAV + garbage) * WebSocket stream contract
  * robustness edges (missing fields, empty payloads, unknown scenario)

Usage:
  python scripts/run_feature_sweep.py [base_url]

Exit codes: 0 = all features green, 1 = one or more failures, 2 = server unreachable.
Report -> reports/feature_sweep_YYYY-MM-DD.json
"""
from __future__ import annotations

import asyncio
import base64
import json
import struct
import sys
import wave
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List

import httpx
import numpy as np
import websockets

ROOT = Path(__file__).resolve().parent.parent
BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")
WS_URL = BASE.replace("http", "ws", 1) + "/ws/stream-svi"

SR = 16000
CHUNK_SEC = 0.5
CHUNK_SAMPLES = int(SR * CHUNK_SEC)


def synth_chunk(distress: float, n: int = CHUNK_SAMPLES) -> np.ndarray:
    """Lightweight deterministic acoustic probe (distress-tuned), not the
    audited curve -- the audited curve is exercised by fused_qa.js."""
    e = distress ** 2.0
    buf = np.zeros(n, dtype=np.float32)
    phase = 0.0
    base_f0 = 110 + e * 35
    f0a = (6 + e * 24) * 1.7
    for i in range(n):
        t = i / SR
        f0 = max(70.0, base_f0 + f0a * np.sin(2 * np.pi * 0.85 * t))
        phase += 2 * np.pi * f0 / SR
        jitter = ((i * 2654435761) % 1000 / 1000 - 0.5) * 0.05 * (0.3 + e)
        am = 1.0 + 0.7 * e * (0.5 + 0.5 * np.sin(2 * np.pi * 6.0 * t))
        amp = (0.18 + 0.32 * e) * am
        buf[i] = (np.sin(phase) * amp + jitter)
    return buf


def float32_wav_bytes(pcm: np.ndarray) -> bytes:
    """Build a mono 16 kHz IEEE-float32 WAV in memory."""
    data = pcm.astype("<f4").tobytes()
    fmt = struct.pack("<HHIIHH", 3, 1, SR, SR * 4, 4, 32)  # WAVE_FORMAT_IEEE_FLOAT
    return b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVE" + b"fmt " + \
        struct.pack("<I", 16) + fmt + b"data" + struct.pack("<I", len(data)) + data


async def main() -> int:
    checks: List[Dict[str, Any]] = []

    async def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"feature": name, "ok": bool(ok), "detail": detail})
        print(f"[sweep] {'PASS' if ok else 'FAIL':4}  {name}{'  (' + detail + ')' if detail else ''}")

    async with httpx.AsyncClient(base_url=BASE, timeout=15) as client:
        try:
            r = await client.get("/api/v1/health")
            health = r.json()
        except Exception as exc:  # unreachable server
            print(f"[sweep] FATAL: server unreachable at {BASE}: {exc}")
            return 2

        # ---- Static dashboard assets ----
        for path, marker in [
            ("/", "nidaan"),
            ("/static/css/style.css", "--accent"),
            ("/static/js/app.js", "OfflineSVI"),
            ("/static/js/call_simulator.js", "NIDAAN_SYNTH"),
            ("/static/js/offline_data.js", "sc-015"),
        ]:
            r = await client.get(path)
            await check(f"GET {path} -> 200", r.status_code == 200, f"HTTP {r.status_code}")
            if r.status_code == 200:
                await check(f"GET {path} content marker", marker.lower() in r.text.lower(), marker)

        # ---- Health ----
        await check("GET /api/v1/health status ok", health.get("status") == "ok",
                    str(health.get("status")))
        bands = health.get("thresholds", {})
        await check("health thresholds = 4 bands",
                    {k: list(v) for k, v in (bands or {}).items()} ==
                    {"LOW": [0, 30], "MODERATE": [31, 60], "HIGH": [61, 80], "CRITICAL": [81, 100]},
                    str(bands))

        # ---- Scenarios ----
        r = await client.get("/api/v1/scenarios")
        body = r.json()
        scs = body.get("scenarios", [])
        await check("GET /api/v1/scenarios count=15", r.status_code == 200 and body.get("count") == 15 and len(scs) == 15,
                    f"count={body.get('count')}")
        ids = [s.get("id") for s in scs]
        await check("scenario ids unique", len(set(ids)) == 15)
        dist = {}
        for s in scs:
            dist[str(s.get("expected_risk"))] = dist.get(str(s.get("expected_risk")), 0) + 1
        await check("scenario tier distribution 3/3/3/6",
                    dist.get("LOW", 0) == 3 and dist.get("MODERATE", 0) == 3 and
                    dist.get("HIGH", 0) == 3 and dist.get("CRITICAL", 0) == 6, str(dist))

        # ---- Action plans ----
        r = await client.get("/api/v1/action-plans")
        plans = r.json()
        await check("GET /api/v1/action-plans 4 tiers",
                    r.status_code == 200 and set(plans.keys()) == {"LOW", "MODERATE", "HIGH", "CRITICAL"},
                    str(list(plans.keys())))
        legal = plans.get("CRITICAL", {}).get("legal_framework", "")
        await check("CRITICAL plan anchored to PoA Act 1989 (as amended 2015)",
                    "as amended 2015" in legal, legal)
        crit_steps = plans.get("CRITICAL", {}).get("steps", [])
        await check("every CRITICAL step carries a statute anchor",
                    all(s.get("statute") for s in crit_steps))
        statutes = " | ".join(s.get("statute", "") for s in crit_steps)
        await check("CRITICAL plan includes Witness Protection Sec 15A(1)",
                    any("15A" in (s.get("statute", "") or "") for s in crit_steps), statutes)

        # ---- analyze-text: all 15 scenarios ----
        tier_matches = 0
        for s in scs:
            r = await client.post("/api/v1/analyze-text", json={"text": s["transcript"]})
            if r.status_code != 200:
                await check(f"analyze-text {s['id']} HTTP 200", False, f"HTTP {r.status_code}")
                continue
            obj = r.json()
            got = obj["analysis"]["risk_category"]
            ts = obj["analysis"]["semantic_trauma_score"]
            plan = obj["action_plan"]
            if got == s["expected_risk"]:
                tier_matches += 1
            else:
                await check(f"analyze-text {s['id']}: {s['expected_risk']}",
                            False, f"got {got} (ts={ts})")
        await check("analyze-text 15/15 tier match", tier_matches == 15, f"{tier_matches}/15")

        # analyze-text response completeness on a CRITICAL sample (sc-012)
        r = await client.post("/api/v1/analyze-text", json={"text": scs[11]["transcript"]})
        obj = r.json()
        a = obj["analysis"]; p = obj["action_plan"]
        await check("analyze-text payload has triggers + keywords",
                    a.get("risk_category") == "CRITICAL" and isinstance(a.get("primary_triggers"), list)
                    and isinstance(a.get("detected_keywords"), dict), str(a.get("risk_category")))
        await check("analyze-text CRITICAL plan -> PCR step with statute",
                    any("PCR" in (s.get("action", "") or "") and s.get("statute") for s in p["steps"]))

        # ---- analyze-text robustness ----
        r = await client.post("/api/v1/analyze-text", json={"text": "namaste saja aaja bata de"})
        await check("analyze-text benign text -> LOW (not crash)",
                    r.status_code == 200 and r.json()["analysis"]["risk_category"] == "LOW")
        r = await client.post("/api/v1/analyze-text", json={})
        await check("analyze-text missing field -> 422", r.status_code == 422, f"HTTP {r.status_code}")
        r = await client.post("/api/v1/analyze-text", json={"text": ""})
        await check("analyze-text empty text -> 422", r.status_code == 422, f"HTTP {r.status_code}")

        # ---- analyze-audio ----
        probe = synth_chunk(0.9)
        b64 = base64.b64encode(probe.tobytes()).decode("ascii")
        r = await client.post("/api/v1/analyze-audio", json={"audio_base64": b64})
        acc = r.json().get("acoustic", {})
        as_ = acc.get("acoustic_score", -1); conf = acc.get("signal_confidence", -1)
        await check("analyze-audio valid float32 -> acoustic bounded",
                    r.status_code == 200 and 0 <= as_ <= 100 and 0 <= conf <= 1,
                    f"as={as_} conf={conf}")
        r = await client.post("/api/v1/analyze-audio", json={"audio_base64": ""})
        acc = r.json().get("acoustic", {})
        await check("analyze-audio empty payload -> 200 neutral (zero-error)",
                    r.status_code == 200 and acc.get("acoustic_score", -1) == 0.0,
                    f"HTTP {r.status_code} as={acc.get('acoustic_score')}")
        r = await client.post("/api/v1/analyze-audio", json={"audio_base64": "###not-base64###"})
        await check("analyze-audio garbage base64 -> 400", r.status_code == 400, f"HTTP {r.status_code}")

        # ---- upload-audio ----
        wav = float32_wav_bytes(synth_chunk(0.6))
        files = {"file": ("probe.wav", wav, "audio/wav")}
        r = await client.post("/api/v1/upload-audio", files=files)
        acc = r.json().get("acoustic", {})
        await check("upload-audio valid float32 WAV -> 200 with filename",
                    r.status_code == 200 and r.json().get("filename") == "probe.wav"
                    and "acoustic_score" in acc, f"HTTP {r.status_code}")
        files = {"file": ("junk.bin", b"\x00\x01\x02garbage\xff", "application/octet-stream")}
        r = await client.post("/api/v1/upload-audio", files=files)
        await check("upload-audio garbage bytes -> 400", r.status_code == 400, f"HTTP {r.status_code}")

    # ---- WebSocket stream contract ----
    try:
        async with websockets.connect(WS_URL, close_timeout=5) as ws:
            first = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
            await check("WS session_start", first.get("type") == "session_start",
                        str(first.get("type")))

            await ws.send(json.dumps({"type": "scenario", "scenario_id": "sc-012"}))
            loaded = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
            await check("WS scenario_loaded embeds text_analysis",
                        loaded.get("type") == "scenario_loaded"
                        and loaded.get("expected_tier") == "CRITICAL"
                        and loaded.get("text_analysis", {}).get("risk_category") == "CRITICAL",
                        f"type={loaded.get('type')} tier={loaded.get('expected_tier')}")

            await ws.send(json.dumps({"type": "text_token", "text": "goli dikha ke dhamkaya ab bahut dar"}))
            got = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
            await check("WS text_token -> text_analysis reply", got.get("type") == "text_analysis",
                        str(got.get("type")))

            for _ in range(8):
                await ws.send(base64.b64encode(synth_chunk(0.9).tobytes()).decode("ascii"))
            await ws.send(json.dumps({"type": "reset"}))
            reset_ack = None
            for _ in range(16):
                m = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
                if m.get("type") == "reset_ack":
                    reset_ack = m
                    break
            await check("WS reset -> reset_ack",
                        reset_ack is not None, str(reset_ack and reset_ack.get("type")))

            await ws.send(json.dumps({"type": "scenario", "scenario_id": "sc-014"}))
            await ws.send(json.dumps({"type": "eof"}))
            final = None
            while final is None:
                m = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
                if m.get("type") == "final_frame":
                    final = m
            d = final.get("data", {})
            plan = final.get("action_plan", {})
            await check("WS eof -> final_frame CRITICAL (sc-014)",
                        d.get("risk_category") == "CRITICAL", str(d.get("risk_category")))
            await check("WS final_frame plan statute-anchored",
                        any("15A" in (s.get("statute") or "") for s in plan.get("steps", [])),
                        str(plan.get("risk_tier")))
    except Exception as exc:
        await check("WebSocket stream contract", False, f"{type(exc).__name__}: {exc}")

    failed = [c for c in checks if not c["ok"]]
    print(f"\n[sweep] Feature sweep: {len(checks) - len(failed)}/{len(checks)} green")

    stamp = datetime.now().strftime("%Y-%m-%d")
    report = {
        "generated_at": datetime.now().isoformat(),
        "base_url": BASE,
        "checks": checks,
        "summary": {"green": len(checks) - len(failed), "total": len(checks)},
    }
    out_dir = ROOT / "reports"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / f"feature_sweep_{stamp}.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[sweep] report -> {out}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))