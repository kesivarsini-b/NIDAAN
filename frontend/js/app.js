/* =========================================================================
   app.js
   NIDAAN - WebSocket client, live waveform, SVI gauge & dashboard wiring.

   Connects to /ws/stream-svi, renders SVI gauge, waveform, transcript,
   triggers, keywords, action plan, and an SVI time-series trace.
   ========================================================================= */
(function () {
    "use strict";

    const WS_URL = "ws://" + location.host + "/ws/stream-svi";
    const MAX_TRACE_POINTS = 120;

    // ---- DOM references ----
    const $ = (id) => document.getElementById(id);
    const els = {
        wsDot: $("wsDot"),
        wsStatus: $("wsStatus"),
        sessionId: $("sessionId"),
        micToggle: $("micToggle"),
        micState: $("micState"),
        scenarioSelect: $("scenarioSelect"),
        runScenarioBtn: $("runScenarioBtn"),
        waveform: $("waveform"),
        demoText: $("demoText"),
        analyzeTextBtn: $("analyzeTextBtn"),
        resetBtn: $("resetBtn"),
        sviDisplay: $("sviDisplay"),
        tierBadge: $("tierBadge"),
        acousticScore: $("acousticScore"),
        textScore: $("textScore"),
        audioConfidence: $("audioConfidence"),
        sviTrace: $("sviTrace"),
        gaugeProgress: $("gaugeProgress"),
        gaugeNeedle: $("gaugeNeedle"),
        transcriptBox: $("transcriptBox"),
        triggersList: $("triggersList"),
        keywordsList: $("keywordsList"),
        actionPlan: $("actionPlan"),
        offlineToggle: $("offlineToggle"),
        demoModeBadge: $("demoModeBadge"),
        dispatchModal: $("dispatchModal"),
        dispatchAck: $("dispatchAck"),
    };

    let socket = null;
    let connected = false;
    let currentTier = "STANDBY";
    let lastTier = "STANDBY";
    let traceValues = [];
    let audioContext = null;
    let lastWaveSamples = new Uint8Array(0);
    let offlineMode = false;
    let forceOffline = false;
    let offlineTranscript = "";

    const simulator = new window.CallSimulator(
        handleSimulatorChunk,
        (msg) => { els.micState.textContent = msg; }
    );

    // ---- Waveform rendering (synthetic + mic) ----
    function renderWaveform() {
        const canvas = els.waveform;
        const ctx = canvas.getContext("2d");
        const W = canvas.width = canvas.offsetWidth;
        const H = 120;
        const mid = H / 2;

        ctx.fillStyle = "#06090f";
        ctx.fillRect(0, 0, W, H);
        ctx.strokeStyle = "#38bdf8";
        ctx.lineWidth = 1.6;
        ctx.beginPath();

        const data = lastWaveSamples.length > 64 ? lastWaveSamples : new Uint8Array(W).fill(128);
        for (let x = 0; x < W; x++) {
            const idx = Math.floor((x / W) * data.length);
            const v = (data[idx] - 128) / 128;
            const y = mid + v * (H * 0.42);
            if (x === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
        }
        ctx.stroke();

        // Trace tier color tint
        const tint = tierColor(currentTier);
        ctx.strokeStyle = tint;
        ctx.globalAlpha = 0.35;
        ctx.beginPath();
        ctx.moveTo(0, mid);
        ctx.lineTo(W, mid);
        ctx.stroke();
        ctx.globalAlpha = 1;
    }

    // ---- SVI gauge rendering ----
    const ARC_LENGTH = 251.327; // 160deg arc radius 80 => ~251
    function renderSVI(svi) {
        const progress = els.gaugeProgress;
        const offset = ARC_LENGTH - (ARC_LENGTH * svi) / 100;
        progress.style.strokeDashoffset = offset.toFixed(1);

        const needle = els.gaugeNeedle;
        // Map 0..100 -> arc from 180deg (left) to 0deg (right).
        const angle = Math.PI - (Math.PI * svi) / 100;
        const cx = 100, cy = 110, r = 64;
        needle.setAttribute("x2", (cx + r * Math.cos(angle)).toFixed(1));
        needle.setAttribute("y2", (cy + r * Math.sin(angle)).toFixed(1));

        els.sviDisplay.textContent = svi.toFixed(0);
    }

    function setTier(tier) {
        currentTier = (tier || "STANDBY").toUpperCase();
        els.tierBadge.className = "tier-badge tier-" + currentTier;
        els.tierBadge.textContent = currentTier;
    }

    function tierColor(tier) {
        switch (tier) {
            case "LOW": return "#22c55e";
            case "MODERATE": return "#facc15";
            case "HIGH": return "#f97316";
            case "CRITICAL": return "#ef4444";
            default: return "#94a3b8";
        }
    }

    // ---- SVI time-series trace ----
    function renderTrace() {
        const canvas = els.sviTrace;
        const ctx = canvas.getContext("2d");
        const W = canvas.width = canvas.offsetWidth;
        const H = 90;
        ctx.fillStyle = "#06090f";
        ctx.fillRect(0, 0, W, H);

        if (traceValues.length < 2) return;

        const max = 100;
        const step = W / (MAX_TRACE_POINTS - 1);
        ctx.lineWidth = 2;
        ctx.strokeStyle = "#38bdf8";
        ctx.beginPath();
        for (let i = 0; i < traceValues.length; i++) {
            const x = i * step;
            const y = H - (traceValues[i] / max) * (H - 8) - 4;
            if (i === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
        }
        ctx.stroke();
    }

    function pushTrace(value) {
        traceValues.push(value);
        if (traceValues.length > MAX_TRACE_POINTS) traceValues.shift();
        // Horizontal scroll re-render is handled in redraw loop.
    }

    // ---- Transcript & trigger rendering ----
    const TRIGGER_WORDS = [
        "maar", "maarenge", "pitai", "jalam", "agani", "boycott", "bahishkar",
        "chamar", "bhangi", "neech", "suicide", "khudkushi", "rape", "balatkar",
        "toda", "tod diya", "phod", "hamla", "dhakka", "goli", "threat",
    ];

    // =====================================================================
    // Offline Demo Mode — lightweight client-side SVI fallback.
    // Used when the WebSocket / REST server drops mid-presentation so the
    // judging flow never breaks. Mirrors backend features & fusion math.
    // =====================================================================
    const OfflineSVI = (function () {
        const SR = 16000;
        const CLAMP = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
        const r2 = (arr) => { // mean
            if (!arr.length) return 0;
            let s = 0;
            for (let i = 0; i < arr.length; i++) s += arr[i];
            return s / arr.length;
        };
        const stddev = (arr) => {
            if (arr.length < 2) return 0;
            const m = r2(arr);
            let s = 0;
            for (let i = 0; i < arr.length; i++) s += (arr[i] - m) * (arr[i] - m);
            return Math.sqrt(s / arr.length);
        };

        // ---- Mirrors backend/text_analyzer.py lexicon ----
        const SEVERITY = {
            physical_threat: 0.30, land_arson: 0.28, social_boycott: 0.22,
            caste_abuse: 0.24, suicidal_ideation: 0.52, sexual_violence: 0.50,
            property_damage: 0.20, family_threat: 0.16,
            economic_deprivation: 0.15, exclusion: 0.16,
        };
        const LEXICON = {
            physical_threat: ["maar", "maarenge", "maarda", "maarde", "mar diya", "mar dunga", "mar doge", "jaan se maar", "jaan se", "pitai", "dhakka", "dhakke", "goli", "goda", "hamla", "thappad", "fire", "dhamki", "dhamkaya", "dhamkata", "goli dikha", "marne", "maarne"],
            land_arson: ["aag laga", "ag laga", "jalam", "agani", "aag", "jal gayi", "goli laga", "zameen", "khabza", "zabardasti"],
            social_boycott: ["boycott", "boyatt", "bahishkar", "bhand", "samaj se", "koi baat nahi", "baat nahi karte", "gaon wale baat"],
            caste_abuse: ["chamar", "chuda", "bhangi", "achhoot", "achhut", "neech", "jati", "naapak", "ganda", "gaali", "kamina", "nalayak", "caste"],
            suicidal_ideation: ["khudkushi", "suicide", "jeena nahi", "mar jaana", "mar jana", "mar jayega", "mar jaunga", "mar jayungi", "hum mar jayein", "hum mar jaye", "khatam kar", "dam nikla"],
            sexual_violence: ["chhed", "chhedh", "rape", "balatkar", "cheeda", "chhudai", "touch"],
            property_damage: ["tod", "toda", "phod", "barbaad", "jal gayi", "aag", "jhandaa jal", "goli", "fire"],
            family_threat: ["bete ko", "beti ko", "bete", "beti", "gharwale", "ma baap", "bhai ko", "behen", "pati", "biwi", "bacchon", "bachchon", "family"],
            economic_deprivation: ["bhookha", "bhookhe", "naukri se", "kam karna", "paisa", "khaana", "khaane", "rozgar", "dookan band", "business band"],
            exclusion: ["paani se", "paani nahi", "naal", "kuan", "talaab", "well", "school se", "nikale", "nikala", "nikalte", "mat betho", "pichhe betho", "use nahi kar"],
        };
        const INTENSIFIERS = ["bahut", "bht", "kitna", "zyada", "khatarnak", "roz", "din", "kal se", "abhi", "again", "fir", "tumko", "jee na"];
        const patterns = {};
        Object.keys(LEXICON).forEach((cat) => {
            patterns[cat] = LEXICON[cat].map((w) => new RegExp("\\b" + w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "\\b", "i"));
        });

        // ---- Text channel (Ts) — mirrors backend analysis ----
        function textScore(text) {
            const norm = String(text || "").normalize("NFKD")
                .toLowerCase().replace(/[^a-z\s']/g, " ").replace(/\s+/g, " ").trim();
            const counted = {};
            const keywords = {};
            Object.keys(patterns).forEach((cat) => {
                const hits = [];
                patterns[cat].forEach((re, i) => {
                    if (re.test(norm)) hits.push(LEXICON[cat][i]);
                });
                hits.forEach((h) => { keywords[h] = (keywords[h] || 0) + 1; });
                if (hits.length) counted[cat] = hits;
            });
            const hasInt = INTENSIFIERS.some((i) => new RegExp("\\b" + i + "\\b", "i").test(norm));
            const ratios = {};
            Object.keys(counted).forEach((cat) => {
                let ratio = SEVERITY[cat] + 0.06 * (counted[cat].length - 1);
                if (hasInt) ratio += 0.03;
                ratios[cat] = Math.min(0.55, ratio);
            });
            let blended = 100;
            Object.values(ratios).forEach((r) => { blended *= (1 - r); });
            let score = 100 - blended;
            if (ratios.suicidal_ideation) score += 30;
            if (ratios.sexual_violence) score += 20;
            if (/\b(goli|fire)\b/i.test(norm)) score += 20;
            if (ratios.social_boycott && ratios.economic_deprivation) score += 10;
            score = Math.min(100, score);
            const ordered = Object.keys(counted).sort((a, b) =>
                (counted[b].length * SEVERITY[b] + SEVERITY[b]) - (counted[a].length * SEVERITY[a] + SEVERITY[a]));
            return {
                ts: score,
                primaryTriggers: ordered.map((c) => c.replace(/_/g, " ").replace(/\b\w/g, (m) => m.toUpperCase())),
                detectedKeywords: keywords,
            };
        }

        // ---- Base64 decoders ----
        function decodeFloat32(b64) {
            const bin = atob(b64.replace(/^wav:/, ""));
            const u8 = new Uint8Array(bin.length);
            for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
            const out = new Float32Array(u8.length / 4);
            const dv = new DataView(u8.buffer);
            for (let i = 0; i < out.length; i++) out[i] = dv.getFloat32(i * 4, true);
            return out;
        }
        function decodeWav16(b64) {
            const bin = atob(b64.slice(4));
            const u8 = new Uint8Array(bin.length);
            for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
            const offset = (u8.length > 44 && u8[0] === 0x52 && u8[1] === 0x49) ? 44 : 0;
            const count = Math.floor((u8.length - offset) / 2);
            const out = new Float32Array(count);
            const dv = new DataView(u8.buffer);
            for (let i = 0; i < count; i++) out[i] = dv.getInt16(offset + i * 2, true) / 32768;
            return out;
        }
        function decodePayload(payload) {
            if (String(payload && payload.data || "").startsWith("wav:")) return decodeWav16(payload.data);
            try { return decodeFloat32(payload.data); } catch (e) { return new Float32Array(0); }
        }

        // ---- Acoustic channel (As) — mirrors backend/acoustic_analyzer.py ----
        function analyzeAcoustic(f32) {
            const n = f32.length;
            if (n < 1600) return { as: 0, confidence: 0, pitch_std: 0 };
            let peak = 1e-10;
            for (let i = 0; i < n; i++) { const a = Math.abs(f32[i]); if (a > peak) peak = a; }
            const norm = new Float32Array(n);
            for (let i = 0; i < n; i++) norm[i] = f32[i] / peak;

            const FL = 400, HOP = 160;
            const nFrames = Math.max(1, Math.floor((n - FL) / HOP) + 1);
            const frameRms = new Float64Array(nFrames);

            // Pitch via autocorrelation (mirrors numpy fallback path).
            const pit_pitch = [], pFL = 480, pHOP = 160;
            const nPitch = Math.max(0, Math.floor((n - pFL) / pHOP));
            for (let f = 0; f < nPitch; f++) {
                let rmsAcc = 0;
                const r = new Float64Array(pFL);
                for (let lag = 0; lag < pFL; lag++) {
                    let acc = 0;
                    for (let i = 0; i < pFL - lag; i++) acc += norm[f * pHOP + i] * norm[f * pHOP + i + lag];
                    r[lag] = acc;
                }
                for (let i = 0; i < pFL; i++) rmsAcc += norm[f * pHOP + i] * norm[f * pHOP + i];
                const rm = Math.sqrt(rmsAcc / pFL + 1e-10);
                if (rm > 0.005) {
                    const lagMax = Math.max(1, Math.floor(SR / 400)); // 40
                    r.fill(0, 0, lagMax);
                    let bestLag = 0, bestV = -1;
                    for (let lag = lagMax; lag < pFL; lag++) {
                        if (r[lag] > bestV) { bestV = r[lag]; bestLag = lag; }
                    }
                    const f0 = bestLag > 0 ? SR / bestLag : 0;
                    if (f0 >= 70 && f0 <= 400 && bestV > 0.3 * r[0]) pit_pitch.push(f0);
                }
            }

            // Per-frame RMS + jitter/shimmer/tremor.
            for (let f = 0; f < nFrames; f++) {
                let s = 0;
                const base = f * HOP;
                for (let i = 0; i < FL; i++) { const v = norm[base + i]; s += v * v; }
                frameRms[f] = Math.sqrt(s / FL + 1e-10);
            }
            const valid = Array.from(frameRms).filter((v) => v > 1e-6);
            const jitter = valid.length >= 3 ? (() => {
                let d = 0; for (let i = 1; i < valid.length; i++) d += Math.abs(valid[i] - valid[i - 1]);
                return d / valid.length / (r2(valid));
            })() : 0;
            const shimmer = valid.length >= 3 ? stddev(valid) / r2(valid) : 0;
            const tremor = tremorStrength(Array.from(frameRms));

            let sq = 0;
            for (let i = 0; i < norm.length; i++) sq += norm[i] * norm[i];
            const globalRms = Math.sqrt(sq / norm.length);
            const silenceThreshold = Math.max(globalRms * 0.1, 1e-4);
            let silentCount = 0;
            for (let f = 0; f < nFrames; f++) if (frameRms[f] < silenceThreshold) silentCount++;
            const silenceRatio = silentCount / Math.max(1, nFrames);

            const pitchStd = pit_pitch.length ? stddev(pit_pitch) : 0;

            let confidence = 0.5;
            if (globalRms > 0.02) confidence += 0.2; else if (globalRms > 0.005) confidence += 0.1;
            if (silenceRatio < 0.45) confidence += 0.2; else confidence += 0.05;
            if (pit_pitch.length >= 10) confidence += 0.1;
            confidence = CLAMP(confidence, 0, 1);

            const pn = Math.min(1, pitchStd / 25);
            const sn = Math.min(1, silenceRatio / 0.45);
            const jn = Math.min(1, jitter / 0.02);
            const shn = Math.min(1, shimmer / 0.05);
            const tn = Math.min(1, tremor * 4);
            const raw = (0.30 * pn + 0.25 * sn + 0.15 * jn + 0.15 * shn + 0.15 * tn) * 100;
            const as = CLAMP(Math.max(0, raw - (1 - confidence) * 15), 0, 100);
            return { as, confidence, pitch_std: pitchStd };
        }

        function tremorStrength(frameRms) {
            const n = frameRms.length;
            if (n < 16) return 0;
            const mean = r2(frameRms);
            let band = 0, total = 0;
            const end = Math.floor(n / 2);
            for (let k = 0; k <= end; k++) {
                const freq = k / (n * 0.01);
                let re = 0, im = 0;
                for (let i = 0; i < n; i++) {
                    const v = frameRms[i] - mean;
                    const ang = -2 * Math.PI * k * i / n;
                    re += v * Math.cos(ang); im += v * Math.sin(ang);
                }
                const e = re * re + im * im;
                total += e;
                if (freq >= 3 && freq <= 8) band += e;
            }
            return total + 1e-10 ? band / (total + 1e-10) : 0;
        }

        function tier(score) {
            if (score <= 30) return "LOW";
            if (score <= 60) return "MODERATE";
            if (score <= 80) return "HIGH";
            return "CRITICAL";
        }

        function fuse(as, ts, confidence) {
            const ca = confidence;
            const svi = ca * (0.4 * as + 0.6 * ts) + (1 - ca) * ts;
            return CLAMP(svi, 0, 100);
        }

        // ---- Statutory action plans (mirrors poa_recommender.py) ----
        const PLANS = {
            LOW: { risk_tier: "LOW", priority: "ROUTINE", poa_sections: ["Sec 3(2)(i)", "Sec 21(2)"],
                steps: [{ action: "Auto-docket complaint in NHAA case management system", owner: "NHAA Docket Desk", sla: "Immediate", channel: "Internal", statute: "PoA Act 1989 · Sec 3(2)(i)" },
                    { action: "Send routine inquiry status SMS to complainant", owner: "Automated Messaging", sla: "Within 2 hours", channel: "SMS 14566", statute: "PoA Act 1989 · Sec 21(2)" }] },
            MODERATE: { risk_tier: "MODERATE", priority: "PRIORITY", poa_sections: ["Sec 3(1)(r)", "Sec 18A", "Sec 22"],
                steps: [{ action: "Priority callback by District Welfare Officer", owner: "District Welfare Officer", sla: "Within 24 hours", channel: "Phone 14566", statute: "PoA Act 1989 · Sec 3(1)(r)" },
                    { action: "Schedule structured 48-hour safety recheck", owner: "Welfare Office", sla: "48 hours", channel: "Automated reminder", statute: "PoA Act 1989 · Sec 18A" },
                    { action: "Document preliminary FIR guidance", owner: "Legal Aid Cell", sla: "Within 24 hours", channel: "Document", statute: "PoA Act 1989 · Sec 18A / Sec 22" }] },
            HIGH: { risk_tier: "HIGH", priority: "HIGH", poa_sections: ["Sec 3(2)(v)", "Sec 4", "Sec 6", "Sec 8"],
                steps: [{ action: "Route call to senior counselor / trauma specialist", owner: "Senior Counselor", sla: "Immediate", channel: "Live transfer", statute: "PoA Act 1989 · Sec 3(2)(v)" },
                    { action: "Trigger tele-medical assistance referral", owner: "Tele-Medicine Desk", sla: "Within 15 minutes", channel: "Referral + call", statute: "PoA Act 1989 · Sec 4" },
                    { action: "Escalate to DSP-level officer with case summary", owner: "Deputy SP (Crime/SC-ST)", sla: "Within 30 minutes", channel: "High-priority ticket", statute: "PoA Act 1989 · Sec 6 / Sec 3(2)(v)" }] },
            CRITICAL: { risk_tier: "CRITICAL", priority: "EMERGENCY", poa_sections: ["Sec 3(2)(v)", "Sec 15A(1)", "Sec 15A(2)", "Sec 21(2)"],
                steps: [{ action: "Auto-bypass call queue (emergency transfer)", owner: "Switchboard Bot", sla: "Immediate", channel: "Live transfer", statute: "PoA Act 1989 · Sec 3(2)(v)" },
                    { action: "Notify District Police PCR (armed response assessment)", owner: "District Police PCR", sla: "Within 1 minute", channel: "Emergency notification", statute: "PoA Act 1989 · Sec 21(2)" },
                    { action: "Activate Witness Protection Cell under Sec 15A(1)", owner: "Witness Protection Cell", sla: "Within 5 minutes", channel: "Secure channel", statute: "PoA Act 1989 · Sec 15A(1) — Witness Protection" },
                    { action: "Send victim location to nearest police station", owner: "NHAA Operations", sla: "Within 5 minutes", channel: "Encrypted dispatch", statute: "PoA Act 1989 · Sec 15A(1) / Sec 21(2)" },
                    { action: "Request emergency medical / ambulance dispatch", owner: "Tele-Medicine / 108", sla: "Within 10 minutes", channel: "Ambulance dispatch", statute: "PoA Act 1989 · Sec 21(2)" }] },
        };
        function planFor(score) { return PLANS[tier(score)] || PLANS.LOW; }

        return { textScore, analyzeAcoustic, decodePayload, fuse, tier, planFor };
    })();

    function renderLocalFrame(as, confidence) {
        const ts = OfflineSVI.textScore(offlineTranscript).ts;
        const svi = OfflineSVI.fuse(as, ts, confidence);
        const tierName = OfflineSVI.tier(svi);
        renderSVI(svi);
        setTier(tierName);
        els.acousticScore.textContent = as != null ? as.toFixed(0) : "—";
        els.textScore.textContent = ts.toFixed(0);
        els.audioConfidence.textContent = (confidence * 100).toFixed(0) + "%";
        pushTrace(svi);
        renderActionPlan(OfflineSVI.planFor(svi));
        if (tierName === "CRITICAL" && lastTier !== "CRITICAL") showDispatch();
        lastTier = tierName;
    }

    function renderTranscript(text) {
        if (!text) {
            els.transcriptBox.innerHTML = '<p class="placeholder">No live transcript yet.</p>';
            return;
        }
        let escaped = escapeHtml(text);
        for (const word of TRIGGER_WORDS) {
            const re = new RegExp("\\b(" + word + ")\\b", "gi");
            escaped = escaped.replace(re, '<span class="hl-trigger">$1</span>');
        }
        els.transcriptBox.innerHTML = escaped;
        els.transcriptBox.scrollTop = els.transcriptBox.scrollHeight;
    }

    function renderTriggers(primaryTriggers) {
        if (!primaryTriggers || !primaryTriggers.length) {
            els.triggersList.innerHTML = '<span class="chip chip-empty">No triggers yet</span>';
            return;
        }
        els.triggersList.innerHTML = primaryTriggers
            .map((t) => '<span class="chip chip-hot">' + escapeHtml(t) + "</span>")
            .join("");
    }

    function renderKeywords(keywords) {
        const entries = Object.entries(keywords || {});
        if (!entries.length) {
            els.keywordsList.innerHTML = '<span class="muted">--</span>';
            return;
        }
        els.keywordsList.innerHTML = entries
            .sort((a, b) => b[1] - a[1])
            .slice(0, 16)
            .map(([k, n]) => '<span class="kw">' + escapeHtml(k) + " ×" + n + "</span>")
            .join("");
    }

    function renderActionPlan(plan) {
        if (!plan || !plan.steps || !plan.steps.length) return;
        const tier = (plan.risk_tier || "LOW").toUpperCase();
        const steps = plan.steps
            .map((s) => "<li><strong>[" + s.owner + "]</strong> " + escapeHtml(s.action) + " <em>(" + s.channel + ", " + s.sla + ")</em>" +
                (s.statute ? ' <span class="stat">' + escapeHtml(s.statute) + "</span>" : "") + "</li>")
            .join("");
        const sections = (plan.poa_sections || []).join(", ");
        els.actionPlan.className = "action-plan plan-" + tier;
        els.actionPlan.innerHTML =
            '<div class="plan-header">' + escapeHtml(plan.risk_tier) +
            " · " + escapeHtml(plan.priority) + "</div>" +
            '<ul class="plan-steps">' + steps + "</ul>" +
            (sections ? '<div class="poa-sections">PoA Sections: ' + escapeHtml(sections) + "</div>" : "");
    }

    function escapeHtml(s) {
        return String(s).replace(/[&<>"']/g, (c) => ({
            "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
        }[c]));
    }

    // ---- WebSocket handling ----
    function connect() {
        socket = new WebSocket(WS_URL);

        socket.onopen = () => {
            connected = true;
            els.wsDot.classList.remove("offline");
            els.wsDot.classList.add("online");
            els.wsStatus.textContent = "Connected";
            els.demoModeBadge.classList.add("hidden");
            connectBtn(true);
        };

        socket.onclose = () => {
            connected = false;
            els.wsDot.classList.remove("online");
            els.wsStatus.textContent = "Disconnected";
            connectBtn(false);
            if (!offlineMode) {
                enableOffline("Server connection dropped — switching to local SVI engine.");
            }
        };

        socket.onerror = (e) => {
            els.wsStatus.textContent = "Error";
        };

        socket.onmessage = (ev) => {
            let msg;
            try {
                msg = JSON.parse(ev.data);
            } catch (e) {
                return;
            }

            switch (msg.type) {
                case "session_start":
                    els.sessionId.textContent = "#" + msg.session_id.slice(0, 8);
                    break;

                case "svi_frame":
                case "final_frame": {
                    const d = msg.data;
                    renderSVI(d.svi_score);
                    setTier(d.risk_category);
                    els.acousticScore.textContent =
                        d.acoustic_score != null ? d.acoustic_score.toFixed(0) : "—";
                    els.textScore.textContent =
                        d.text_score != null ? d.text_score.toFixed(0) : "—";
                    els.audioConfidence.textContent =
                        d.audio_confidence != null ? (d.audio_confidence * 100).toFixed(0) + "%" : "—";
                    pushTrace(d.svi_score);
                    if (msg.action_plan) renderActionPlan(msg.action_plan);
                    if (d.risk_category === "CRITICAL" && lastTier !== "CRITICAL") showDispatch();
                    lastTier = d.risk_category || "STANDBY";
                    break;
                }

                case "text_analysis":
                    renderTranscript(msg.partial_transcript || "");
                    renderTriggers(msg.analysis.primary_triggers);
                    renderKeywords(msg.analysis.detected_keywords);
                    break;

                case "scenario_loaded":
                    els.transcriptBox.innerHTML =
                        '<p><strong>Scenario loaded:</strong> ' +
                        escapeHtml(msg.scenario.title) +
                        ' <span class="muted">(expected: ' +
                        escapeHtml(msg.expected_tier) + ")</span></p>";
                    renderTriggers(msg.text_analysis.primary_triggers);
                    renderKeywords(msg.text_analysis.detected_keywords);
                    break;

                case "pong":
                case "reset_ack":
                    break;
            }
        };
    }

    function send(obj) {
        if (socket && connected && socket.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify(obj));
        }
    }

    // ---- Simulator chunk -> socket or local SVI ----
    function handleSimulatorChunk(kind, payload) {
        lastWaveSamples = waveformFromPayload(payload);
        if (kind === "audio_chunk") {
            if (offlineMode) {
                const f32 = OfflineSVI.decodePayload(payload);
                if (f32.length) {
                    const a = OfflineSVI.analyzeAcoustic(f32);
                    renderLocalFrame(a.as, a.confidence);
                }
            } else {
                send({ type: "audio_chunk", data: payload.data });
            }
        }
    }

    function waveformFromPayload(payload) {
        // For mic stream we get wav base64; for synth we get float32 base64.
        let u8 = null;
        try {
            let b64 = payload.data;
            if (b64.startsWith("wav:")) b64 = b64.slice(4);
            const bin = atob(b64);
            u8 = new Uint8Array(bin.length);
            for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
        } catch (e) {
            return new Uint8Array(0);
        }
        if (u8.length < 256) return u8;
        if (u8.length >= 44 && u8[0] === 0x52 && u8[1] === 0x49) {
            // WAV: RIFF -> skip header, 16-bit little-endian assumed.
            u8 = u8.subarray(44);
        }
        const count = Math.min(512, Math.floor(u8.length / 2));
        const out = new Uint8Array(count);
        for (let i = 0; i < count; i++) {
            const sample16 = (u8[2 * i] | (u8[2 * i + 1] << 8));
            out[i] = 128 + (sample16 >> 8);
        }
        return out;
    }

    // ---- Buttons ----
    function connectBtn(on) {
        const enabled = on || offlineMode;
        els.micToggle.disabled = !enabled;
        els.runScenarioBtn.disabled = !enabled;
        if (scenarioSelectHasOptions()) els.scenarioSelect.disabled = !enabled;
    }

    function scenarioSelectHasOptions() {
        return els.scenarioSelect.options.length > 1;
    }

    els.micToggle.addEventListener("click", () => {
        if (simulator.recording || simulator.synthMode) {
            simulator.stop();
            els.micToggle.classList.remove("recording");
            els.micToggle.innerHTML = '<span class="btn-icon">&#127908;</span> Connect Microphone';
        } else {
            simulator.startMicrophone();
            els.micToggle.classList.add("recording");
            els.micToggle.innerHTML = '<span class="btn-icon">&#9632;</span> Stop Session';
        }
    });

    els.runScenarioBtn.addEventListener("click", runSelectedScenario);

    async function runSelectedScenario() {
        const scenarioId = els.scenarioSelect.value;
        if (!scenarioId) return;
        const scenario = scenarioById(scenarioId);
        if (!scenario) return;

        if (offlineMode) {
            offlineTranscript = scenario.transcript || "";
            lastTier = "";
            const analysis = OfflineSVI.textScore(offlineTranscript);
            els.transcriptBox.innerHTML =
                '<p><strong>Scenario loaded (offline):</strong> ' +
                escapeHtml(scenario.title) +
                ' <span class="muted">(expected: ' +
                escapeHtml(scenario.expected_risk) + ")</span></p>";
            renderTriggers(analysis.primaryTriggers);
            renderKeywords(analysis.detectedKeywords);
            simulator.startSynthesizer(scenario.synth_profile);
            els.micToggle.classList.add("recording");
            els.micToggle.innerHTML = '<span class="btn-icon">&#9632;</span> Stop Session';
            return;
        }

        send({ type: "scenario", scenario_id: scenarioId });

        if (scenario) {
            simulator.startSynthesizer({
                distress: scenario.synth_profile.distress,
                silenceGaps: scenario.synth_profile.silence_gaps,
            });
            els.micToggle.classList.add("recording");
            els.micToggle.innerHTML = '<span class="btn-icon">&#9632;</span> Stop Session';
        }
    }

    els.analyzeTextBtn.addEventListener("click", async () => {
        const text = els.demoText.value.trim();
        if (!text) return;
        if (offlineMode) {
            offlineTranscript = text;
            const analysis = OfflineSVI.textScore(text);
            renderTranscript(text);
            renderTriggers(analysis.primaryTriggers);
            renderKeywords(analysis.detectedKeywords);
            renderActionPlan(OfflineSVI.planFor(analysis.ts));
            setTier(OfflineSVI.tier(analysis.ts));
            return;
        }
        send({ type: "text_token", text: text });

        const resp = await fetch("/api/v1/analyze-text", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text }),
        });
        if (resp.ok) {
            const data = await resp.json();
            renderTranscript(text);
            renderTriggers(data.analysis.primary_triggers);
            renderKeywords(data.analysis.detected_keywords);
            renderActionPlan(data.action_plan);
            setTier(data.analysis.risk_category);
        }
    });

    els.resetBtn.addEventListener("click", () => {
        if (offlineMode) {
            offlineTranscript = "";
            lastTier = "STANDBY";
        } else {
            send({ type: "reset" });
        }
        simulator.stop();
        els.micToggle.classList.remove("recording");
        els.micToggle.innerHTML = '<span class="btn-icon">&#127908;</span> Connect Microphone';
        traceValues = [];
        els.sviDisplay.textContent = "--";
        setTier("STANDBY");
        els.acousticScore.textContent = "--";
        els.textScore.textContent = "--";
        els.audioConfidence.textContent = "--";
        renderTranscript("");
        renderTriggers([]);
        renderKeywords({});
        els.actionPlan.innerHTML = '<p class="muted">Waiting for first SVI frame...</p>';
    });

    // ---- Scenario dropdown loading ----
    let loadedScenarios = [];

    function scenarioById(id) {
        return loadedScenarios.find((s) => String(s.id) === String(id));
    }

    async function loadScenarios() {
        try {
            const resp = await fetch("/api/v1/scenarios");
            if (!resp.ok) throw new Error("scenario endpoint unavailable");
            const data = await resp.json();
            loadedScenarios = data.scenarios || [];
        } catch (e) {
            // Offline fallback: use embedded registry shipped with the frontend.
            loadedScenarios = (window.NIDAAN_FALLBACK_SCENARIOS || []).slice();
        }
        if (!loadedScenarios.length) {
            els.scenarioSelect.innerHTML = '<option value="">Scenarios unavailable</option>';
            return;
        }
        const select = els.scenarioSelect;
        select.innerHTML = '<option value="">— Select a scenario —</option>' +
            loadedScenarios.map((s) =>
                '<option value="' + s.id + '">' +
                "[" + escapeHtml(s.expected_risk) + "] " + escapeHtml(s.title) +
                "</option>").join("");
        connectBtn(connected);
    }

    // ---- Offline Demo Mode control ----
    function enableOffline(reason) {
        offlineMode = true;
        if (socket) { try { socket.close(); } catch (e) { /* noop */ } }
        els.wsDot.classList.remove("online");
        els.wsDot.classList.add("offline");
        els.wsStatus.textContent = "Demo Mode Active";
        els.demoModeBadge.classList.remove("hidden");
        if (reason) els.micState.textContent = reason;
        connectBtn(connected);
    }

    function disableOffline() {
        offlineMode = false;
        els.wsDot.classList.remove("offline");
        els.wsStatus.textContent = "Connecting...";
        els.demoModeBadge.classList.add("hidden");
        els.micState.textContent = "no permission yet";
        connectBtn(connected);
        connect();
    }

    els.offlineToggle.addEventListener("change", () => {
        forceOffline = els.offlineToggle.checked;
        if (forceOffline) enableOffline("Manual switch — Demo Mode Active.");
        else disableOffline();
    });

    // ---- Police / Legal dispatch popup on CRITICAL ----
    function showDispatch() {
        const modal = els.dispatchModal;
        modal.classList.add("open");
        modal.querySelector(".dispatch-id").textContent =
            "NHAA-" + new Date().getTime().toString(36).toUpperCase();
    }
    els.dispatchAck.addEventListener("click", () => {
        els.dispatchModal.classList.remove("open");
    });

    // ---- Boot ----
    const bootParams = new URLSearchParams(location.search);
    if (bootParams.get("offline") === "1") forceOffline = true;

    function redrawLoop() {
        renderWaveform();
        renderTrace();
        requestAnimationFrame(redrawLoop);
    }

    loadScenarios();
    if (forceOffline) {
        els.offlineToggle.checked = true;
        enableOffline("Demo Mode Active.");
    } else {
        connect();
    }
    redrawLoop();

    // Expose for manual debugging.
    window.NIDAAN = { simulator, getTier: () => currentTier, isOffline: () => offlineMode, OfflineSVI };
})();