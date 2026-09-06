# NIDAAN — SIH Submission Presentation (6-Slide Template)

> **Programme:** Smart India Hackathon (SIH) 2025/26 — Software Edition
> **Problem Statement ID:** `26093`
> **Department:** Ministry of Social Justice & Empowerment (MoSJE) — National Helpline Against Atrocities (`NHAA — 14566`)
> **Team Name:** `Team NIDAAN`
> **Proposed Solution:** NIDAAN — AI-Enabled Real-Time Stress & Trauma Assessment Middleware for Helpline 14566
>
> This file is the canonical, copy-paste-ready source for the 6-slide submission deck.
> Every slide below maps 1:1 to the official SIH presentation template order.

---

## Slide 1 — Title Slide

| Field | Content |
|---|---|
| **Problem Statement ID** | `26093` |
| **Problem Statement Title** | AI-based process automation for prevention of atrocities against Scheduled Castes and Scheduled Tribes (SC/ST) |
| **Theme** | Smart Automation / AI for Social Impact |
| **Ministry** | MoSJE — Ministry of Social Justice & Empowerment |
| **Beneficiary Helpline** | National Helpline Against Atrocities — **NHAA 14566** |
| **Team Name** | Team NIDAAN |
| **Solution Title** | **NIDAAN — AI-Enabled Real-Time Stress & Trauma Assessment Middleware Engine for NHAA 14566** |

**Slide tagline (on-slide):**
> *"Every atrocity call is a voice under pressure. NIDAAN converts that voice into a live 0–100 risk index — and dispatches the right SC/ST Act response in seconds."*

**Presenter notes:** 30-second opener — NHAA 14566 logs abuse, threat, and life-risk calls from SC/ST victims; operators today must listen, paraphrase, classify, and escalate manually. NIDAAN gives them a live, explainable risk gauge.

---

## Slide 2 — Proposed Solution

**Goal:** Turn Helpline 14566 into an **asynchronous, priority-aware triage engine** — no call waits, no note-taking during the victim's narration.

**Key functionality (on-slide bullets):**

- **Asynchronous voice + text processing** — audio is streamed and analysed in **2-second chunks** over WebSocket while the operator speaks live; transcription text and acoustic features arrive in parallel, never blocking the call.
- **Live SVI (Stress–Vulnerability Index) calculation** — a single **0–100 fused score** combining acoustic distress (pitch instability, jitter, shimmer, tremor band, silence gaps) with lexical markers (10-category Hinglish trauma/abuse lexicon, severity-weighted with intensifiers):

  `SVI = C_audio · (0.4 · As + 0.6 · Ts) + (1 − C_audio) · Ts`

- **Tiered, statute-anchored dispatch integration** — the live SVI maps to an action plan every 2 seconds:

  | SVI | Tier | Immediate dispatch |
  |---|---|---|
  | 0–30 | LOW | Routine docket + SMS follow-up |
  | 31–60 | MODERATE | District Welfare Officer callback ≤ 24 h + 48 h safety recheck |
  | 61–80 | HIGH | Senior-counselor live transfer, tele-medical referral, DSP-level escalation |
  | 81–100 | CRITICAL | Emergency modal — queue bypass, District Police PCR ≤ 1 min, 108 ambulance, **Witness Protection (Sec 15A)** |

- **Operator cockpit** — live transcript, keyword highlights, risk gauge, waveform, per-feature trace, and the full statutory action card with owner + SLA + channel.

**Presenter notes:** emphasise the two asymmetric wins — (1) the victim never waits and never repeats their story; (2) the operator is a **verifier**, not a **scribe**.

---

## Slide 3 — Technical Approach & Architecture

**System flow (on-slide 4-node diagram):**

```
 Catch The Voice ──▶ Analyse In Parallel ──▶ Fuse & Classify ──▶ Dispatch & Track
 [WebRTC mic /     [Acoustic Analyzer          [SVI Engine       [PoA Recommender
  IVR audio file]   ‖  Text Analyzer]            (late fusion,      → operator dashboard
  → WS stream       → 2 s chunk pipeline        0–100, 4 tiers]    → emergency modal]
```

**Technology stack (on-slide table):**

| Layer | Technology | Role in NIDAAN |
|---|---|---|
| Backend runtime | **FastAPI + Uvicorn (Python 3.10+)** | REST + WebSocket live engine, session orchestration |
| Real-time transport | **WebRTC / WebSocket** | Browser mic capture, 2-second audio chunk streaming |
| Speech / Text | **Bhashini ASR + Whisper** (integration path) and built-in Hinglish lexicon scorer | Hindi/Hinglish + dialectal speech-to-text and keyword/trigger extraction |
| Acoustic analysis | **Librosa / pyin / OpenSMILE** (NumPy/SciPy fallback in-Core) | Pitch tracking, jitter, shimmer, tremor FFT (3–8 Hz band), silence ratio |
| Fusion & policy | SVI fusion formula + static tier bands | Explainable 0–100 escalation with statutory PoA mapping |
| UI | Vanilla JS dashboard (WebRTC + Canvas) | Gauge, trace, scenario player, offline mirror engine |

