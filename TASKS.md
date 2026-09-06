# NIDAAN — Master Task Assignment & Roadmap

**Project:** National Intelligent Distress & Atrocity Assessment Network (Problem Statement ID 26093)
**Line Ministry:** MoSJE — National Helpline Against Atrocities (NHAA 14566)
**Milestone:** Fully functional MVP prototype

---

## Legend

- `[ ]` — Not started
- `[~]` — In progress
- `[x]` — Done

---

## 1. KC — Tech Lead & OpenCode Driver

**Scope:** Environment setup, FastAPI server lifecycle, WebSocket stream routing, multi-file integration, release management.

### Tasks

- [x] Scaffold repository structure (`backend/`, `frontend/`, `data/`, configs).
- [x] Author `requirements.txt` pinning stable versions.
- [x] Author `.env.example` and `config.py` central configuration (weights, thresholds, ports, intervals).
- [x] Implement FastAPI application lifecycle (`backend/app.py`):
  - Startup/shutdown handlers, scenario preloading.
  - CORS + static-frontend mounting.
  - REST endpoints: health, scenarios, analyze-text, analyze-audio, upload-audio, action-plans.
- [x] Verify WebSocket stream routing (`/ws/stream-svi`):
  - Session lifecycle (`StreamConnectionManager`).
  - Inbound audio chunk / text token / scenario / reset / eof frames.
  - Outbound SVI frames on the 1–2 s cadence (> final).
- [x] Integration test: run a 15-scenario sweep and confirm tier agreement.
- [x] Prepare `git` hygiene (`.gitignore`, initial commit, branch policy).
- [x] Wrap MVP: uvicorn launcher, `python backend/app.py` entry point, README execution steps.
- [x] Post-MVP: `tests/` unit suite (engine, analyzers, recommender).
- [x] Release hardening: zero-error acoustic fallbacks (short-chunk/empty/silence), tier-band progress, per-step statute anchors, 55-test suite.
- [x] Deliverables: `scripts/generate_slides.py` (-> `docs/NIDAAN_SIH_Presentation.pptx`), `scripts/run_daily_qa.py` (scheduled 15-scenario sweep -> `reports/`).
- [ ] Post-MVP: operator queueing, TLS termination, authN.

**Definition of done:** `uvicorn backend.app:app --reload` boots; dashboard loads; all REST + WS routes respond; 15 scenarios run end-to-end.

---

## 2. Sanjay — AI/ML & Acoustic Pipeline Lead

**Scope:** `acoustic_analyzer.py` tuning, Librosa/OpenSMILE feature extraction, `svi_engine.py` weight calibration, performance profiling.

### Tasks

- [x] Implement NumPy-first F0 estimation (autocorrelation fallback when Librosa is absent).
- [x] Implement spectral/amplitude features: RMS dynamics, silence ratio (`T_sil/T_total`).
- [x] Implement perturbation metrics: jitter, shimmer, 3–8 Hz tremor envelope.
- [x] Derive `As` acoustic distress score and `C_audio` signal confidence with degradation penalty.
- [x] Calibrate `ACOUSTIC_FEATURES` thresholds against the 15 synthetic scenarios:
  - Validate pitch-std, silence-ratio normalization curves.
  - Confirm LOW scenarios score < 31 and CRITICAL scenarios > 81.
- [x] Implement `svi_engine.py`:
  - Fusion formula `SVI = C·(0.4·As + 0.6·Ts) + (1−C)·Ts`.
  - Rolling multimodal window (`RollingSVIWindow`) for streaming cadence.
  - Risk tiering LOW/MODERATE/HIGH/CRITICAL.
- [x] Evaluate on low-bandwidth degradation: injected silence → `C_audio` drop → text-track fallback.
- [ ] (OpenSMILE) record prosody deltas for validation vs `librosa.pyin`.
- [ ] Post-MVP: streaming noise-PAD filtering, VAD gating, per-operator calibration.

**Definition of done:** every scenario's synthetic audio yields an acoustic score within ±7 pts of the labeled risk band; confidence stays within [0.4, 1.0] for usable audio.

---

## 3. Mithra — Frontend Engineer & UI Tester

**Scope:** `frontend/index.html` layout, real-time SVI gauge in `app.js`, WebRTC mic streaming, waveform canvas, testing low-bandwidth scenarios.

### Tasks

- [x] Build dark-mode control-room layout (`index.html` + `css/style.css`):
  - Top bar (brand + WS status), three-panel grid (simulator / gauge / analysis).
  - SVI gauge SVG (green→red gradient arc, needle, tier badge).
  - Sub-score cards (As, Ts, C_audio), SVI trace chart, action-plan box.
