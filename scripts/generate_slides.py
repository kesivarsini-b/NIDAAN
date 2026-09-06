# ============================================================================
# NIDAAN - SIH 2025/26 submission deck generator
# ----------------------------------------------------------------------------
# Builds docs/NIDAAN_SIH_Presentation.pptx (6 slides) from the canonical
# copy-paste source docs/SIH_SUBMISSION_PPT.md.
#
# Usage:  python -m pip install python-pptx
#         python scripts/generate_slides.py
# ============================================================================

import os

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

DOCS_DIR = os.path.join(os.path.dirname(__file__), "..", "docs")
OUT_PATH = os.path.join(DOCS_DIR, "NIDAAN_SIH_Presentation.pptx")

# Theme ------------------------------------------------------------------------
ACCENT = RGBColor(0xE8, 0x5D, 0x30)   # NIDAAN ember
DARK = RGBColor(0x0F, 0x14, 0x1E)
PANEL = RGBColor(0x1A, 0x22, 0x33)
TEXT = RGBColor(0xE8, 0xEB, 0xF2)
MUTED = RGBColor(0xA9, 0xB3, 0xC8)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)

M = Inches(0.45)

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)
BLANK = prs.slide_layouts[6]


def _panel(slide, x, y, w, h, fill):
    from pptx.enum.shapes import MSO_SHAPE
    shp = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h)
    shp.fill.solid()
    shp.fill.fore_color.rgb = fill
    shp.line.fill.background()
    shp.shadow.inherit = False
    return shp


def _textbox(slide, x, y, w, h):
    box = slide.shapes.add_textbox(x, y, w, h)
    tf = box.text_frame
    tf.word_wrap = True
    return tf


def _fill(tf, lines):
    for i, (text, size, color, bold, space_after) in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        run = p.add_run()
        run.text = text
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.color.rgb = color
        run.font.name = "Segoe UI"
        if space_after is not None:
            p.space_after = Pt(space_after)
    return tf


def _header(slide, title, subtitle=None):
    _panel(slide, Inches(0), Inches(0), prs.slide_width, Inches(1.0), DARK)
    bar = slide.shapes.add_shape(
        __import__("pptx.enum.shapes", fromlist=["MSO_SHAPE"]).MSO_SHAPE.RECTANGLE,
        Inches(0), Inches(0.92), prs.slide_width, Inches(0.08),
    )
    bar.fill.solid()
    bar.fill.fore_color.rgb = ACCENT
    bar.line.fill.background()
    bar.shadow.inherit = False
    tf = _textbox(slide, M, Inches(0.12), Inches(11), Inches(0.8))
    _fill(tf, [(title, 26, WHITE, True, None)])
    if subtitle:
        tf2 = _textbox(slide, Inches(11.6), Inches(0.28), Inches(1.4), Inches(0.6))
        _fill(tf2, [(subtitle, 11, MUTED, False, None)])


def _bullet(tf, text, size=14, color=TEXT, bold=False, space=6):
    p = tf.add_paragraph()
    run = p.add_run()
    run.text = "\u25B8  " + text
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    run.font.name = "Segoe UI"
    p.space_after = Pt(space)
    return p


def _table(slide, x, y, w, h, data, col_widths=None, header_fill=PANEL,
           body_size=12, header_size=12):
    from pptx.enum.shapes import MSO_SHAPE
    rows, cols = len(data), len(data[0])
    shape = slide.shapes.add_table(rows, cols, x, y, w, h)
    table = shape.table
    if col_widths:
        for ci, cw in enumerate(col_widths):
            table.columns[ci].width = cw
    for ri, row in enumerate(data):
        for ci, val in enumerate(row):
            cell = table.cell(ri, ci)
            cell.margin_left = Inches(0.08)
            cell.margin_right = Inches(0.08)
            cell.margin_top = Inches(0.03)
            cell.margin_bottom = Inches(0.03)
            cell.vertical_anchor = 1  # MIDDLE
            tfc = cell.text_frame
            tfc.word_wrap = True
            p = tfc.paragraphs[0]
            run = p.add_run()
            run.text = str(val)
            run.font.size = Pt(header_size if ri == 0 else body_size)
            run.font.bold = (ri == 0)
            run.font.color.rgb = WHITE if ri == 0 else TEXT
            run.font.name = "Segoe UI"
            cell.fill.solid()
            cell.fill.fore_color.rgb = header_fill if ri == 0 else DARK
    return table


