# NIDAAN Demonstration Cheatsheet (Judge-Ready)

Target: 3–5 minutes, zero fluff, offline-safe.

---

## 0. The 30-Second Pitch (say this verbatim)

> "NIDAAN is a real-time distress engine for India's National Helpline Against Atrocities —
> it captures a caller's voice until one unit, from 0 to 100. It fuses **how** the caller sounds
> — pitch instability, tremor, jitter — with **what** they say — suicide cues, caste abuse,
> threats — into a single risk score. Every 2 seconds, the score drives a tiered Plan of Action
> anchored to the PoA Act 1989, from routine follow-up at LOW to instant police-PCR dispatch,
> ambulance, and Witness Protection at CRITICAL. No cloud dependency for the demo — it runs
> fully offline in your browser."

---

## 1. Exact Click Sequence (Live Judge Demo)

1. Open `index.html` (or `http://localhost:8000` via `run.py`). If the server is not running,
   the UI auto-enters **Demo Mode** — badge "Offline" appears. You never say "it's not working".
2. Toggle **Demo Mode** switch (top-right, optional — confirm it's checked).
3. Pick scenario from the dropdown — start with **sc-004 (Denied Drinking Water Access)**.
4. Click **Run Scenario** → waveform animates, chunks stream, trace fills in.
5. Let it run ~3 frames; watch **Risk Tier badge** settle at MODERATE and the **action plan card** swap to the 24-hour callback + safety recheck.
6. Switch to a HIGH case, e.g. **sc-008 (Threat of Harm)**, run it — now watch a senior counselor route + DSP-level escalation.
7. Finally **sc-011 / sc-012 (CRITICAL)** → watch the score climb **past 80**.
8. **The money shot:** the **Police/Medical Dispatch modal pops** — ready-docketed alert, PCR notification, ambulance SLA. Click **Acknowledge**.
9. Round-trip: rerun **sc-001 (routine inquiry)** → tier resets to LOW, modal never fires.
10. Optional: unplug/Airplane-mode the machine and repeat — everything above still works.

---

## 2. The Narrative (what the demo "says")

- **LOW (sc-001..003):** "calm caller, low distress — the system still logs a docket and sends an SMS. Nothing escalates automatically."
- **MODERATE (sc-004..006):** "the voice tightens — pitch spread up, tremor appears. A district welfare officer must call back within 24 hours, plus a 48-hour safety recheck."
- **HIGH (sc-007..009):** "coercive language + trembling voice. The call is live-transferred to a senior counselor while a DSP-level officer is issued a high-priority ticket."
- **CRITICAL (sc-011..015):** "the fusion hits 80+ — this is now an emergency. Call queue is bypassed, police PCR and 108 are notified within 60 seconds, victim location goes encrypted. That popup is the system doing its job, not a mock."

---

## 3. Judge Q&A — five most likely questions

**Q1. How is the score computed?**
> Late fusion: `SVI = C·(0.4·As + 0.6·Ts) + (1−C)·Ts`. `As` is the acoustic score —
> pitch instability (pyin), jitter, shimmer, tremor power in the 3–8 Hz band, silence ratio.
> `Ts` is the lexical score from a 10-category Hinglish lexicon with severity weights and
> intensifiers. `C` is audio confidence — on silence the score leans on text. Both branches
> are independently auditable in the trace panel.

**Q2. Why late fusion instead of a neural net?**
> Explainability for helpline staff and regulators. A single score with auditable acoustic and
> text components means a supervisor can see *why* a call escalated — same math in the offline
> browser engine, so the judge can verify the formula on any scenario.

**Q3. Is this really PoA Act 1989?**
> Yes — the Plan-of-Action steps map to statutory sections: crime-on-allegation escalation
> (`Sec 3(2)(v)`), Witness Protection (`Sec 15A(1)`), and victim notification duties (`Sec 6`,
> `Sec 8`). Dispatch SLAs and owners are listed per step in the action card.

**Q4. What happens when the server is down or the mic is blocked?**
> The browser fails over to the embedded offline SVI engine — identical lexicon, autocorrelation
> pitch, fusion formula, and tier bands. The demo still renders waveforms, tiers, and the dispatch
> modal. Perfect-demo guarantee.

**Q5. False positives?**
> The engine tunes toward sensitivity at CRITICAL (a false *dispatch alert* that a human confirms
> is cheaper than a missed emergency) but requires both acoustic stress *and* lexical lethality
> to reach 80+, and the confidence gate suppresses garbage audio. The trace panel exposes every
> contributing feature so a human can override before dispatch.

---

## 4. Numbers to have on hand

| Metric | Value |
|---|---|
| Live latency | ~2 s update cadence |
| Tier bands | 0–30 / 31–60 / 61–80 / 81–100 |
| Calibrated scenarios | 15 (3×LOW, 3×MODERATE, 3×HIGH, 6×CRITICAL) |
| Backend regression | 36/36 passing (`pytest tests/test_svi_engine.py`) |
| Offline verification | 15/15 tier fidelity (Node harness) |
| Fusion weights | Acoustic 0.4 / Text 0.6 (confidence-weighted) |

## 5. Emergency recovery lines (never stall)

- Microphone blocked → "we are in synthetic caller (Demo Mode) — designed for rooms without audio permissions."
- Server not running → "the offline engine is the same math, no network." (It is.)
- Judge asks to see LOW again → run sc-001, tier badge drops, modal stays closed.
- Time running out → skip sc-004..006, jump straight to sc-012 for the CRITICAL dispatch modal.