- [x] Implement `app.js`:
  - WebSocket client + auto-reconnect.
  - Gauge/needle/progress updates per `svi_frame`.
  - Waveform rendering (live mic + synthetic), transcript with trigger highlighting.
  - Trigger chips, raw keyword list, statutory action plan renderer.
- [x] Implement `call_simulator.js`:
  - WebRTC `getUserMedia` + `MediaRecorder` chunked streaming.
  - Audio-unavailable fallback → deterministic distress-waveform synthesizer.
- [x] Wire scenario dropdown → WS `scenario` frame + simulator profile.
- [ ] UI edge tests:
  - No-mic-permission path (dropped to synth mode gracefully).
  - Long-session memory: transcript wraps beyond 40 tokens.
  - Low-bandwidth: slow network tab throttle — WebSocket must not stall.
  - Mobile + narrow viewport (grid collapses to single column).
- [ ] Polish: empty-state messages, loading indicators on scenario fetch, favicon.
- [ ] Post-MVP: history/audit drawer, multi-caller wallboard.

**Definition of done:** dashboard runs under Chrome/Firefox on Windows + Android; gauge reacts <500ms after a WS frame; no console errors in normal + degraded runs.

---

## 4. Harshatha — Dataset Architect & Legal/Domain Lead

**Scope:** `data/synthetic_scenarios.json` (15 realistic Hinglish/regional SC/ST atrocity cases), PoA Act section mapping in `poa_recommender.py`, presentation slides.

### Tasks

- [x] Author dataset with metadata block + 15 scenarios:
  - 3 LOW, 3 MODERATE, 3 HIGH, 6 CRITICAL.
  - Realistic Hinglish + regional transliteration (UP, Bihar, Chhattisgarh, Rajasthan, Telangana, Maharashtra, Gujarat, Punjab, AP).
  - Each entry: transcript, expected tier, expected trigger categories, `synth_profile` (distress/silence) knobs for the acoustic simulator.
- [x] Verify lexicon coverage: every scenario's trigger categories are detectable by `text_analyzer.py`.
- [x] Implement `poa_recommender.py` tier→action mapping:
  - LOW: auto-docketing + routine status SMS.
  - MODERATE: welfare-officer priority callback within 24h.
  - HIGH: senior counselor + tele-medical assistance.
  - CRITICAL: queue bypass + District Police PCR + Witness Protection Cell **Sec 15A(1)** + emergency dispatch.
  - Annotate relevant PoA sections per tier (Sec 3(1)(r)/(v)/(w)/(x), Sec 3(2)(v)/(va), Sec 4, Sec 6, Sec 8, Sec 15A, Sec 18A, Sec 21, Sec 22).
- [ ] Legal validation pass: section citations re-checked against the SC/ST (PoA) Act 1989 + 2015 Amendment.
- [x] Data QA sweep: run all 15 scenarios through `analyze-text`; confirm predicted tier matches label.
- [x] Draft presentation slides (problem, architecture, SVI math, demo screenshots, impact metrics) — `docs/SIH_SUBMISSION_PPT.md`, `docs/PRESENTATION_DECK.md`, `DEMO_CHEATSHEET.md`, `docs/DEMO_VIDEO_SCRIPT.md`.
- [ ] Post-MVP: add district-level aggregations + exclusion-heatmap dataset fields.

**Definition of done:** dataset loads cleanly via `/api/v1/scenarios`; each of the 15 records produces a text-analysis tier matching its `expected_risk`; PoA section mapping is domain-validated.

---

## Cross-Function Schedule (prototype)

| Sprint | Focus                                   | Deliverables                                    |
|--------|-----------------------------------------|-------------------------------------------------|
| 1      | Foundation                              | Structure, configs, requirements, README        |
| 2      | Backend core                            | Acoustic + Text + Fusion + Recommender          |
| 3      | Real-time & UI                          | FastAPI WS server, dashboard, simulator         |
| 4      | Integration & QA                        | 15-scenario sweep, degraded-channel testing     |
| 5      | Presentation & handoff                  | Slides, legal validation, demo recordings       |

---

## Definition of Done (MVP)

1. Repository boots with `pip install -r requirements.txt` + `uvicorn backend.app:app --reload`.
2. All REST + WebSocket endpoints functional per §6 of README.
3. Dashboard renders SVI gauge, waveform, transcript, triggers, action plan in real time.
4. All 15 synthetic scenarios stream end-to-end and land in their labeled risk tier.
5. `svi_engine.py` degrades gracefully to text-only when audio confidence → 0.
6. Legal mapping validated by domain lead; README + TASKS.md updated.