# Slide 1 - Title -----------------------------------------------------------------
s = prs.slides.add_slide(BLANK)
_panel(s, Inches(0), Inches(0), prs.slide_width, prs.slide_height, DARK)
bar = s.shapes.add_shape(
    __import__("pptx.enum.shapes", fromlist=["MSO_SHAPE"]).MSO_SHAPE.RECTANGLE,
    Inches(0), Inches(4.55), prs.slide_width, Inches(0.06),
)
bar.fill.solid()
bar.fill.fore_color.rgb = ACCENT
bar.line.fill.background()
bar.shadow.inherit = False

tf = _textbox(s, M, Inches(1.4), Inches(12.4), Inches(2.6))
_fill(tf, [
    ("SMART INDIA HACKATHON 2025/26  \u2014  SOFTWARE EDITION", 16, ACCENT, True, 10),
    ("NIDAAN \u2014 AI-Enabled Real-Time Stress & Trauma Assessment Middleware Engine for NHAA 14566", 34, WHITE, True, 12),
    ("Every atrocity call is a voice under pressure. NIDAAN converts that voice into a live 0\u2013100 risk index \u2014 and dispatches the right SC/ST Act response in seconds.", 15, MUTED, False, None),
])

tf = _textbox(s, M, Inches(5.0), Inches(12.4), Inches(1.7))
_fill(tf, [
    ("Problem Statement ID: 26093    |    Theme: Smart Automation / AI for Social Impact", 14, TEXT, False, 6),
    ("Ministry of Social Justice & Empowerment (MoSJE)  \u2014  National Helpline Against Atrocities (NHAA 14566)", 13, TEXT, False, 6),
    ("Team NIDAAN", 15, ACCENT, True, None),
])


# Slide 2 - Proposed Solution ------------------------------------------------------
s = prs.slides.add_slide(BLANK)
_header(s, "Proposed Solution", "PS 26093")

tf = _textbox(s, M, Inches(1.15), Inches(12.4), Inches(1.55))
_fill(tf, [("Goal: turn Helpline 14566 into an asynchronous, priority-aware triage engine \u2014 no call waits, no note-taking during the victim's narration.", 14, TEXT, False, None)])

tf = _textbox(s, M, Inches(2.05), Inches(7.4), Inches(4.6))
_fill(tf, [("", 1, TEXT, False, 2)])
_bullet(tf, "Asynchronous voice + text processing \u2014 audio streamed & analysed in 2-second chunks over WebSocket; never blocks the call.")
_bullet(tf, "Live SVI (Stress\u2013Vulnerability Index) \u2014 single 0\u2013100 fused score from acoustic distress (pitch instability, jitter, shimmer, tremor band 3\u20138 Hz, silence gaps) + 10-category Hinglish trauma/abuse lexicon.")
_bullet(tf, "Tiered, statute-anchored dispatch \u2014 live SVI re-mapped to a PoA action plan every 2 seconds.")
_bullet(tf, "Operator cockpit \u2014 live transcript, keyword highlights, risk gauge, waveform, per-feature trace, full statutory action card (owner + SLA + channel).")

tf = _textbox(s, Inches(7.85), Inches(2.05), Inches(4.9), Inches(2.2))
_fill(tf, [("", 1, TEXT, False, 2)])
p = tf.add_paragraph()
run = p.add_run()
run.text = "SVI = C\u1D00\u1D64\u2C97\u1D65\u1D68 \u00B7 (0.4 \u00B7 As + 0.6 \u00B7 Ts) + (1 \u2212 C\u1D00\u1D64\u2C97\u1D65\u1D68) \u00B7 Ts"
run.font.size = Pt(17)
run.font.bold = True
run.font.color.rgb = ACCENT
run.font.name = "Consolas"
p.space_after = Pt(8)
_fill(tf, [("C = audio channel confidence; As = acoustic score; Ts = text score. On silence/degraded audio, score degrades safely to the text channel.", 12, MUTED, False, None)])

_table(s, M, Inches(4.05), Inches(12.4), Inches(3.1), [
    ["SVI", "Tier", "Immediate dispatch"],
    ["0\u201330", "LOW", "Routine docket + SMS follow-up"],
    ["31\u201360", "MODERATE", "District Welfare Officer callback \u2264 24 h + 48 h safety recheck"],
    ["61\u201380", "HIGH", "Senior-counselor live transfer, tele-medical referral, DSP-level escalation"],
    ["81\u2013100", "CRITICAL", "Queue bypass, District Police PCR \u2264 1 min, 108 ambulance \u2264 10 min, Witness Protection (Sec 15A)"],
], col_widths=[Inches(1.2), Inches(2.0), Inches(9.2)])


