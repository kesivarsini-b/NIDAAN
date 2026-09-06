# NIDAAN — National Intelligent Distress & Atrocity Assessment Network

**AI-Enabled Real-Time Stress & Trauma Assessment Middleware Engine**
for the **National Helpline Against Atrocities (NHAA – 14566)**
Ministry of Social Justice and Empowerment (MoSJE)

> **Problem Statement ID:** 26093

---

## 1. Overview

NIDAAN is a multimodal middleware engine that continuously fuses **spoken
voice prosody** and **real-time text narrative** into a single **Stress &
Vulnerability Index (SVI)**. The index is used to triage distress calls,
flag trauma indicators, and automatically map callers to the correct
statutory administrative action under the **SC/ST (Prevention of Atrocities)
Act, 1989** (as amended 2015).

The system is built as a production-grade prototype:

- **FastAPI** server exposing REST + WebSocket endpoints.
- **NumPy/Librosa** acoustic feature pipeline (pitch variance, jitter,
  shimmer, silence ratio, tremor 3–8 Hz).
- **Lexicon / intent-based** Indic NLP scoring supporting Hinglish and common
  regional transliterations of SC/ST trauma indicators.
- **Dynamic degradation compensation** so the engine keeps producing robust
  scores on low-bandwidth / low-quality audio channels.
- **Operator dashboard** (dark-mode control room) with live WebRTC
  microphone streaming, scenario runner, SVI gauge, waveform, transcript
  highlighting and statutory action plan.

---

## 2. Problem Statement (ID 26093)

Victims of caste-based atrocities frequently reach helplines in states of
acute distress. Operator assessment is subjective, language-dependent, and
does not scale. Key gaps NIDAAN addresses:

1. **No objective distress scoring** for triage and prioritization.
2. **No real-time multimodal fusion** of *what is said* and *how it is said*.
3. **No automated mapping** from distress tier to statutory processes
   (docketing, welfare callback, witness protection under Sec 15A).
4. **Low-bandwidth resilience** — rural callers often have degraded audio;
   the engine degrades gracefully to text-only analysis.

---

## 3. System Architecture

```
                      ┌────────────────────────────────────────────┐
                      │              NHAA 14566                 │
                      │             Caller / Operator             │
                      └──────────────┬─────────────────────────────┘
                                     │  WebRTC audio stream (Opus / PCM)
                                     ▼
                      ┌────────────────────────────────────────────┐
                      │                INGRESS                      │
                      │    FastAPI WebSocket  /ws/stream-svi        │
                      │    REST  /api/v1/*                          │
                      └──────────────┬─────────────────────────────┘
                                     │
              ┌──────────────────────┴──────────────────────┐
              ▼                                             ▼
   ┌─────────────────────────┐              ┌─────────────────────────┐
   │  ASYNCHRONOUS DUAL-TRACK ENGINE                        │
   │                         │              │                         │
   │  TRACK A · Acoustic     │              │  TRACK B · Text         │
   │  ───────────────────    │              │  ───────────────────    │
   │  acoustic_analyzer.py   │              │  text_analyzer.py       │
   │  • Pitch variance       │              │  • Trauma lexicon       │
   │  • Jitter / Shimmer     │              │  • Weighted categories  │
   │  • Silence ratio        │              │  • Hinglish regex       │
   │  • 3–8 Hz tremor        │              │                         │
   │                         │              │                         │
   │  Output: As ∈ [0,100]   │              │  Output: Ts ∈ [0,100]   │
   │  Confidence: C_audio    │              │                         │
   └─────────────┬───────────┘              └────────────┬───────────┘
                 │                                       │
                 └──────────────┬────────────────────────┘
                                ▼
                 ┌────────────────────────────────────────────┐
                 │       MULTIMODAL FUSION                    │
                 │        svi_engine.py                       │
                 │   SVI = C·(0.4·As + 0.6·Ts) + (1−C)·Ts      │
                 │   Tier: LOW / MODERATE / HIGH / CRITICAL   │
                 └──────────────┬─────────────────────────────┘
                                │  SVI frame (1–2 s cadence)
                                ▼
                 ┌────────────────────────────────────────────┐
                 │        OPERATOR DASHBOARD                  │
                 │  SVI Gauge ▸ Transcript ▸ Triggers ▸       │
                 │  Action Plan (poa_recommender.py)          │
                 │  Sec 3 ◇ Sec 15A(1) ◇ Witness Protection   │
                 └────────────────────────────────────────────┘
```

