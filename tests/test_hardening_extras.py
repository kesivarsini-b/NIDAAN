"""
test_hardening_extras.py
========================
Regression coverage for the post-release hardening pass:
  * zero-error acoustic fallbacks (empty / short-chunk / degenerate input)
  * tier-band info surfaced by the SVI engine final frame
  * per-step statutory clause anchors on every PoA action plan
"""
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.acoustic_analyzer import AcousticAnalyzer
from backend.svi_engine import SVIEngine, _resolve_category, tier_band_info
from backend.poa_recommender import recommender

PASSBAND = ("LOW", "MODERATE", "HIGH", "CRITICAL")


# -----------------------------------------------------------------------
# Acoustic zero-error guarantees
# -----------------------------------------------------------------------
class TestAcousticFallbacks:
    """Degenerate inputs must never raise - they degrade to a neutral frame."""

    def test_empty_signal_returns_neutral(self):
        r = AcousticAnalyzer().analyze(np.array([], dtype=np.float32))
        assert r["acoustic_score"] == 0.0
        assert r["features"]["frame_count"] == 0

    def test_short_chunk_below_one_frame(self):
        r = AcousticAnalyzer().analyze(np.zeros(120, dtype=np.float32))
        assert r["acoustic_score"] == 0.0
        assert r["features"]["frame_count"] == 0

    def test_silence_does_not_crash(self):
        a = AcousticAnalyzer()
        r = a.analyze(np.zeros(16000, dtype=np.float32))
        assert r["signal_confidence"] < 1.0
        assert 0.0 <= r["acoustic_score"] <= 100.0

    def test_tiny_random_noise_does_not_crash(self):
        rng = np.random.default_rng(7)
        r = AcousticAnalyzer().analyze(rng.standard_normal(300).astype(np.float32))
        assert 0.0 <= r["acoustic_score"] <= 100.0

    def test_normal_sine_produces_frames(self):
        sr = 16000
        sig = (0.5 * np.sin(2 * np.pi * 160 * np.arange(sr) / sr)).astype(np.float32)
        r = AcousticAnalyzer().analyze(sig)
        assert r["features"]["frame_count"] > 0
        assert r["signal_confidence"] == pytest.approx(1.0, abs=0.01)

    def test_live_chunk_accepts_tiny_input(self):
        a = AcousticAnalyzer()
        chunk = np.zeros(8000, dtype=np.float32)
        r = a.analyze_live_chunk(chunk)
        assert 0.0 <= r["acoustic_score"] <= 100.0
        assert r == a.analyze(chunk)

    def test_neutral_frame_structure_complete(self):
        frame = AcousticAnalyzer._neutral_frame(16000)
        assert frame["signal_confidence"] == 0.0
        assert frame["acoustic_score"] == 0.0
        assert frame["features"]["frame_count"] == 0
        assert frame["features"]["library"]
        assert frame["features"]["sample_rate"] == 16000
        assert "silence_ratio" in frame


# -----------------------------------------------------------------------
# Tier band info
# -----------------------------------------------------------------------
class TestTierBandInfo:
    def test_band_boundaries_match_resolve_category(self):
        for score in [0, 30, 30.5, 60, 60.06, 80, 80.5, 100]:
            info = tier_band_info(score)
            assert info["category"] == _resolve_category(score)

    def test_band_progress_in_unit_interval(self):
        for score in [5, 45, 70, 95]:
            info = tier_band_info(score)
            assert 0.0 <= info["band_progress"] <= 1.0
            assert info["band_low"] <= info["band_high"]

    def test_band_progress_monotonic_within_band(self):
        low = tier_band_info(1)["band_progress"]
        high = tier_band_info(29)["band_progress"]
        assert high > low

    def test_clamped_extremes(self):
        assert tier_band_info(-5)["category"] == "LOW"
        assert tier_band_info(150)["category"] == "CRITICAL"
        # 150 clamps to 100 -> 19/20 of the CRITICAL band (81-100)
        assert tier_band_info(150)["band_progress"] == pytest.approx(0.95)

    def test_fuse_meta_exposes_tier(self):
        r = SVIEngine().fuse(90, 60)
        assert 61 <= r.svi_score <= 80  # HIGH band
        assert r.to_dict()["meta"]["tier"]["category"] == "HIGH"


# -----------------------------------------------------------------------
# PoA recommender statutory payloads
# -----------------------------------------------------------------------
class TestPoARecommenderPayloads:
    def test_every_step_carries_statute(self):
        for tier in PASSBAND:
            plan = recommender.recommend_for_tier(tier)
            for step in plan.steps:
                assert step.statute, f"{tier} step {step.step} missing statute"
                assert "PoA Act 1989" in step.statute

    def test_legal_framework_amendment_year(self):
        plan = recommender.recommend_for_tier("LOW")
        assert "as amended 2015" in plan.legal_framework

    def test_to_dict_rounded_safe(self):
        plan = recommender.recommend_for_tier("CRITICAL")
        d = plan.to_dict()
        assert d["legal_framework"] == plan.legal_framework
        assert len(d["poa_sections"]) >= 3
        assert all("statute" in s for s in d["steps"])
        assert d["risk_tier"] == "CRITICAL"

    def test_escalation_contacts_present_higher_tiers(self):
        for tier in ("MODERATE", "HIGH", "CRITICAL"):
            plan = recommender.recommend_for_tier(tier)
            assert len(plan.escalation_contacts) >= 2

    def test_critical_plan_includes_witness_protection(self):
        plan = recommender.recommend_for_tier("CRITICAL")
        sections = " ".join(plan.poa_sections)
        assert "15A" in sections
        actions = " ".join(s.action for s in plan.steps)
        assert "Witness Protection" in actions

    def test_recommend_actions_accepts_score_or_tier(self):
        assert recommender.recommend_actions(85)["risk_tier"] == "CRITICAL"
        assert recommender.recommend_actions("high")["risk_tier"] == "HIGH"

    def test_all_plans_flat_dict(self):
        all_plans = recommender.all_plans()
        assert set(all_plans.keys()) == set(PASSBAND)