"""
app.py
======
NIDAAN - FastAPI WebSockets & REST Server.

Endpoints:
    GET  /                        - Serve the operator dashboard static UI
    GET  /api/v1/scenarios        - Return pre-built synthetic test scenarios
    POST /api/v1/analyze-text     - REST text-narrative risk analysis
    POST /api/v1/analyze-audio    - REST audio-file acoustic analysis
    GET  /api/v1/action-plans     - Listing of statutory action plans by tier
    WS   /ws/stream-svi           - Real-time audio/text stream SVI fusion
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from fastapi import (
    FastAPI,
    File,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import config
from backend.acoustic_analyzer import AcousticAnalyzer, analyzer as acoustic_analyzer
from backend.poa_recommender import recommender
from backend.svi_engine import RollingSVIWindow, SVIEngine
from backend.text_analyzer import TextRiskAnalyzer, analyzer as text_analyzer

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("nidaan.app")

BASE_DIR = config.BASE_DIR
FRONTEND_DIR = BASE_DIR / "frontend"

app = FastAPI(
    title="NIDAAN - National Intelligent Distress & Atrocity Assessment Network",
    version="0.1.0",
    description="AI-Enabled Real-Time Stress & Trauma Assessment Middleware Engine "
                "for the National Helpline Against Atrocities (NHAA - 14566).",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------
class AnalyzeTextRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=10000, description="Transcript / narrative to analyse.")


class AnalyzeAudioRequest(BaseModel):
    audio_base64: str = Field(..., description="Base64-encoded mono PCM float32 payload.")


class SVIResponse(BaseModel):
    svi_score: float
    risk_category: str
    primary_triggers: List[str]
    timestamp: str
    acoustic_score: Optional[float] = None
    text_score: Optional[float] = None
    audio_confidence: Optional[float] = None
    meta: Dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Scenario store helper
# ---------------------------------------------------------------------------
def load_scenarios() -> List[Dict[str, Any]]:
    path: Path = config.SCENARIOS_PATH
    if not path.exists():
        logger.warning("Scenarios file not found at %s", path)
        return []
    try:
        with path.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
        return payload.get("scenarios", [])
    except Exception as exc:  # pragma: no cover
        logger.error("Unable to load scenarios: %s", exc)
        return []


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------
@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return JSONResponse({"detail": "Frontend not built yet."}, status_code=404)


@app.get("/api/v1/scenarios")
async def get_scenarios() -> JSONResponse:
    scenarios = load_scenarios()
    return JSONResponse({"count": len(scenarios), "scenarios": scenarios})


@app.post("/api/v1/analyze-text")
async def analyze_text(request: AnalyzeTextRequest) -> JSONResponse:
    result = text_analyzer.analyze(request.text)
    plan = recommender.recommend_for_score(result.semantic_trauma_score)
    return JSONResponse(
        {
            "analysis": result.to_dict(),
            "action_plan": plan.to_dict(),
        }
    )


@app.post("/api/v1/analyze-audio")
async def analyze_audio(request: AnalyzeAudioRequest) -> JSONResponse:
    try:
        raw = base64.b64decode(request.audio_base64)
        pcm = np.frombuffer(raw, dtype=np.float32)
    except Exception as exc:
        return JSONResponse({"detail": f"Invalid audio payload: {exc}"}, status_code=400)

    acoustic = acoustic_analyzer.analyze(pcm)
    return JSONResponse({"acoustic": acoustic})


@app.post("/api/v1/upload-audio")
async def upload_audio(file: UploadFile = File(...)) -> JSONResponse:
    content = await file.read()
    try:
        import soundfile as sf

        data, sr = sf.read(io.BytesIO(content), dtype="float32", always_2d=False)
        if data.ndim > 1:
            data = data.mean(axis=1)
    except Exception as exc:
        return JSONResponse({"detail": f"Unable to decode audio: {exc}"}, status_code=400)
    acoustic = acoustic_analyzer.analyze(data, sample_rate=sr)
    return JSONResponse({"filename": file.filename, "acoustic": acoustic})


@app.get("/api/v1/action-plans")
async def get_action_plans() -> JSONResponse:
    return JSONResponse(recommender.all_plans())


@app.get("/api/v1/health")
async def health() -> JSONResponse:
    return JSONResponse(
        {
            "status": "ok",
            "service": "NIDAAN",
            "version": "0.1.0",
            "time": datetime.now(timezone.utc).isoformat(),
            "libraries": {
                "librosa": acoustic_analyzer.library,
            },
            "thresholds": config.RISK_THRESHOLDS,
        }
    )


# ---------------------------------------------------------------------------
# WebSocket stream handler
# ---------------------------------------------------------------------------
class StreamConnectionManager:
    """Tracks active WebSocket streams keyed by session id."""

    def __init__(self) -> None:
        self.active: Dict[str, WebSocket] = {}
        self.lock = asyncio.Lock()

    async def connect(self, session_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self.lock:
            self.active[session_id] = websocket

    async def disconnect(self, session_id: str) -> None:
        async with self.lock:
            self.active.pop(session_id, None)

    @property
    def count(self) -> int:
        return len(self.active)


manager = StreamConnectionManager()


def _decode_audio_chunk(payload: str) -> np.ndarray:
    """Decode a websocket audio payload (base64 float32 or 'base64:wav')."""
    try:
        if payload.startswith("wav:"):
            wav_b64 = payload[len("wav:"):]
            wav_bytes = base64.b64decode(wav_b64)
            import soundfile as sf

            data, _ = sf.read(io.BytesIO(wav_bytes), dtype="float32", always_2d=False)
            if data.ndim > 1:
                data = data.mean(axis=1)
            return np.asarray(data, dtype=np.float32)

        raw = base64.b64decode(payload)
        return np.frombuffer(raw, dtype=np.float32)
    except Exception:
        return np.array([], dtype=np.float32)


def _parse_text_scope(msg: Dict[str, Any]) -> List[str]:
    triggers = text_analyzer.analyze(msg.get("text", "")).primary_triggers
    return triggers


@app.websocket("/ws/stream-svi")
async def websocket_svi(websocket: WebSocket) -> None:
    session_id = str(uuid.uuid4())
    await manager.connect(session_id, websocket)
    logger.info("WebSocket stream opened: %s (active=%d)", session_id, manager.count)

    window = RollingSVIWindow(push_interval=config.WS_PUSH_INTERVAL)
    transcript_parts: List[str] = []

    try:
        await websocket.send_json(
            {
                "type": "session_start",
                "session_id": session_id,
                "interval": config.WS_PUSH_INTERVAL,
                "message": "NIDAAN SVI stream connected.",
            }
        )

        while True:
            try:
                message = await asyncio.wait_for(websocket.receive_text(), timeout=0.5)
            except asyncio.TimeoutError:
                # Emit a periodic frame on the scheduled cadence.
                frame = window.current_frame()
                if frame is not None:
                    plan = recommender.recommend_for_score(frame.svi_score)
                    await websocket.send_json(
                        {
                            "type": "svi_frame",
                            "data": frame.to_dict(),
                            "action_plan": plan.to_dict(),
                        }
                    )
                continue
            except WebSocketDisconnect:
                break

            if message == "__PING__":
                await websocket.send_json({"type": "pong", "session_id": session_id})
                continue

            try:
                msg: Dict[str, Any] = json.loads(message)
            except json.JSONDecodeError:
                # Treat as raw audio chunk payload.
                pcm = _decode_audio_chunk(message)
                if pcm.size:
                    acoustic = acoustic_analyzer.analyze_live_chunk(pcm)
                    window.ingest_acoustic(
                        acoustic_score=acoustic["acoustic_score"],
                        confidence=acoustic["signal_confidence"],
                    )
                continue

            msg_type = msg.get("type", "")

            if msg_type == "audio_chunk":
                pcm = _decode_audio_chunk(msg.get("data", ""))
                if pcm.size:
                    acoustic = acoustic_analyzer.analyze_live_chunk(pcm)
                    window.ingest_acoustic(
                        acoustic_score=acoustic["acoustic_score"],
                        confidence=acoustic["signal_confidence"],
                    )

            elif msg_type == "text_token":
                token = msg.get("text", "")
                if token:
                    transcript_parts.append(token)
                    result = text_analyzer.analyze(" ".join(transcript_parts[-40:]))
                    window.ingest_text(
                        text_score=result.semantic_trauma_score,
                        triggers=result.primary_triggers,
                    )
                    await websocket.send_json(
                        {
                            "type": "text_analysis",
                            "partial_transcript": " ".join(transcript_parts[-40:]),
                            "analysis": result.to_dict(),
                        }
                    )

            elif msg_type == "reset":
                transcript_parts.clear()
                window = RollingSVIWindow(push_interval=config.WS_PUSH_INTERVAL)
                await websocket.send_json({"type": "reset_ack", "session_id": session_id})

            elif msg_type == "eof":
                frame = window.snapshot_frame()
                if frame is not None:
                    plan = recommender.recommend_for_score(frame.svi_score)
                    await websocket.send_json(
                        {
                            "type": "final_frame",
                            "data": frame.to_dict(),
                            "action_plan": plan.to_dict(),
                        }
                    )

            elif msg_type == "scenario":
                scenario_id = msg.get("scenario_id")
                scenarios = load_scenarios()
                selected = next((s for s in scenarios if str(s.get("id")) == str(scenario_id)), None)
                if selected:
                    transcript_parts.append(selected.get("transcript", ""))
                    result = text_analyzer.analyze(selected.get("transcript", ""))
                    window.ingest_text(
                        text_score=result.semantic_trauma_score,
                        triggers=result.primary_triggers,
                    )
                    await websocket.send_json(
                        {
                            "type": "scenario_loaded",
                            "scenario": selected,
                            "expected_tier": selected.get("expected_risk"),
                            "text_analysis": result.to_dict(),
                        }
                    )

    except WebSocketDisconnect:
        logger.info("WebSocket stream closed: %s", session_id)
    finally:
        await manager.disconnect(session_id)
        logger.info("WebSocket stream cleaned up: %s (active=%d)", session_id, manager.count)


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def startup() -> None:
    logger.info("NIDAAN service starting up...")
    scenarios = load_scenarios()
    logger.info("Loaded %d synthetic scenarios from %s", len(scenarios), config.SCENARIOS_PATH)


@app.on_event("shutdown")
async def shutdown() -> None:
    logger.info("NIDAAN service shutting down...")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.app:app",
        host=config.HOST,
        port=config.PORT,
        reload=config.DEBUG,
    )
