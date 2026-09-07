#!/usr/bin/env node
/* ============================================================================
   fused_qa.js
   ----------------------------------------------------------------------------
   NIDAAN live fused-path QA ("windowed live path, 8 s streams", PRESENTATION_DECK
   Slide 6). Streams every embedded scenario through the real server WebSocket
   engine: scenario transcript -> 8 s of synth audio (the exact shipped
   call_simulator.js curve) -> eof -> compares the server's fused risk tier
   against the scenario's labeled expected tier.

   Requires a running server ("python run.py" or uvicorn) and Node >= 21.

   Usage:
     node scripts/fused_qa.js [base_url]

   Exit code 0 = 15/15 fused-tier matches, 1 = mismatch, 2 = server unreachable.
   Report -> reports/fused_qa_YYYY-MM-DD.json
   ========================================================================== */
"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.join(__dirname, "..");
const BASE = String(process.argv[2] || "http://127.0.0.1:8000").replace(/\/+$/, "");
const WS_URL = BASE.replace(/^http/i, "ws") + "/ws/stream-svi";
const SAMPLE_RATE = 16000;
const CHUNK_SAMPLES = 8000; // 500 ms chunks, 16 chunks = 8 s stream
const CHUNKS_PER_STREAM = 16;
const TIER_BANDS = [
    { category: "LOW", high: 30 },
    { category: "MODERATE", high: 60 },
    { category: "HIGH", high: 80 },
    { category: "CRITICAL", high: 100 },
];

function tierFor(score) {
    for (const band of TIER_BANDS) if (score <= band.high) return band.category;
    return "CRITICAL";
}

function encodeFloatChunk(f32) {
    const bytes = new Uint8Array(f32.length * 4);
    const view = new DataView(bytes.buffer);
    for (let i = 0; i < f32.length; i++) view.setFloat32(i * 4, f32[i], true);
    return Buffer.from(bytes).toString("base64");
}

async function main() {
    /* ---- Boot the real shipped synth + scenario registry in a VM. ---- */
    const sandbox = { window: {}, console };
    sandbox.atob = (s) => Buffer.from(s, "base64").toString("latin1");
    sandbox.btoa = (s) => Buffer.from(s, "latin1").toString("base64");
    sandbox.window.atob = sandbox.atob;
    sandbox.window.btoa = sandbox.btoa;
    sandbox.global = sandbox.window;
    vm.createContext(sandbox);
    vm.runInContext(fs.readFileSync(path.join(ROOT, "frontend/js/offline_data.js"), "utf8"), sandbox);
    vm.runInContext(fs.readFileSync(path.join(ROOT, "frontend/js/call_simulator.js"), "utf8"), sandbox);
    const synth = sandbox.window.NIDAAN_SYNTH;
    const profileById = {};
    for (const sc of sandbox.window.NIDAAN_FALLBACK_SCENARIOS) profileById[sc.id] = sc.synth_profile;

    /* ---- Server truth for ids/titles/expected tiers. ---- */
    let scenarios;
    try {
        const res = await fetch(`${BASE}/api/v1/scenarios`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const body = await res.json();
        scenarios = Array.isArray(body) ? body : (body && body.scenarios) || [];
        if (!scenarios.length) throw new Error("no scenarios returned");
    } catch (err) {
        console.error(`[fused-qa] FATAL: stack unreachable at ${BASE}: ${err.message}`);
        process.exit(2);
    }

    function streamScenario(sc) {
        return new Promise((resolve) => {
            const expected = String(sc.expected_risk).toUpperCase();
            const rows = { id: sc.id, title: sc.title, expected };
            let ws;
            const finish = (err) => {
                try { ws && ws.close(); } catch (_) { /* noop */ }
                resolve(rows);
            };
            try {
                ws = new WebSocket(WS_URL);
            } catch (e) {
                rows.error = String(e.message || e);
                rows.match = false;
                return finish();
            }
            const timeout = setTimeout(() => { rows.error = "timeout waiting for final_frame"; rows.match = false; finish(); }, 30000);
            ws.onerror = (e) => { rows.error = String(e.message || "ws error"); rows.match = false; finish(); };
            ws.onmessage = (ev) => {
                let msg;
                try { msg = JSON.parse(String(ev.data)); } catch (_) { return; }
                if (msg.type !== "final_frame" || !msg.data) return;
                clearTimeout(timeout);
                const svi = Number(msg.data.svi_score);
                const conf = msg.data.audio_confidence;
                rows.svi = Number(svi.toFixed(1));
                rows.acoustic = msg.data.acoustic_score != null ? Number(msg.data.acoustic_score.toFixed(1)) : null;
                rows.text = msg.data.text_score != null ? Number(msg.data.text_score.toFixed(1)) : null;
                rows.conf = conf != null ? Number(conf.toFixed(2)) : null;
                rows.got = tierFor(svi);
                rows.match = rows.got === expected;
                finish();
            };
            ws.onopen = () => {
                try {
                    ws.send(JSON.stringify({ type: "scenario", scenario_id: sc.id }));
                    const profile = profileById[sc.id] || {};
                    let sampleIndex = 0;
                    for (let c = 0; c < CHUNKS_PER_STREAM; c++) {
                        const buf = new Float32Array(CHUNK_SAMPLES);
                        for (let i = 0; i < CHUNK_SAMPLES; i++) {
                            buf[i] = synth.emotionCurve(sampleIndex + i, profile);
                        }
                        sampleIndex += CHUNK_SAMPLES;
                        ws.send(JSON.stringify({ type: "audio_chunk", data: encodeFloatChunk(buf) }));
                    }
                    ws.send(JSON.stringify({ type: "eof" }));
                } catch (e) {
                    rows.error = String(e.message || e);
                    rows.match = false;
                    finish();
                }
            };
        });
    }

    const results = [];
    for (const sc of scenarios) results.push(await streamScenario(sc));

    let failed = 0;
    console.log("id      expected    fused       svi    as     ts     conf   ok");
    for (const r of results) {
        const ok = r.match ? "OK" : "FAIL";
        if (!r.match) failed++;
        console.log(String(r.id).padEnd(7) + r.expected.padEnd(11) + String(r.got || "—").padEnd(11) +
            String(r.svi != null ? r.svi : "—").padEnd(7) +
            String(r.acoustic != null ? r.acoustic : "—").padEnd(6) +
            String(r.text != null ? r.text : "—").padEnd(6) +
            String(r.conf != null ? r.conf : "—").padEnd(6) + ok + (r.error ? "  (" + r.error + ")" : ""));
    }
    const total = results.length;
    console.log(`\nFused QA: ${total - failed}/${total} tier matches`);

    const report = {
        generated_at: new Date().toISOString(),
        base_url: BASE,
        streams_seconds: (CHUNKS_PER_STREAM * CHUNK_SAMPLES) / SAMPLE_RATE,
        chunk_ms: (CHUNK_SAMPLES / SAMPLE_RATE) * 1000,
        results: results,
        summary: { matched: total - failed, total },
    };
    const stamp = new Date().toISOString().slice(0, 10);
    const outDir = path.join(ROOT, "reports");
    const outFile = path.join(outDir, `fused_qa_${stamp}.json`);
    fs.mkdirSync(outDir, { recursive: true });
    fs.writeFileSync(outFile, JSON.stringify(report, null, 2), "utf8");
    console.log(`[fused-qa] report -> ${outFile}`);

    process.exit(failed === 0 ? 0 : 1);
}

main().catch((err) => {
    console.error("[fused-qa] FATAL:", err);
    process.exit(2);
});