### Module map

| Layer            | File                              | Responsibility                                  |
|------------------|-----------------------------------|-------------------------------------------------|
| Ingress          | `backend/app.py`                  | FastAPI WebSocket & REST server, stream routing |
| Track A          | `backend/acoustic_analyzer.py`    | Voice prosody → Acoustic Score (As) + Caudio     |
| Track B          | `backend/text_analyzer.py`        | Indic NLP → Semantic Trauma Score (Ts)           |
| Fusion           | `backend/svi_engine.py`           | Multimodal fusion, risk tiering, trigger ranking |
| Statutory Mapper | `backend/poa_recommender.py`      | SVI tier → SC/ST (PoA) Act administrative action|
| Dashboard        | `frontend/`                       | SVI gauge, waveform, transcript, action box     |
| Dataset          | `data/synthetic_scenarios.json`   | 15 labeled Hinglish/regional test scenarios     |

---

## 4. Mathematical Model — The SVI Equation

The Stress & Vulnerability Index is a **confidence-weighted multimodal
fused score** over `[0, 100]`:

```
SVI = C_audio · (0.4 · A_s + 0.6 · T_s) + (1 − C_audio) · T_s
```

| Symbol       | Meaning                                                       | Range    |
|--------------|---------------------------------------------------------------|----------|
| `A_s`        | Acoustic Distress Score (pitch variance, jitter, silence…)   | 0 – 100  |
| `T_s`        | Semantic Trauma Score (weighted keyword/intent severity)      | 0 – 100  |
| `C_audio`    | Signal Confidence (channel reliability, SNR proxy)            | 0 – 1    |
| `0.4` / `0.6`| Modality weights (voice 40%, text 60%) — calibrated per env    | 0 – 1    |

**Why the formula matters — dynamic degradation compensation:**

- When audio quality collapses (`C_audio → 0`), the acoustic term is
  automatically damped and the engine falls back to the **text track**:
  `SVI → T_s`. No single-caller experience loss, no platform outage.
- When audio is clean and informative (`C_audio → 1`),
  `SVI → 0.4·A_s + 0.6·T_s`, giving high-bandwidth callers the full
  multimodal benefit.
- Intermediate confidence values blend both channels smoothly.

### Risk categorization

| Tier        | Score range | Primary action                                             |
|-------------|-------------|------------------------------------------------------------|
| **LOW**     | 0 – 30      | Auto-docketing, routine inquiry status SMS                 |
| **MODERATE**| 31 – 60     | Priority welfare-officer callback within 24h               |
| **HIGH**    | 61 – 80     | Senior counselor + tele-medical assistance                 |
| **CRITICAL**| 81 – 100    | Queue bypass, Police PCR, Witness Protection Cell (Sec 15A)|

### Acoustic distress score (sub-model)

```
A_s = (0.30·ΔPitchᶰ + 0.25·Silenceᶰ + 0.15·Jᶰ + 0.15·Shᶰ + 0.15·Tremorᶰ)·100 − Penalty(1−C_audio)
```

Each channel is normalized against physiologically-motivated thresholds
(e.g. pitch variance 25 Hz, silence ratio 0.45, jitter 2%, shimmer 5%).

### Semantic trauma score (sub-model)

```
T_s = min(100, Σ_category w_c · occurrences_c · intensity_c · 0.5)
```

Severity weights are defined for ten categories including physical threat
(30), sexual violence (50), suicidal ideation (52), caste abuse (24), land
arson (28), and social boycott (22).

---