# Slide 3 - Technical Approach ----------------------------------------------------
s = prs.slides.add_slide(BLANK)
_header(s, "Technical Approach & Architecture", "PS 26093")

tf = _textbox(s, M, Inches(1.15), Inches(12.4), Inches(0.7))
_fill(tf, [("System flow", 15, TEXT, True, None)])

flow = [("Catch The Voice", "WebRTC mic / IVR audio file \u2192 WS stream"),
        ("Analyse In Parallel", "Acoustic Analyzer \u2225 Text Analyzer \u00B7 2 s chunks"),
        ("Fuse & Classify", "SVI Engine \u00B7 late fusion \u00B7 0\u2013100 \u00B7 4 tiers"),
        ("Dispatch & Track", "PoA Recommender \u2192 dashboard / emergency modal")]
x = M
_w = Inches(2.9)
_gap = Inches(0.55)
for i, (head, sub) in enumerate(flow):
    _panel(s, x, Inches(1.75), _w, Inches(1.05), PANEL)
    tf = _textbox(s, x + Inches(0.08), Inches(1.85), _w - Inches(0.16), Inches(0.85))
    _fill(tf, [(f"{i+1}. {head}", 13, WHITE, True, 2), (sub, 9.5, MUTED, False, None)])
    if i < 3:
        ar = s.shapes.add_shape(
            __import__("pptx.enum.shapes", fromlist=["MSO_SHAPE"]).MSO_SHAPE.RIGHT_ARROW,
            x + _w, Inches(2.05), _gap, Inches(0.5),
        )
        ar.fill.solid()
        ar.fill.fore_color.rgb = ACCENT
        ar.line.fill.background()
        ar.shadow.inherit = False
    x = x + _w + _gap

_table(s, M, Inches(3.15), Inches(12.4), Inches(3.9), [
    ["Layer", "Technology", "Role in NIDAAN"],
    ["Backend runtime", "FastAPI + Uvicorn (Python 3.10+)", "REST + WebSocket live engine, session orchestration"],
    ["Real-time transport", "WebRTC / WebSocket", "Browser mic capture, 2-second audio chunk streaming"],
    ["Speech / Text", "Bhashini ASR + Whisper (integration path); built-in Hinglish lexicon", "Hindi/Hinglish speech-to-text and keyword/trigger extraction"],
    ["Acoustic analysis", "librosa / pyin / OpenSMILE (NumPy/SciPy fallback in-core)", "Pitch, jitter, shimmer, tremor FFT (3\u20138 Hz), silence ratio"],
    ["Fusion & policy", "SVI fusion formula + static tier bands", "Explainable 0\u2013100 escalation with statutory PoA mapping"],
    ["UI", "Vanilla JS dashboard (WebRTC + Canvas)", "Gauge, trace, scenario player, offline mirror engine"],
], col_widths=[Inches(2.0), Inches(4.4), Inches(6.0)], body_size=10.5, header_size=11)

tf = _textbox(s, M, Inches(6.95), Inches(12.4), Inches(0.5))
_fill(tf, [("Deployment-ready: single-container uvicorn backend.app:app (Docker, port 8000) with a full browser offline fallback \u2014 the SVI math runs with zero network.", 12, MUTED, False, None)])


# Slide 4 - Feasibility & Viability ------------------------------------------------
s = prs.slides.add_slide(BLANK)
_header(s, "Feasibility & Viability", "PS 26093")

_table(s, M, Inches(1.15), Inches(12.4), Inches(4.6), [
    ["Challenge", "NIDAAN response"],
    ["Low-bandwidth telephony (PSTN/IVR)", "Chunked 2-second streaming, confidence-gated fusion \u2014 on silence/degraded audio the score degrades safely to the text channel without dropping the session."],
    ["Local languages / dialects", "Hinglish-first lexicon (Hindi/Urdu/Punjabi/Bhojpuri mixed); Bhashini + Whisper path to 22 scheduled languages."],
    ["Network / cloud unavailability", "Full offline demo mode \u2014 browser-embedded SVI engine (offline_data.js) reproduces identical features, formula, tiers and action plans with zero backend."],
    ["MoSJE administrative integration", "Tiered plans map to real NHAA workflow owners (Welfare Office, Legal Aid Cell, District Police PCR, Witness Protection Cell) with named SLA + channel."],
    ["Deployment cost", "Lightweight container (~1 GB), single-core viable, no GPU at PoC stage \u2014 air-gapped-friendly footprint."],
], col_widths=[Inches(3.4), Inches(9.0)], body_size=11)

