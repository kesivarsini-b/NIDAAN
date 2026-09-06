"""
svi_engine.py
=============
NIDAAN - Multimodal SVI (Stress & Vulnerability Index) Fusion Engine.

Implements the core fusion algorithm that combines acoustic metrics (As) and
text/semantic metrics (Ts) into a single Stress & Vulnerability Index using a
dynamic signal-confidence-weighted formula:

    SVI = C_audio * (0.4 * As + 0.6 * Ts) + (1 - C_audio) * Ts

Where:
    As       - Acoustic Distress Score in [0, 100]
    Ts       - Semantic Trauma Score in [0, 100]
    C_audio  - Signal Confidence in [0, 1] (reliability of the audio channel)

The audio weight (0.4) and text weight (0.6) are calibrated in config.py and
can be tuned at runtime for production deployment.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import config


@dataclass
class SVIResult:
    """Immutable container for a single fusion-engine output frame."""
    svi_score: float
    risk_category: str
    primary_triggers: List[str]
    timestamp: str
    acoustic_score: Optional[float] = None
    text_score: Optional[float] = None
    audio_confidence: Optional[float] = None
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "svi_score": round(self.svi_score, 2),
            "risk_category": self.risk_category,
            "primary_triggers": self.primary_triggers,
            "timestamp": self.timestamp,
            "acoustic_score": round(self.acoustic_score, 2) if self.acoustic_score is not None else None,
            "text_score": round(self.text_score, 2) if self.text_score is not None else None,
            "audio_confidence": round(self.audio_confidence, 3) if self.audio_confidence is not None else None,
            "meta": self.meta,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, float(value)))


# Single source of truth for the continuous risk bands. The same bands are
# mirrored by the browser offline engine and the PoA recommender.
TIER_BANDS: List[Dict[str, Any]] = [
    {"category": "LOW", "band_low": 0, "band_high": 30},
    {"category": "MODERATE", "band_low": 31, "band_high": 60},
    {"category": "HIGH", "band_low": 61, "band_high": 80},
    {"category": "CRITICAL", "band_low": 81, "band_high": 100},
]


def _resolve_category(score: float) -> str:
    score = _clamp(score)
    for band in TIER_BANDS:
        if score <= band["band_high"]:
            return band["category"]
    return "CRITICAL"


def tier_band_info(score: float) -> Dict[str, Any]:
    """Return the active band plus 0..1 progress toward crossing its ceiling.

    Progress is (score - band_low) / (band_high - band_low + 1), so a gauge
    can render a distinct, immediate transition the moment the score tips
    into the next band.
    """
    score = _clamp(score)
    for band in TIER_BANDS:
        if score <= band["band_high"]:
            span = max(1, band["band_high"] - band["band_low"] + 1)
            return {
                "category": band["category"],
                "band_low": band["band_low"],
                "band_high": band["band_high"],
                "band_progress": round((score - band["band_low"]) / span, 4),
            }
    return {"category": "CRITICAL", "band_low": 81, "band_high": 100, "band_progress": 1.0}


class SVIEngine:
    """
    Multimodal Stress & Vulnerability Index Fusion Engine.

    The engine is stateless with respect to individual frames; callers (e.g.
    the WebSocket stream handler) maintain rolling window state and supply the
    current aggregate acoustic and text scores.
    """

    def __init__(
        self,
        audio_weight: float = config.SVI_AUDIO_WEIGHT,
        text_weight: float = config.SVI_TEXT_WEIGHT,
    ) -> None:
        self.audio_weight = audio_weight
        self.text_weight = text_weight

    def fuse(
        self,
        acoustic_score: Optional[float],
        text_score: Optional[float],
        audio_confidence: Optional[float] = None,
        primary_triggers: Optional[List[str]] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> SVIResult:
        """
        Compute the fused SVI score.

        Parameters
        ----------
        acoustic_score : float | None
            Acoustic Distress Score As in [0, 100]. May be None if the live
            audio pipeline has not produced a robust estimate yet.
        text_score : float | None
            Semantic Trauma Score Ts in [0, 100].
        audio_confidence : float | None
            Signal Confidence Caudio in [0, 1]. When provided it overrides the
            internal degradation compensation; when None or undefined the
            engine derives a conservative confidence from whether acoustic
            data exists.
        primary_triggers : list[str] | None
            Most salient trigger labels surfaced from either modality.
        meta : dict | None
            Optional diagnostic metadata to embed in the frame.
        """
        ts = _clamp(text_score if text_score is not None else 0.0)

        # --- Dynamic degradation compensation --------------------------------
        if audio_confidence is None:
            if acoustic_score is None:
                # No usable audio: fall back entirely to the text channel.
                caudio = 0.0
                as_effective = 0.0
            else:
                # Audio exists but confidence was not supplied: assume a
                # conservative 0.6 reliability for voice-quality frames.
                caudio = 0.6
                as_effective = _clamp(acoustic_score)
        else:
            caudio = max(0.0, min(1.0, float(audio_confidence)))
            as_effective = _clamp(acoustic_score) if acoustic_score is not None else 0.0

        # --- Fusion formula --------------------------------------------------
        # SVI = Caudio * (Aw*As + Tw*Ts) + (1 - Caudio) * Ts
        acoustic_component = (self.audio_weight * as_effective) + (self.text_weight * ts)
        svi = caudio * acoustic_component + (1.0 - caudio) * ts
        svi = _clamp(svi)

        triggers = list(primary_triggers or [])[:8]

        meta_payload = {
            "degradation_compensation": {
                "audio_confidence": round(caudio, 3),
                "formula": "C*(" + str(self.audio_weight) + "*As+" + str(self.text_weight) + "*Ts)+(1-C)*Ts",
            },
            "tier": tier_band_info(svi),
            **(meta or {}),
        }

        return SVIResult(
            svi_score=svi,
            risk_category=_resolve_category(svi),
            primary_triggers=triggers,
            timestamp=datetime.now(timezone.utc).isoformat(),
            acoustic_score=as_effective,
            text_score=ts,
            audio_confidence=caudio,
            meta=meta_payload,
        )


class RollingSVIWindow:
    """
    Per-stream rolling analyser that aggregates incremental acoustic and text
    updates and emits fused SVI frames on a scheduled cadence (1-2 seconds).
    """

    def __init__(
        self,
        push_interval: float = config.WS_PUSH_INTERVAL,
        window_size: int = 20,
    ) -> None:
        self.engine = SVIEngine()
        self.push_interval = push_interval
        self.window_size = window_size
        self.acoustic_window: List[float] = []
        self.text_window: List[float] = []
        self.confidence_window: List[float] = []
        self.triggers: Dict[str, int] = {}
        self.last_push_ts: float = time.monotonic()

    def ingest_acoustic(self, acoustic_score: float, confidence: Optional[float] = None) -> None:
        self.acoustic_window.append(_clamp(acoustic_score))
        if len(self.acoustic_window) > self.window_size:
            self.acoustic_window.pop(0)
        if confidence is not None:
            self.confidence_window.append(max(0.0, min(1.0, confidence)))
            if len(self.confidence_window) > self.window_size:
                self.confidence_window.pop(0)

    def ingest_text(self, text_score: float, triggers: Optional[List[str]] = None) -> None:
        self.text_window.append(_clamp(text_score))
        if len(self.text_window) > self.window_size:
            self.text_window.pop(0)
        for t in triggers or []:
            self.triggers[t] = self.triggers.get(t, 0) + 1

    @staticmethod
    def _mean(values: List[float]) -> float:
        return sum(values) / len(values) if values else 0.0

    @property
    def has_acoustic(self) -> bool:
        return len(self.acoustic_window) > 0

    def current_frame(self, force: bool = False) -> Optional[SVIResult]:
        now = time.monotonic()
        if not force and (now - self.last_push_ts) < self.push_interval:
            if not self.has_acoustic and not self.text_window:
                return None
            return None

        agg_acoustic = self._mean(self.acoustic_window) if self.has_acoustic else None
        agg_text = self._mean(self.text_window) if self.text_window else 0.0
        agg_conf = self._mean(self.confidence_window) if self.confidence_window else None

        top_triggers = sorted(self.triggers.items(), key=lambda kv: kv[1], reverse=True)
        trigger_labels = [label for label, _ in top_triggers]

        frame = self.engine.fuse(
            acoustic_score=agg_acoustic,
            text_score=agg_text,
            audio_confidence=agg_conf,
            primary_triggers=trigger_labels,
            meta={
                "acoustic_frames": len(self.acoustic_window),
                "text_frames": len(self.text_window),
            },
        )
        self.last_push_ts = now
        return frame

    def snapshot_frame(self) -> SVIResult:
        return self.current_frame(force=True)


engine = SVIEngine()