## 5. Installation & Execution

### Prerequisites

- Python **3.9+**
- Node has **no build step** — the dashboard is static assets served by
  FastAPI.

### 1. Clone & enter

```bash
git clone <repo-url> NIDAAN
cd NIDAAN
```

### 2. Create a virtual environment (recommended)

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # macOS / Linux
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

> On Windows, Librosa needs a working `llvmlite` — installed automatically
> as a dependency. If install fails, use the `[standard]` extras:
> `pip install "librosa[standard]"`.

### 4. Configure environment

```bash
copy .env.example .env        # Windows
cp .env.example .env          # macOS / Linux
```

Edit values as needed (ports, weights, push interval).

### 5. Run the server

Quickest — one-click launcher (installs missing deps, picks a free port, opens the browser):

```bash
python run.py
```

Or directly:

```bash
uvicorn backend.app:app --reload
```

The operator dashboard is then available at:

```
http://127.0.0.1:8000
```

Interactive API docs (Swagger UI):

```
http://127.0.0.1:8000/docs
```

### Quick smoke test

```bash
curl http://127.0.0.1:8000/api/v1/health
curl -X POST http://127.0.0.1:8000/api/v1/analyze-text \
     -H "Content-Type: application/json" \
     -d '{"text":"Mera ghar jala diya aur log mujhe maarne aaye"}'
```

Automated checks:

```bash
pytest tests/test_svi_engine.py            # 36-case backend regression suite
python mock_caller.py                       # streams all 15 scenarios over WebSocket
```

### Docker (containerized deployment)

```bash
docker compose up --build                  # builds + serves on http://127.0.0.1:8000
```

The container runs `uvicorn backend.app:app` on port `8000` with a healthcheck
and a non-root user. See `Dockerfile`.

### Offline Demo Mode

If the API is unreachable (no server, network block, or manual **Demo Mode**
toggle, or `?offline=1` in the URL), the dashboard boots a browser-embedded SVI
engine (`frontend/js/offline_data.js` + `app.js`) that reproduces the same
10-category lexicon, autocorrelation pitch analysis, fusion formula, tier
bands, and statutory action plans — so the demo is fully self-contained. A
"Demo Mode" badge shows the active fallback.

---

## 6. API Reference

### REST

| Method | Endpoint                  | Description                                  |
|--------|---------------------------|----------------------------------------------|
| GET    | `/`                       | Operator dashboard UI                        |
| GET    | `/api/v1/scenarios`       | List the 15 synthetic test scenarios         |
| POST   | `/api/v1/analyze-text`    | Text narrative → Ts, triggers, action plan   |
| POST   | `/api/v1/analyze-audio`   | Base64 float32 PCM → acoustic metrics        |
| POST   | `/api/v1/upload-audio`    | Uploaded audio file → acoustic metrics       |
| GET    | `/api/v1/action-plans`    | Statutory plans for all four tiers           |
| GET    | `/api/v1/health`          | Health, version, library status              |

### WebSocket — `/ws/stream-svi`

Client sends one JSON object per message:

```json
{"type": "audio_chunk", "data": "<base64 float32 PCM or wav:base64>"}
{"type": "text_token",  "text": "mera ghar jala diya"}
{"type": "scenario",    "scenario_id": "sc-012"}
{"type": "reset"}
{"type": "eof"}
```

Server pushes:

```json
{"type": "session_start", "session_id": "...", "interval": 1.5}
{"type": "text_analysis", "partial_transcript": "...", "analysis": {...}}
{"type": "svi_frame", "data": {...}, "action_plan": {...}}
{"type": "final_frame", "data": {...}, "action_plan": {...}}
```

---

## 7. Demo Walkthrough

1. Start the server (see §5).
2. Open `http://127.0.0.1:8000`.
3. Accept microphone permission — the **SVI meter** begins to move as you
   speak, and the waveform animates from your live audio.
4. Alternatively pick a **scenario** from the dropdown (15 test cases) and
   click **Run Scenario** — the simulator streams synthetic stressed-speech
   audio plus the scenario transcript into the fusion engine.
