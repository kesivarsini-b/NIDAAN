#!/usr/bin/env python3
"""
mock_caller.py
==============
Offline NIDAAN demo caller — streams synthetic audio+text to the WS endpoint.

Usage:
    python mock_caller.py                     # run all 15 scenarios
    python mock_caller.py sc-001 sc-010       # run specific scenario ids
"""
import asyncio
import base64
import json
import struct
import sys
from pathlib import Path

import numpy as np

# Project root
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import websockets

SR = 16000
CHUNK_SEC = 2.0
CHUNK_SAMPLES = int(SR * CHUNK_SEC)

# Final generator calibration constants (verified 15/15)
F0_GAIN = 1.7
AM_GAIN = 0.7
GAP_ON = 0.92
GAP_VALUE = 0.02
DISTRESS_EXP = 2.0


def render_chunk(distress: float, gaps: bool, n: int = CHUNK_SAMPLES, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    e = distress ** DISTRESS_EXP
    buf = np.zeros(n, dtype=np.float32)
    phase = 0.0
    base_f0 = 110 + e * 35
    f0a = (6 + e * 24) * F0_GAIN
    for i in range(n):
        t = i / SR
        contour = f0a * np.sin(2 * np.pi * 0.85 * t + 0.7)
        tremor_fm = e * 9 * np.sin(2 * np.pi * 6.0 * t)
        f0 = max(70.0, base_f0 + contour + tremor_fm)
        phase += 2 * np.pi * f0 / SR
        jitter = (rng.random() - 0.5) * 0.05 * (0.3 + e)
        am = 1.0 + AM_GAIN * e * (0.5 + 0.5 * np.sin(2 * np.pi * 6.0 * t + 1.2))
        gate = 1.0
        if gaps:
            gate = GAP_VALUE if np.sin(2 * np.pi * 0.32 * t) > GAP_ON else 1.0
        amp = (0.18 + 0.32 * e) * (0.7 + 0.3 * np.sin(2 * np.pi * 0.5 * t)) * am
        buf[i] = (np.sin(phase) * amp + jitter) * gate
    return buf


def encode_pcm(f32: np.ndarray) -> str:
    raw = f32.astype(np.float32).tobytes()
    return base64.b64encode(raw).decode("ascii")


def load_scenarios() -> dict:
    with open(ROOT / "data" / "synthetic_scenarios.json", encoding="utf-8") as f:
        return {s["id"]: s for s in json.load(f)["scenarios"]}


async def stream_scenario(ws, scenario: dict, chunk_count: int = 8, base_seed: int = 1000):
    sid = scenario["id"]
    prof = scenario["synth_profile"]

    # 1. Load transcript context
    await ws.send(json.dumps({
        "type": "scenario",
        "scenario_id": sid,
    }))

    # 2. Stream audio chunks (2s each)
    for c in range(chunk_count):
        pcm = render_chunk(prof["distress"], prof["silence_gaps"], seed=base_seed + c)
        await ws.send(encode_pcm(pcm))
        await asyncio.sleep(0.05)

    # 3. Signal end-of-stream and drain until the final_frame arrives
    await ws.send(json.dumps({"type": "eof"}))
    final = None
    deadline = asyncio.get_event_loop().time() + 30
    while asyncio.get_event_loop().time() < deadline:
        try:
            data = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
        except asyncio.TimeoutError:
            break
        if data.get("type") == "final_frame":
            final = data
            break
    return final or {}


async def main():
    scenarios = load_scenarios()
    ids = sys.argv[1:] if len(sys.argv) > 1 else sorted(scenarios.keys())

    for idx, sid in enumerate(ids):
        sc = scenarios.get(sid)
        if sc is None:
            print(f"[mock] Unknown scenario {sid} — skipping")
            continue
        async with websockets.connect("ws://127.0.0.1:8000/ws/stream-svi") as ws:
            start = await ws.recv()
            result = await stream_scenario(ws, sc, base_seed=1000 + idx * 20)
        if not result:
            print(f"[mock] {sid:8}  NO final_frame received")
            continue
        final = result.get("data", result)
        cat = final.get("risk_category", "?")
        score = final.get("svi_score", 0)
        expected = sc["expected_risk"]
        mark = "OK" if cat == expected else "MISMATCH"
        print(f"[mock] {sid:8}  fused={cat:9}  svi={score:6.1f}  expected={expected:9}  {mark}")
    print("[mock] Done.")


if __name__ == "__main__":
    asyncio.run(main())
