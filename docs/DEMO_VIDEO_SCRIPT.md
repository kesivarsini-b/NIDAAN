# NIDAAN — 3-Minute Demo Video Script (Frame-by-Frame)

> **Video title:** NIDAAN — AI-Enabled Distress Triage for NHAA Helpline 14566
> **Target runtime:** 3 minutes exactly (hard cut). Total: 4 acts, 12 frames.
> **Format specs:** 1080p, 16:9, H.264 + AAC, subtitles ON (English), voiceover pace ≈ 150 wpm.

---

## ACT 1 — 0:00 → 0:30 · Problem Hook & Call-Volume Bottlenecks

| Time | Frame | Visual | Voiceover (read verbatim) |
|---|---|---|---|
| 0:00 | 1a | Cold open: dark screen, single ring, a real 14566 call-center scene (borrowed footage) — headsets, screens, long queues | "Every minute in India, someone from a Scheduled Caste or Tribe community faces abuse, threats, and violence — and calls the National Helpline Against Atrocities, 14566." |
| 0:06 | 1b | Animated counter: "1 operator · 1 voice · 1 notebook" with three separate fatigue icons appearing | "Today one operator must *listen*, *take notes*, *classify*, and *escalate* — all while a distressed victim is still talking." |
| 0:12 | 1c | Call-flow graphic: caller → queue → operator → manual form → escalation (5 hops, each highlighted red). Animated "QUEUE DELAY" stamp | "Critical cases can sit in a queue. Every second of delay is a second a victim stands unprotected." |
| 0:18 | 1d | Big caption: **"What if the system could listen, score, and dispatch — while the operator just… connects?"** | "NIDAAN answers that question live." |

---

## ACT 2 — 0:30 → 1:30 · Live Dashboard Session (screen recording)

| Time | Frame | Visual | Voiceover |
|---|---|---|---|
| 0:30 | 2a | Full screen: NIDAAN dashboard. Mouse hovers the **Demo Mode** toggle and clicks it ON. Badge "Offline" appears top-left | "This is the NIDAAN cockpit. To keep the demo honestly network-independent, we run the engine's browser mirror — identical math — in Demo Mode." |
| 0:37 | 2b | Scenario dropdown opens; select **sc-007 → "Threat of Harm"**. Mouse clicks **Run Scenario**. Waveform bursts to life | "A caller describes being threatened — in Hinglish, the languages our helpline actually hears." |
| 0:44 | 2c | Slow zoom on the **transcript panel** as tokens enter chunk-by-chunk; keyword chips light up *(dhamki, goli, jaan, log)* and the **keyword list** fills | "As the voice streams, trauma keywords are highlighted in real time — the words that, legally and clinically, must not be missed." |
| 0:55 | 2d | Gauge sweep: SVI climbs **40 → 60 → 67**. Tier badge flips LOW→MODERATE→**HIGH**. Action-plan card swaps to "Senior Counselor live transfer · DSP escalation" | "Acoustic stress meets lexical lethality. Within twelve seconds the fused index crosses into HIGH." |
| 1:05 | 2e | Left panel tour (scrub annotation rectangles): **pitch instability, tremor band, jitter** sparklines, then the **confidence %** readout | "Every number is explainable — pitch spread, tremor in the 3-to-8 hertz fear band, jitter — plus an audio-confidence weight on top." |
| 1:14 | 2f | Hard cut to **sc-012 → CRITICAL**. Gauge surges past **80**. **Police/Medical Dispatch modal slides in** — ack button pulsing | "Now the same pipeline on a life-threat call. NIDAAN doesn't just score — it dispatches." |

---

## ACT 3 — 1:30 → 2:15 · SVI Deep-Dive & SC/ST Act Dispatch

| Time | Frame | Visual | Voiceover |
|---|---|---|---|
| 1:30 | 3a | Animated formula build-up, term by term:<br>`SVI = C·(0.4·As + 0.6·Ts) + (1−C)·Ts` (As = acoustic, Ts = text, C = confidence) | "The engine uses late fusion — thirty percent of the weight chases how the voice shakes, sixty percent what the words confess, all gated by audio confidence." |
| 1:42 | 3b | Split screen: left the **acoustic trace** (pitch_std 6 → 18 across the distress ladder), right the **lexicon categories** with severity sliders | "Both channels are auditable, so a supervisor can always answer: *why did this call escalate?*" |
| 1:54 | 3c | Close-up of the dispatch modal contents: "Sec 15A(1) · Witness Protection Cell · ≤5 min", "District Police PCR · ≤1 min", "Ambulance 108 · ≤10 min" | "On CRITICAL, the plan auto-anchors to the Prevention of Atrocities Act — witness protection, police response, and medical dispatch, each with its SLA." |
| 2:03 | 3d | Cursor clicks **Acknowledge** → modal closes → docket line item appears in the "Case Docket" log, timestamped | "One click. The docket is logged and the statutory chain is underway — the operator stays human, the state stays fast." |

---

## ACT 4 — 2:15 → 3:00 · Impact, Scalability, Offline Proof, Close

| Time | Frame | Visual | Voiceover |
|---|---|---|---|
| 2:15 | 4a | Metric cards animate in: **2s** update cadence · **0–100** explainable index · **15** calibrated scenarios · **36/36** regression tests | "Built for 24/7 scale: a two-second cadence that never blocks the call line." |
| 2:24 | 4b | Network toggle: show tray, turn **Wi-Fi OFF**. Dashboard keeps scoring sc-005, badge stays live, no errors | "And the offline proof — force the laptop's network down, and the SVI engine keeps running. Judges included." |
| 2:32 | 4c | Deployment slide: Docker container icon → `port 8000`, arrows to operator PCs and helpline IVR | "One lightweight container ships the whole engine — ready for MoSJE's pilot cloud or on-prem racks." |
| 2:41 | 4d | Final frame: team name, PS ID **26093**, **NIDAAN — वजह से समाधान तक** ("from root cause to resolution") | "NIDAAN turns a voice under pressure into a response on the ground. Team NIDAAN — thank you." |

---

## Production notes

- **B-roll:** keep real helpline footage in Act 1 to *outrage*, switch to screen capture in Act 2 onward.
- **Subtitles:** burn English subs; top 20% for Act 1 (numbers on screen), bottom for dashboard acts.
- **Music:** room-tone intro → low pulse from 1:30 → resolve warm at 2:41. No vocals over narration.
- **Length guards:** if behind schedule, cut frame 2e (feature tour) first, then 4b (require offline proof).
- **Truth-checks before render:** all SVI numbers (67 / 82) are reproduced by `mock_caller.py` against the released build; re-run before final render.