"""
test_svi_engine.py
==================
Automated test suite for NIDAAN SVI Engine core fusion logic, REST endpoint
payload integrity, and WebSocket streaming contract.
"""
import sys
from pathlib import Path

import pytest
import numpy as np

# Project root on sys.path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.svi_engine import SVIEngine, SVIResult, RollingSVIWindow, _resolve_category, _clamp


# -----------------------------------------------------------------------
# Fusion math invariants
# -----------------------------------------------------------------------
class TestSVIBounds:
    """SVI score must always live in [0, 100]."""

    @pytest.mark.parametrize("as_val,ts_val", [
        (0, 0), (100, 100), (50, 50), (0, 100), (100, 0),
    ])
    def test_score_in_range(self, as_val, ts_val):
        eng = SVIEngine()
        result = eng.fuse(as_val, ts_val)
        assert 0 <= result.svi_score <= 100

    def test_all_none_inputs(self):
        result = SVIEngine().fuse(None, None)
        assert result.svi_score == 0.0
        assert result.risk_category == "LOW"


class TestTierCategorisation:
    """Continuous resolvers: 30.5→MODERATE, 60.06→HIGH, 80.5→CRITICAL."""

    @pytest.mark.parametrize("score,expected", [
        (0, "LOW"), (10, "LOW"), (30, "LOW"),
        (30.5, "MODERATE"), (45, "MODERATE"), (60, "MODERATE"),
        (60.06, "HIGH"), (75, "HIGH"), (80, "HIGH"),
        (80.5, "CRITICAL"), (90, "CRITICAL"), (100, "CRITICAL"),
    ])
    def test_boundary_continuous(self, score, expected):
        assert _resolve_category(score) == expected

    def test_negative_clamps_to_zero(self):
        assert _clamp(-50) == 0.0
        assert _resolve_category(-1) == "LOW"

    def test_over100_clamps_to_100(self):
        assert _clamp(200) == 100.0
        assert _resolve_category(150) == "CRITICAL"


class TestCaudioZeroDegradation:
    """When audio confidence is zero, SVI collapses to pure text score."""

    def test_caudio_zero_equals_text(self):
        eng = SVIEngine()
        for ts in [0, 25, 50, 75, 100]:
            result = eng.fuse(acoustic_score=90, text_score=ts, audio_confidence=0.0)
            assert result.svi_score == pytest.approx(ts, abs=0.5)

    def test_no_audio_equals_text(self):
        eng = SVIEngine()
        result = eng.fuse(acoustic_score=None, text_score=65)
        assert result.svi_score == pytest.approx(65, abs=1.0)

    def test_full_confidence_blends_audio_text(self):
        eng = SVIEngine()
        result = eng.fuse(acoustic_score=100, text_score=100, audio_confidence=1.0)
        assert result.svi_score == 100.0

    def test_mixed_confidence_shifts_toward_text(self):
        eng = SVIEngine()
        high_conf = eng.fuse(acoustic_score=100, text_score=0, audio_confidence=1.0)
        low_conf  = eng.fuse(acoustic_score=100, text_score=0, audio_confidence=0.3)
        assert low_conf.svi_score < high_conf.svi_score


# -----------------------------------------------------------------------
# SVIResult serialisation
# -----------------------------------------------------------------------
class TestSVIResultSerialisation:
    def test_to_dict_keys(self):
        result = SVIEngine().fuse(50, 50)
        d = result.to_dict()
        assert d["svi_score"] == pytest.approx(result.svi_score, abs=0.05)
        assert d["risk_category"] in ("LOW", "MODERATE", "HIGH", "CRITICAL")
        assert "timestamp" in d
        assert d["acoustic_score"] is not None
        assert d["audio_confidence"] is not None

    def test_to_json_is_valid(self):
        import json
        result = SVIEngine().fuse(70, 30)
        parsed = json.loads(result.to_json())
        assert "svi_score" in parsed


# -----------------------------------------------------------------------
# RollingSVIWindow aggregation
# -----------------------------------------------------------------------
class TestRollingWindow:
    def test_snapshot_frame_after_ingest(self):
        win = RollingSVIWindow(push_interval=0.0)
        win.ingest_acoustic(80.0, confidence=0.95)
        win.ingest_text(90.0)
        frame = win.snapshot_frame()
        assert frame is not None
        assert 60 <= frame.svi_score <= 100

    def test_window_discards_oldest(self):
        win = RollingSVIWindow(push_interval=0.0, window_size=3)
        for v in [10, 20, 30, 40]:
            win.ingest_acoustic(v, confidence=1.0)
        frame = win.snapshot_frame()
        # acoustic_window holds the last 3 of [10,20,30,40] -> mean(20,30,40)=30
        assert frame.acoustic_score == pytest.approx(30, abs=2)


# -----------------------------------------------------------------------
# REST endpoint contract (requires httpx / TestClient)
# -----------------------------------------------------------------------
class TestRESTAnalyzeText:
    """POST /api/v1/analyze-text returns valid structure."""

    @pytest.fixture()
    def client(self):
        from fastapi.testclient import TestClient
        from backend.app import app
        return TestClient(app)

    def test_health_returns_ok(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_analyze_text_structure(self, client):
        resp = client.post("/api/v1/analyze-text", json={"text": "They are threatening us with goli"})
        assert resp.status_code == 200
        body = resp.json()
        assert "analysis" in body
        assert "action_plan" in body
        assert body["analysis"]["semantic_trauma_score"] > 0

    def test_scenarios_endpoint(self, client):
        resp = client.get("/api/v1/scenarios")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 15
        assert len(data["scenarios"]) >= 15

    def test_analyze_text_empty_string_rejected(self, client):
        resp = client.post("/api/v1/analyze-text", json={"text": ""})
        assert resp.status_code == 422


# -----------------------------------------------------------------------
# WebSocket streaming payload contract
# -----------------------------------------------------------------------
class TestWebSocketStream:
    """Verify /ws/stream-svi message sequence and structure."""

    @pytest.fixture()
    def ws_url(self):
        from fastapi.testclient import TestClient
        return "ws://testserver/ws/stream-svi"

    @pytest.fixture()
    def client(self):
        from fastapi.testclient import TestClient
        from backend.app import app
        return TestClient(app)

    def test_session_start_on_connect(self, client):
        with client.websocket_connect("/ws/stream-svi") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "session_start"
            assert "session_id" in msg

    def test_text_analysis_payload(self, client):
        with client.websocket_connect("/ws/stream-svi") as ws:
            ws.receive_json()  # session_start
            ws.send_json({"type": "text_token", "text": "I want to die"})
            text_msg = ws.receive_json()
            assert text_msg["type"] == "text_analysis"
            assert "analysis" in text_msg

    def test_eof_returns_final_frame(self, client):
        with client.websocket_connect("/ws/stream-svi") as ws:
            ws.receive_json()  # session_start
            ws.send_json({"type": "eof"})
            final = ws.receive_json()
            assert final["type"] == "final_frame"
            assert "data" in final
            assert final["data"]["svi_score"] >= 0

    def test_reset_clears_state(self, client):
        with client.websocket_connect("/ws/stream-svi") as ws:
            ws.receive_json()
            ws.send_json({"type": "text_token", "text": "kill everyone"})
            ws.receive_json()  # text_analysis
            ws.send_json({"type": "reset"})
            ack = ws.receive_json()
            assert ack["type"] == "reset_ack"
            ws.send_json({"type": "eof"})
            final = ws.receive_json()
            assert final["type"] == "final_frame"