5. Watch the **Transcript panel** highlight trauma triggers, the **Action
   Recommendation box** climb tiers (Low → Critical) and display the mapped
   SC/ST (PoA) Act sections, and the **SVI trace** chart build over time.

---

## 8. Project Structure

```
NIDAAN/
├── README.md
├── TASKS.md                       # Team task breakdown (4 members)
├── requirements.txt
├── .env.example                   # Environment template
├── .dockerignore                  # Lean Docker build context
├── Dockerfile                     # python:3.10-slim production image
├── docker-compose.yml             # Port 8000 mapping for containerized runs
├── config.py                      # Central configuration & thresholds
├── run.py                         # One-click launcher (deps + port + browser)
├── mock_caller.py                 # 15-scenario WebSocket regression caller
├── backend/
│   ├── __init__.py
│   ├── app.py                     # FastAPI WebSockets & REST server
│   ├── svi_engine.py              # Multimodal SVI fusion engine
│   ├── acoustic_analyzer.py       # Voice prosody extraction
│   ├── text_analyzer.py           # Indic NLP / intent risk scoring
│   └── poa_recommender.py         # SC/ST (PoA) Act action mapper
├── frontend/
│   ├── index.html                 # Operator dashboard
│   ├── css/style.css              # Control-room styling
│   └── js/
│       ├── app.js                 # WS client, gauge, waveform UI, offline engine
│       ├── call_simulator.js      # Mic + synthetic scenario runner
│       └── offline_data.js        # Offline Demo Mode scenario registry
├── tests/
│   └── test_svi_engine.py         # 36-case backend regression suite
├── docs/
│   ├── SIH_SUBMISSION_PPT.md      # 6-slide SIH submission template
│   ├── SYSTEM_ARCHITECTURE.md     # ASCII + Mermaid flow, fusion matrix
│   ├── DEMO_VIDEO_SCRIPT.md       # 3-minute video frame-by-frame script
│   └── PRESENTATION_DECK.md       # Extended judging deck + Q&A
├── DEMO_CHEATSHEET.md             # Judge-ready live demo playbook
└── data/
    └── synthetic_scenarios.json   # 15 localized test scripts & labels
```

---

## 9. Security, Legal & Ethical Notes

- **Synthetic data only.** The included scenarios are fictional and exist
  solely to exercise the pipeline. Do not load real PII without a privacy
  impact assessment.
- NIDAAN is a **decision-support middleware**, not a diagnostic tool. SVI
  flags distress signals; a trained human operator always makes the final
  triage decision.
- The PoA action mapper cites sections of the SC/ST (Prevention of
  Atrocities) Act, 1989 for administrative routing and must be validated by
  the Legal & Domain lead before production.
- Audio and transcript payloads should be encrypted in transit (TLS) in
  production; the prototype uses `ws://`/`http://` for local demo.
- CSP / auth headers should be added when deploying beyond `localhost`.

---

## 10. Roadmap

| Phase | Item                                                              |
|-------|-------------------------------------------------------------------|
| 0     | Prototype (this repo): fusion engine, simulator, dashboard        |
| 1     | Second-language ASR integration (ASR ↔ text track)                |
| 2     | On-prem ASR streaming (StreamingAutos), event-driven partials     |
| 3     | Asynchronous dual-track decoupling (audio + text in parallel)     |
| 4     | Operator queueing, tele-medicine dispatch, police PCR integration |
| 5     | Production hardening (authN, TLS, audit trails, DR)               |

---

## 11. License & Attribution

Internal prototype for the MoSJE Smart India Hackathon / NHAA 14566 problem
statement. Attribution: Project NIDAAN Team — KC (Tech Lead), Sanjay
(AI/ML & Acoustic), Mithra (Frontend & UI), Harshatha (Dataset & Legal/Domain).

---

*National Helpline Against Atrocities (NHAA) — 14566 — Mon-Sat, 9:00 AM - 6:00 PM IST.*