p = _panel(s, M, Inches(5.95), Inches(12.4), Inches(1.2), PANEL)
tf = _textbox(s, M + Inches(0.15), Inches(6.05), Inches(12.1), Inches(1.0))
_fill(tf, [
    ("Viability horizon", 14, ACCENT, True, 4),
    ("PoC (this build) \u2192 NHAA pilot with MoSJE IT + NCCS; consent-based deployment of Whisper/Bhashini ASR in the call path.", 13, TEXT, False, None),
])


# Slide 5 - Impact & Benefits -------------------------------------------------------
s = prs.slides.add_slide(BLANK)
_header(s, "Impact & Benefits", "PS 26093")

tf = _textbox(s, M, Inches(1.25), Inches(12.4), Inches(5.9))
_fill(tf, [
    ("", 1, TEXT, False, 4),
    ("\u25B8  Reduces operator cognitive load \u2014", 15, WHITE, True, 2),
    ("     dashboard pre-classifies & pre-drafts the action plan; \u226530% call-handling effort saved on critical-call intake.", 13.5, TEXT, False, 10),
    ("\u25B8  Eliminates queue delay for critical atrocity cases \u2014", 15, WHITE, True, 2),
    ("     queue bypass, PCR notification \u2264 1 min, ambulance \u2264 10 min \u2014 a live first-response bolus manual helplines cannot match.", 13.5, TEXT, False, 10),
    ("\u25B8  Strengthens SC/ST Act enforcement \u2014", 15, WHITE, True, 2),
    ("     every CRITICAL case auto-anchors to Sec 3(2)(v), 15A(1), 15A(2), 21(2) with a per-step SLA.", 13.5, TEXT, False, 10),
    ("\u25B8  Witness-protection tracking \u2014", 15, WHITE, True, 2),
    ("     PoA plan carries Witness Protection Cell activation (Sec 15A, 5-min SLA) + encrypted victim-location dispatch.", 13.5, TEXT, False, 10),
    ("\u25B8  Guardrails \u2014", 15, WHITE, True, 2),
    ("     explainable per-feature trace, confidence-gated audio, human-in-the-loop override before any dispatch.", 13.5, TEXT, False, None),
])

p = _panel(s, Inches(0.7), Inches(6.35), Inches(11.9), Inches(0.8), PANEL)
tf = _textbox(s, Inches(0.85), Inches(6.45), Inches(11.6), Inches(0.6))
_fill(tf, [("24/7 triage at a 2-second cadence \u2014 zero dropped detail between the victim's narration and the statutory docket.", 14, ACCENT, True, None)])


# Slide 6 - Research & References ---------------------------------------------------
s = prs.slides.add_slide(BLANK)
_header(s, "Research & References", "PS 26093")

tf = _textbox(s, M, Inches(1.2), Inches(12.4), Inches(6.1))
_fill(tf, [
    ("Legal framework", 16, ACCENT, True, 4),
    ("\u25B8  The Scheduled Castes and the Scheduled Tribes (Prevention of Atrocities) Act, 1989 (No. 33 of 1989) and Rules.", 13, TEXT, False, 4),
    ("\u25B8  The SC/ST (Prevention of Atrocities) Amendment Act, 2015; PoA Amendment Rules 2016 / 2018 (witness protection scheme).", 13, TEXT, False, 4),
    ("\u25B8  Sections mapped in PoA engine: Sec 3(1)(r), 3(2)(v), 4, 6, 8, 15A(1/2), 18A, 21(2), 22.", 13, TEXT, False, 8),
    ("Psychological distress / trauma benchmarks", 16, ACCENT, True, 4),
    ("\u25B8  WHO Psychological First Aid: Guide for Field Workers; IASC MHPSS Guidelines (2007) \u2014 tier thresholds & recheck SLAs.", 13, TEXT, False, 4),
    ("\u25B8  WHO PSSD-style screening cues (sleep, agitation, withdrawal, verbalised suicidal intent) folded into lexicon severity weights.", 13, TEXT, False, 8),
    ("AI / speech frameworks", 16, ACCENT, True, 4),
    ("\u25B8  Bhashini \u2014 National Language Translation Mission (bhashini.gov.in); OpenAI Whisper \u2014 live transcription path.", 13, TEXT, False, 4),
    ("\u25B8  OpenSMILE / librosa + pyin \u2014 paralinguistic acoustic standards underpinning the acoustic score As.", 13, TEXT, False, 4),
    ("\u25B8  MoSJE \u2014 National Helpline Against Atrocities (NHAA 14566) operational brief.", 13, TEXT, False, None),
])


prs.save(OUT_PATH)
print("Wrote", os.path.abspath(OUT_PATH))