**Deployment-ready:** single-container `uvicorn backend.app:app` (Docker), port `8000`, with a full browser **offline fallback** so the SVI math runs even with zero network.

**Presenter notes:** one line per arrow — waveform in → features out → fused index → action steps. Everything shown is running code (15 calibrated scenarios, 36-test regression suite).

---

## Slide 4 — Feasibility & Viability

| Challenge | NIDAAN response |
|---|---|
| **Low-bandwidth telephony (PSTN/IVR callers)** | Chunked 2-second streaming with confidence-gated fusion — on silence/degraded audio, score degrades safely toward the text channel without dropping the session; async design tolerates bursts and jitter. |
| **Local languages / dialects** | Hinglish-first lexicon covering Hindi/Urdu/Punjabi/Bhojpuri mixed speech; **Bhashini** national language platforms + Whisper provide the ASR localisation path to 22 scheduled languages. |
| **Network/cloud unavailability** | Full **offline demo mode** — browser-embedded SVI engine (`offline_data.js`) reproduces identical features, formula, tiers, and action plans with zero backend; demo-guaranteed even in air-gapped judging rooms. |
| **MoSJE administrative integration** | Tiered plans map to real NHAA workflow owners (Welfare Office, Legal Aid Cell, District Police PCR, Witness Protection Cell) with named SLA + channel, ready for docket/ticketing system hand-off. |
| **Deployment cost** | Lightweight container (~1 GB), single-core viable, no GPU required at PoC stage; optics: a government-usable, air-gapped-friendly footprint. |

**Viability horizon:** PoC (this build) → NHAA pilot with MoSJE IT + NCCS; subject to federal consent-based deployment of Whisper/Bhashini ASR in the call path.

**Presenter notes:** the "never say network" moment — flip the machine to airplane mode and the demo keeps scoring, which de-risks the pilot.

---

## Slide 5 — Impact & Benefits

- **Reduces operator cognitive load** — the dashboard pre-classifies and pre-drafts the action plan; operator workload shifts from transcription/note-taking to empathy + verification. Estimated **≥30% call-handling effort saved** on critical-call intake.
- **Eliminates queue delay for critical atrocity cases** — CRITICAL calls **auto-bypass the queue**: switchboard bot transfer, PCR notification ≤ 1 min, ambulance ≤ 10 min — a live first-response bolus the manual helpline cannot match.
- **Strengthens SC/ST Act enforcement** — every CRITICAL case auto-anchors to **Sec 3(2)(v), Sec 15A(1), Sec 15A(2), Sec 21(2)** (Prevention of Atrocities Act, 1989 as amended 2015/2018) with a per-step SLA.
- **Witness protection tracking** — the PoA plan carries a **Witness Protection Cell** activation step (Sec 15A) with a 5-minute SLA and an encrypted victim-location dispatch to the nearest police station.
- **Guardrails** — explainable per-feature trace (no black box), confidence gating against garbage audio, human-in-the-loop override before any dispatch.

**Presenter notes:** maths-first impact — 24/7 triage at 2-second cadence, zero dropped detail between narration and docket.

---

## Slide 6 — Research & References

**Legal framework**
- The Scheduled Castes and the Scheduled Tribes (Prevention of Atrocities) Act, **1989** (No. 33 of 1989) and Rules.
- The Scheduled Castes and the Scheduled Tribes (Prevention of Atrocities) Amendment Act, **2015**.
- PoA Amendment Rules **2016 / 2018** — witness protection scheme and atrocity-case monitoring flow.
- Prevention of Atrocities Act sections mapped in PoA engine: **Sec 3(1)(r), 3(2)(v), 4, 6, 8, 15A(1/2), 18A, 21(2), 22**.
- MoSJE — **NHAA Helpline 14566** operational brief (National Helpline Against Atrocities, Dept. of Social Justice & Empowerment).

**Psychological distress / trauma benchmarks**
- WHO — *Psychological First Aid: Guide for Field Workers* (stress assessment + support escalation benchmarks).
- IASC — *Guidelines on Mental Health and Psychosocial Support in Emergency Settings* (2007) (PSSD pillar benchmarks used to design tier thresholds and recheck SLAs).
- WHO PSSD-style screening cues (sleep, agitation, withdrawal, verbalised suicidal intent) folded into the text lexicon severity weights.

**AI / speech frameworks**
- Bhashini — National Language Translation Mission (Digital India / MeitY) — ASR-MT platform for Indian languages (https://bhashini.gov.in).
- OpenAI Whisper — multilingual speech-to-text benchmark for Hindi/Hinglish live transcription path.
- OpenSMILE / librosa+pyin — paralinguistic acoustic feature standards underpinning `As`.

---

### Submission checklist (this deck source)
- [ ] Slide 1 carries PS ID `26093` + MoSJE/NHAA 14566
- [ ] Slides 1–6 exactly in official order
- [ ] Team name + solution title consistent with registration
- [ ] All technical claims (SVI formula, tiers, SLAs, sections) match the live repository