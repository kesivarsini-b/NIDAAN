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
                this.onChunk("audio_chunk", this._encodeFloatPCM(buffer));
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

    /* Emotion-curve generator: maps scenario knobs to a distress-themed
       waveform. Replicates the backend calibration verified end-to-end at
       15/15 tier fidelity (f0gain=1.7, amgain=0.7, gap_on=0.92, distress^2):
       a slow 0.85 Hz pitch contour plus FM+AM psychomotor tremor at 6 Hz and
       rapid-cycle silence gaps, producing analyzable pitch variance, AM and
       silence features that the librosa branch can extract. */
    const AM_GAIN = 0.7;
    const F0_GAIN = 1.7;
    const GAP_ON = 0.92;
    const GAP_VALUE = 0.02;
    const DISTRESS_EXP = 2.0;

    function baseEmotionCurve(t, p) {
        const distress = clamp(p.distress ?? 0.5, 0, 1);
        const e = Math.pow(distress, DISTRESS_EXP);
        const tSec = t / SAMPLE_RATE;
        const baseF0 = 110 + e * 35;
        const f0a = (6 + e * 24) * F0_GAIN;
        const contour = f0a * Math.sin(2 * Math.PI * 0.85 * tSec + 0.7);
        const tremorFM = e * 9 * Math.sin(2 * Math.PI * 6.0 * tSec);
        const f0 = Math.max(70.0, baseF0 + contour + tremorFM);
        _sviPhase += 2 * Math.PI * f0 / SAMPLE_RATE;
        const jitter = (_rng01() - 0.5) * 0.05 * (0.3 + e);
        const am = 1.0 + AM_GAIN * e * (0.5 + 0.5 * Math.sin(2 * Math.PI * 6.0 * tSec + 1.2));
        let gate = 1.0;
        if (p.silenceGaps) {
            gate = GAP_VALUE;
            if (Math.sin(2 * Math.PI * 0.32 * tSec) > GAP_ON) gate = 1.0;
        }
        const amp = (0.18 + 0.32 * e) * (0.7 + 0.3 * Math.sin(2 * Math.PI * 0.5 * tSec)) * am;
        return (Math.sin(_sviPhase) * amp + jitter) * gate;
    }

    let _sviPhase = 0.0;
    let _rngState = 0xC0FFEE;
    function _rng01() {
        _rngState = (1664525 * _rngState + 1013904223) >>> 0;
        return _rngState / 4294967296;
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

    /* ---------------------------------------------------------------------
       Embedded 15-scenario registry (fallback).
       Mirrors data/synthetic_scenarios.json so the dashboard is fully
       functional with zero network: hitting "Run Scenario" starts the
       synthesizer immediately (waveform + local SVI + keyword pills +
       PoA dispatch) without any server round-trip or restart.
       --------------------------------------------------------------------- */
    const EMBEDDED_SCENARIOS = [
        {"id": "sc-001", "title": "Complaint about Right to Work Application Delay", "expected_risk": "LOW", "transcript": "Namaste, main bastar se baat kar rahi hoon. Ek mahine pehle maine MNREGA ke andar apna kaam ka application diya tha. Aaj tak koi jawab nahi aaya. Sirf yahi batana tha ki meri status kya hai. Koi problem nahi hai bas thoda jalda karke bata de.", "synth_profile": {"distress": 0.12, "silence_gaps": false}},
        {"id": "sc-002", "title": "Ration Card Correction Query", "expected_risk": "LOW", "transcript": "Bhaiya, mera ration card mein naam ki spelling galat hai. Poddar ki jagah Podder likha hai. Kya correction ka form file kar sakta hoon? Iske liye kya document chahiye. Bas itna hi puchna tha, dhyan rakhna.", "synth_profile": {"distress": 0.08, "silence_gaps": false}},
        {"id": "sc-003", "title": "Inquiry about Pension Eligibility", "expected_risk": "LOW", "transcript": "Hello, main sanjay kabhi batao mujhe old age pension mil sakta hai ya nahi? Meri umar 62 saal hai aur mera naam list mein nahi tha. Bas puch rahi thi, agar koi form hai toh batana. Shukriya.", "synth_profile": {"distress": 0.15, "silence_gaps": false}},
        {"id": "sc-004", "title": "Denied Drinking Water Access at Public Tap", "expected_risk": "MODERATE", "transcript": "Hamare gaon ke naal ke paani ke nalle pe pehle hum dalit log paani bharte the. Ab kuch log rokte hain. Kehte hain tumhara haath naa lage, tum log paani use nahi kar sakte. Main apne bachchon ko bhookha nahi rakh sakti. Please kuch karo.", "synth_profile": {"distress": 0.42, "silence_gaps": false}},
        {"id": "sc-005", "title": "Casteist Slur During Shop Argument", "expected_risk": "MODERATE", "transcript": "Kal main ration ki bhandar pe gaya tha. Malik ne kaha tum chamar ke tike ho, yahan se jaao. Mere bete ke saamne usne mujhe neech bola. Gaali woh din bhar ko sunata hai. Kya main complain kar sakta hoon ya nahi?", "synth_profile": {"distress": 0.5, "silence_gaps": false}},
        {"id": "sc-006", "title": "School Boycott of Dalit Children", "expected_risk": "MODERATE", "transcript": "Mere bachche school se hamesha nikale jaate hain. Teacher kehta hai ki bacchon ke saath mat betho, yeh achhoot hain. Kuch saath ke bachche bhi pichhe baith jaate hain. Ab school ke liye main dar rahi hoon, kya karun?", "synth_profile": {"distress": 0.55, "silence_gaps": true}},
        {"id": "sc-007", "title": "Land Grab by Landlord with Intimidation", "expected_risk": "HIGH", "transcript": "Meri 2 acre jameen malik ne zabardasti barbaad kar di. Jab main gaya toh usne bola tujhe jaan se maar dunga. Use gaon ka saara system baith gaya hai. Police mein report kiya toh bolte hain koi case nahi banega. Ab mujhe kahan jaana hai?", "synth_profile": {"distress": 0.68, "silence_gaps": true}},
        {"id": "sc-008", "title": "Forced Removal from Well (Untouchability)", "expected_risk": "HIGH", "transcript": "Hamare gaon ke bade baage mein jo kuan hai, wahan humse paani nahi bharna dete. Una jisne bola tum log kamina ho, jaao. Kal humne try kiya toh ek aadmi ne hamla kar diya aur bhaaga. Main ab paani ke liye 4 km door jaati hoon. Yehi mera roz hai.", "synth_profile": {"distress": 0.72, "silence_gaps": true}},
        {"id": "sc-009", "title": "Verbal Abuse & Grocery Boycott Retaliation", "expected_risk": "HIGH", "transcript": "Hamari dukaan pe ek bada saab log kabhi se aata hi nahi. Pichhle hafte ek aadmi aaya aur gaali di - chamar ka dukandar. Ab usne bola ki aap logon ko boyatt ho gaya, tumhara khana koi nahi khayega. Mera business band hone lag gaya hai. Kya case ho sakta hai?", "synth_profile": {"distress": 0.6, "silence_gaps": false}},
        {"id": "sc-010", "title": "House Arson After Panchayat Dispute", "expected_risk": "CRITICAL", "transcript": "Pichhli raat kuch log mere ghar mein aag laga kar bhaag gaye. Meri saari patrika jal gayi. Mere beete ko use dhakke maar ke roka gaya. Usse bola jaan se maar denge. Ab main apne bachchon ko leke abhi pada hoon, toh kya karu? Kaun madad karega?", "synth_profile": {"distress": 0.88, "silence_gaps": true}},
        {"id": "sc-011", "title": "Sexual Harassment & Death Threat", "expected_risk": "CRITICAL", "transcript": "Ek aadmi roz mere kaam ke raaste mein aake chhed karta hai. Usne bola ki agar police mein bataya toh teri gharwale ko nahi chhodega. Mera pati darta hai. Usne aaj goli dikha ke dhamkaya. Main ab ghar se nikalne se darti hoon. Bahut dar lag raha hai. Please koi batao.", "synth_profile": {"distress": 0.92, "silence_gaps": true}},
        {"id": "sc-012", "title": "Suicidal Ideation After Witness Attack", "expected_risk": "CRITICAL", "transcript": "Maine ek gaon mein gawahi di thi ki chamar logon ke saath maar pitai hui. Ab woh log mujhe dhamkaate hain, mere ghar ke bahar aate hain. Main tab se so nahi paata. Jeena nahi chahti ab. Koi sunega nahi. Agar kal mere saath kuch ho jaye toh koi dekhega bhi nahi.", "synth_profile": {"distress": 0.95, "silence_gaps": true}},
        {"id": "sc-013", "title": "Village-Wide Social Boycott & Grocery Denial", "expected_risk": "CRITICAL", "transcript": "Hamare dharam ki potti baithe hone ke baad se gaon wale humse baat nahi karte. Koi paani ka galla nahi deta, dookaan band kar diya. Bache bhookhe hain. Kal unhone humare samaj ka jhandaa jalane ka bhi kaha. Yehi na hi hai ke hum mar jayein. Bataiye kahan jaayein.", "synth_profile": {"distress": 0.85, "silence_gaps": true}},
        {"id": "sc-014", "title": "Rape Threat During Land Dispute", "expected_risk": "CRITICAL", "transcript": "Land case mein meri family bahut pareshan hai. Ek thakur log aaj aaya aur bola jo zameen ka case jitaoge toh meri beti ko chhed kar rakh dunga. Mere pati ko ghumte huwe polise walon ne bhi dhakka diya. Dhamki roz milti hai. Hum kaise jeeyein? Kasam se ab mera dam nikla ja raha hai.", "synth_profile": {"distress": 0.9, "silence_gaps": true}},
        {"id": "sc-015", "title": "Massacre-Like Violence After Panchayat", "expected_risk": "CRITICAL", "transcript": "Gaon ki panchayat ke baad ek jhund ne hamare ghar par fire kiya. Meri maati to nahi hua lekin mere bhai ko goli lagi hai. Ab woh log wapas aayenge. Police darwaza khol ke bilkul kaam nahi kiya. Main aur meri family abhi bhi bhaag se nikli hai. Bachche fati hui aankhon se dekhte hain. Jaldi batao kya karun?", "synth_profile": {"distress": 0.97, "silence_gaps": false}}
    ];

    global.NIDAAN_EMBEDDED_SCENARIOS = EMBEDDED_SCENARIOS;
    if (!global.NIDAAN_FALLBACK_SCENARIOS || !global.NIDAAN_FALLBACK_SCENARIOS.length) {
        global.NIDAAN_FALLBACK_SCENARIOS = EMBEDDED_SCENARIOS;
    }
})(window);