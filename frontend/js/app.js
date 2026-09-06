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
    };

    let socket = null;
    let connected = false;
    let currentTier = "STANDBY";
    let traceValues = [];
    let audioContext = null;
    let lastWaveSamples = new Uint8Array(0);

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
            .map((s) => "<li><strong>[" + s.owner + "]</strong> " + escapeHtml(s.action) + " <em>(" + s.channel + ", " + s.sla + ")</em></li>")
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
            els.wsDot.classList.add("online");
            els.wsStatus.textContent = "Connected";
            connectBtn(true);
        };

        socket.onclose = () => {
            connected = false;
            els.wsDot.classList.remove("online");
            els.wsStatus.textContent = "Disconnected";
            connectBtn(false);
            setTimeout(connect, 2500);
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

    // ---- Simulator chunk -> socket ----
    function handleSimulatorChunk(kind, payload) {
        lastWaveSamples = waveformFromPayload(payload);
        if (kind === "audio_chunk") {
            send({ type: "audio_chunk", data: payload.data });
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
        els.micToggle.disabled = !on;
        els.runScenarioBtn.disabled = !on;
        if (scenarioSelectHasOptions()) els.scenarioSelect.disabled = !on;
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
        send({ type: "scenario", scenario_id: scenarioId });

        const scenario = scenarioById(scenarioId);
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
        send({ type: "reset" });
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
            const data = await resp.json();
            loadedScenarios = data.scenarios || [];
            const select = els.scenarioSelect;
            select.innerHTML = '<option value="">— Select a scenario —</option>' +
                loadedScenarios.map((s) =>
                    '<option value="' + s.id + '">' +
                    "[" + escapeHtml(s.expected_risk) + "] " + escapeHtml(s.title) +
                    "</option>").join("");
            connectBtn(connected);
        } catch (e) {
            els.scenarioSelect.innerHTML = '<option value="">Scenarios unavailable</option>';
        }
    }

    // ---- Boot ----
    function redrawLoop() {
        renderWaveform();
        renderTrace();
        requestAnimationFrame(redrawLoop);
    }

    loadScenarios();
    connect();
    redrawLoop();

    // Expose for manual debugging.
    window.NIDAAN = { simulator, getTier: () => currentTier };
})();