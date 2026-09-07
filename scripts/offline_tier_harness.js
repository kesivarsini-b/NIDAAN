#!/usr/bin/env node
/* ============================================================================
   offline_tier_harness.js
   ----------------------------------------------------------------------------
   NIDAAN offline tier-fidelity harness (the "Node harness" referenced in
   DEMO_CHEATSHEET.md).

   Runs the REAL browser offline engine - untouched app.js OfflineSVI IIFE +
   the real call_simulator synth curve - against all 15 embedded scenarios and
   asserts the fused SVI tier matches each scenario's labeled expected risk.

   Usage:
     node scripts/offline_tier_harness.js
   Exit code 0 = 15/15 tier fidelity, 1 = mismatch found.
   ========================================================================== */
"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.join(__dirname, "..");
const read = (p) => fs.readFileSync(path.join(ROOT, p), "utf8");

/* ---- Minimal browser shims used by the shipped code ---- */
const b64ToU8 = (b64) => Buffer.from(b64, "base64");
const u8ToB64 = (u8) => Buffer.from(u8).toString("base64");

const sandbox = {
    window: {},
    atob: (s) => b64ToU8(s).toString("latin1"),
    btoa: (s) => Buffer.from(s, "latin1").toString("base64"),
    Float32Array: Float32Array,
    DataView: DataView,
    Math: Math,
    Date: Date,
    console: console,
};
sandbox.window.atob = sandbox.atob;
sandbox.window.btoa = sandbox.btoa;
sandbox.window.Float32Array = Float32Array;
sandbox.window.DataView = DataView;
sandbox.window.Math = Math;
sandbox.window.Date = Date;
sandbox.global = sandbox.window;
vm.createContext(sandbox);

/* Load shipped frontend modules in load order (mirrors index.html). */
vm.runInContext(read("frontend/js/offline_data.js"), sandbox);
vm.runInContext(read("frontend/js/call_simulator.js"), sandbox);

/* Extract the ACTUAL OfflineSVI engine from app.js and run it. */
const appSrc = read("frontend/js/app.js");
const HEAD = "const OfflineSVI = ";
const start = appSrc.indexOf(HEAD);
const end = appSrc.indexOf("})();", start) + "})();".length;
if (start < 0 || end <= start) throw new Error("OfflineSVI IIFE not found in app.js");
const body = appSrc.slice(start + HEAD.length, end);
vm.runInContext("OfflineSVI = " + body, sandbox);

const OfflineSVI = sandbox.OfflineSVI;
const scenarios = sandbox.window.NIDAAN_FALLBACK_SCENARIOS;
const embedded = sandbox.window.NIDAAN_EMBEDDED_SCENARIOS;
const synth = sandbox.window.NIDAAN_SYNTH;

/* ---- Registry parity: JSON source, embedded copy, and offline_data copy
        must agree field-for-field so the offline and server paths can never
        silently drift on labels, transcripts, or synth profiles. ---- */
const jsonScenarios = JSON.parse(fs.readFileSync(path.join(ROOT, "data/synthetic_scenarios.json"), "utf8")).scenarios;
const canonical = (s) =>
    JSON.stringify({
        id: s.id,
        title: s.title,
        expected_risk: s.expected_risk,
        transcript: s.transcript,
        synth_profile: s.synth_profile
            ? Object.keys(s.synth_profile).sort().reduce((o, k) => ((o[k] = s.synth_profile[k]), o), {})
            : null,
    });
const canonBy = (list) => {
    const m = new Map();
    for (const s of list) m.set(String(s.id), canonical(s));
    return m;
};
const sources = {
    "data/synthetic_scenarios.json": canonBy(jsonScenarios),
    "frontend/js/call_simulator.js (embedded)": canonBy(embedded),
    "frontend/js/offline_data.js": canonBy(scenarios),
};
const ids = sources["data/synthetic_scenarios.json"].keys();
const parityDiffs = [];
for (const id of ids) {
    for (const [name, map] of Object.entries(sources)) {
        const a = sources["data/synthetic_scenarios.json"].get(id);
        const b = map.get(id);
        if (a !== b) parityDiffs.push({ id, source: name });
    }
}
if (parityDiffs.length) {
    console.error("PARITY FAIL: registries drifted for:");
    for (const d of parityDiffs) console.error(`  ${d.id}  vs ${d.source}`);
}
const parityOk = parityDiffs.length === 0;

const SAMPLE_RATE = synth.SAMPLE_RATE;
const CHUNK_SAMPLES = 8000; // 500 ms chunk, same as the browser synthesizer

function encodeFloatChunk(f32) {
    const bytes = new Uint8Array(f32.length * 4);
    const view = new DataView(bytes.buffer);
    for (let i = 0; i < f32.length; i++) view.setFloat32(i * 4, f32[i], true);
    return u8ToB64(bytes);
}

function synthesizeChunk(profile) {
    const buf = new Float32Array(CHUNK_SAMPLES);
    for (let i = 0; i < CHUNK_SAMPLES; i++) {
        buf[i] = synth.emotionCurve(i, profile || {});
    }
    return buf;
}

let failed = 0;
const rows = [];
for (const sc of scenarios) {
    const expected = String(sc.expected_risk).toUpperCase();
    const ts = OfflineSVI.textScore(sc.transcript).ts;

    const profile = Object.assign({}, sc.synth_profile || {});
    const pcm = synthesizeChunk(profile);
    const acoustic = OfflineSVI.analyzeAcoustic(pcm);
    const svi = OfflineSVI.fuse(acoustic.as, ts, acoustic.confidence);
    const tier = OfflineSVI.tier(svi);

    const ok = tier === expected;
    if (!ok) failed++;
    rows.push({
        id: sc.id, expected, tier, svi: svi.toFixed(1),
        as: acoustic.as.toFixed(1), ts: ts.toFixed(1),
        conf: acoustic.confidence.toFixed(2), ok,
    });
}

console.log("id     expected    fused       as      ts    conf   svi    ok");
for (const r of rows) {
    console.log(String(r.id).padEnd(7) + r.expected.padEnd(11) + r.tier.padEnd(11) +
        r.as.padEnd(7) + r.ts.padEnd(6) + r.conf.padEnd(7) + r.svi.padEnd(7) + (r.ok ? "OK" : "FAIL"));
}
const total = rows.length;
console.log(`\nFidelity: ${total - failed}/${total} tier matches`);
console.log(`Registry parity: ${parityOk ? "3/3 sources in sync" : "DRIFTED"}`);
process.exit(failed === 0 && parityOk ? 0 : 1);