/* =========================================================================
   call_simulator.js
   NIDAAN - Audio recorder and preset audio scenario runner.

   Responsibilities:
    - WebRTC microphone capture (MediaRecorder) with PCM-ish chunking
      suitable for streaming over the NIDAAN /ws/stream-svi socket.
    - Produces a synthetic "audio scenario": when real audio is not
      available or permission is denied, generates deterministic emotion
      curves (tremor, pitch variance) represented as raw float32 PCM so the
      SVI fusion pipeline still exercises its acoustic branch end-to-end.
   ========================================================================= */
(function (global) {
    "use strict";

    const SAMPLE_RATE = 16000;
    const CHUNK_MS = 500; // matching backend NIDAAN_AUDIO_CHUNK_DURATION_MS

    class CallSimulator {
        constructor(onChunk, onState) {
            this.onChunk = onChunk;
            this.onState = onState;
            this.stream = null;
            this.recorder = null;
            this.recording = false;
            this.synthTimer = null;
            this.synthMode = false;
            this.synthStopToken = 0;
        }

        /* ---------- Real microphone ---------- */
        async startMicrophone() {
            if (this.recording) return;
            try {
                this.stream = await navigator.mediaDevices.getUserMedia({
                    audio: {
                        echoCancellation: true,
                        noiseSuppression: true,
                        sampleRate: SAMPLE_RATE,
                    },
                });
                this.synthMode = false;
                this.synthStopToken++;
                this.recorder = new MediaRecorder(this.stream, {
                    audioBitsPerSecond: 48000,
                });
                this.recorder.ondataavailable = (e) => {
                    if (e.data && e.data.size > 0) {
                        this._streamWav(e.data);
                    }
                };
                this.recorder.start(CHUNK_MS);
                this.recording = true;
                this._setState("recording (live microphone)");
            } catch (err) {
                this._setState("mic unavailable: " + err.message + " -> fallback synthesizer");
                this.startSynthesizer();
            }
        }

        stopMicrophone() {
            this.recording = false;
            if (this.recorder && this.recorder.state !== "inactive") {
                this.recorder.stop();
            }
            if (this.stream) {
                this.stream.getTracks().forEach((t) => t.stop());
                this.stream = null;
            }
            this.recorder = null;
        }

        /* ---------- Synthetic fallback / scenario runner ---------- */
        startSynthesizer(profile) {
            this.stopMicrophone();
            this.synthMode = true;
            this.synthStopToken++;
            const token = this.synthStopToken;
            this._setState("running synthetic scenario profile");

            const profileFn = (t) => baseEmotionCurve(t, profile || {});
            const chunkSamples = Math.floor((SAMPLE_RATE * CHUNK_MS) / 1000);
            let sampleIndex = 0;

            if (this.synthTimer) clearInterval(this.synthTimer);

            this.synthTimer = setInterval(() => {
                if (token !== this.synthStopToken) {
                    clearInterval(this.synthTimer);
                    return;
                }
                const start = sampleIndex;
                sampleIndex += chunkSamples;
                const buffer = new Float32Array(chunkSamples);
                for (let i = 0; i < chunkSamples; i++) {
                    buffer[i] = profileFn(start + i);
                }
                this.onChunk(this._encodeFloatPCM(buffer));
            }, CHUNK_MS);
        }

        stop() {
            this.synthStopToken++;
            if (this.synthTimer) clearInterval(this.synthTimer);
            this.stopMicrophone();
            this.recording = false;
            this._setState("stopped");
        }

        /* ---------- Encoding helpers ---------- */
        _streamWav(blob) {
            blob.arrayBuffer().then((ab) => {
                const wav = new Uint8Array(ab);
                let b64 = bytesToBase64(wav);
                this.onChunk("audio_chunk", { data: "wav:" + b64 });
            });
        }

        _encodeFloatPCM(f32) {
            const bytes = new Uint8Array(f32.length * 4);
            const view = new DataView(bytes.buffer);
            for (let i = 0; i < f32.length; i++) view.setFloat32(i * 4, f32[i], true);
            return { data: bytesToBase64(bytes) };
        }

        _setState(message) {
            if (this.onState) this.onState(message);
        }
    }

    /* Emotion-curve generator: maps a few scenario knobs to a distress-themed
       waveform. Higher distress = bigger pitch variance + tremor bursts. */
    function baseEmotionCurve(t, p) {
        const distress = clamp(p.distress ?? 0.5, 0, 1);
        const baseF0 = 120 + distress * 45; // Hz
        const vibrato = 5 + distress * 8; // Hz variation
        const tremor = (Math.sin(2 * Math.PI * (4 + distress * 4) * t / SAMPLE_RATE) * 0.25 * distress);
        const jitter = (Math.random() - 0.5) * 0.05 * (0.4 + distress);
        const amp = 0.25 + 0.3 * distress + 0.1 * Math.sin(2 * Math.PI * 0.5 * t / SAMPLE_RATE);
        const silenceGap = p.silenceGaps && Math.sin(2 * Math.PI * 0.4 * t / SAMPLE_RATE) > 0.96 ? 0.02 : 1;
        const phase = 2 * Math.PI * baseF0 * t / SAMPLE_RATE + Math.sin(2 * Math.PI * vibrato * t / SAMPLE_RATE) * tremor;
        return (Math.sin(phase) + jitter) * amp * silenceGap;
    }

    function clamp(v, lo, hi) {
        return Math.max(lo, Math.min(hi, v));
    }

    function bytesToBase64(u8) {
        let bin = "";
        const chunk = 0x8000;
        for (let i = 0; i < u8.length; i += chunk) {
            bin += String.fromCharCode.apply(null, u8.subarray(i, i + chunk));
        }
        return btoa(bin);
    }

    global.CallSimulator = CallSimulator;
})(window);