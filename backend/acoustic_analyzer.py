"""
acoustic_analyzer.py
====================
NIDAAN - Voice Prosody & Acoustic Distress Analysis Module.

Extracts acoustic features that correlate with psychological distress:
  - Pitch variance (delta Pitch) - elevated F0 instability under stress
  - Unvoiced silence ratio (T_silence / T_total) - hesitation / speech arrest
  - Jitter & Shimmer - micro-perturbations of frequency and amplitude
  - Tremor (3-8 Hz modulations) - psychomotor agitation
  - Signal amplitude / RMS dynamics

Produces an Acoustic Distress Score (As) in [0, 100] and a Signal Confidence
metric (C_audio) in [0, 1] reflecting how reliable the audio channel is.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

import config

try:
    import soundfile as sf

    _HAS_SOUNDFILE = True
except ImportError:  # pragma: no cover
    _HAS_SOUNDFILE = False

try:
    import librosa

    _HAS_LIBROSA = True
except ImportError:  # pragma: no cover
    _HAS_LIBROSA = False

TREMOR_LOW = config.ACOUSTIC_FEATURES["tremor_freq_low"]
TREMOR_HIGH = config.ACOUSTIC_FEATURES["tremor_freq_high"]
MIN_VOICED_FRAMES = config.ACOUSTIC_FEATURES["min_voiced_frames"]


class AcousticAnalyzer:
    """
    Processes raw PCM audio (float32 numpy arrays, mono) and produces the
    acoustic distress metrics used by the SVI fusion engine.
    """

    def __init__(self, sample_rate: int = config.AUDIO_SAMPLE_RATE) -> None:
        self.sample_rate = sample_rate
        self.library = self._detect_library()

    @staticmethod
    def _detect_library() -> str:
        if _HAS_LIBROSA:
            return "librosa"
        return "numpy"

    # -- Public API ----------------------------------------------------------

    def analyze(self, pcm: np.ndarray, sample_rate: Optional[int] = None) -> Dict[str, Any]:
        """
        Analyze a mono PCM float32 signal.

        Returns a dictionary containing:
            acoustic_score     (float, 0-100)
            signal_confidence  (float, 0-1)
            pitch_std          (Hz)
            pitch_mean         (Hz)
            silence_ratio      (0-1)
            jitter             (0-1 fraction)
            shimmer            (0-1 fraction)
            rms_dynamics       (float)
            tremor_strength    (float)
            features           (raw feature dictionary)
        """
        sr = sample_rate or self.sample_rate
        pcm = self._prepare(pcm)

        rms = self._compute_rms(pcm)
        silence_ratio = self._compute_silence_ratio(pcm, rms)
        voiced_mask = self._voiced_mask(pcm)

        pitch, voicing_prob = self._estimate_pitch(pcm, sr, voiced_mask)

        framed = self._frame(pcm, sr)
        frame_rms = np.sqrt((framed ** 2).mean(axis=1) + 1e-10)

        jitter = self._compute_jitter(frame_rms)
        shimmer = self._compute_shimmer(frame_rms)
        tremor_strength = self._compute_tremor(frame_rms, sr)

        signal_confidence = self._compute_confidence(
            rms=rms,
            silence_ratio=silence_ratio,
            voiced_frames=pitch.size,
        )

        acoustic_score = self._compute_acoustic_score(
            pitch_std=pitch.std() if pitch.size else 0.0,
            silence_ratio=silence_ratio,
            jitter=jitter,
            shimmer=shimmer,
            tremor_strength=tremor_strength,
            signal_confidence=signal_confidence,
        )

        return {
            "acoustic_score": round(acoustic_score, 2),
            "signal_confidence": round(signal_confidence, 3),
            "pitch_std": round(float(pitch.std()) if pitch.size else 0.0, 3),
            "pitch_mean": round(float(pitch.mean()) if pitch.size else 0.0, 3),
            "silence_ratio": round(silence_ratio, 3),
            "jitter": round(jitter, 5),
            "shimmer": round(shimmer, 5),
            "rms_dynamics": round(float(rms), 5),
            "tremor_strength": round(tremor_strength, 5),
            "features": {
                "frame_count": int(pitch.size),
                "library": self.library,
                "sample_rate": sr,
            },
        }

    def analyze_live_chunk(self, pcm: np.ndarray) -> Dict[str, Any]:
        return self.analyze(pcm)

    def load_audio_file(self, path: str) -> Tuple[np.ndarray, int]:
        """Load an audio file and resample to the configured rate."""
        if not _HAS_SOUNDFILE:
            raise RuntimeError("soundfile is required to load audio files.")
        data, sr = sf.read(path, dtype="float32", always_2d=False)
        if data.ndim > 1:
            data = data.mean(axis=1)
        return data, sr

    # -- Private helpers -----------------------------------------------------

    @staticmethod
    def _prepare(pcm: np.ndarray) -> np.ndarray:
        pcm = np.asarray(pcm, dtype=np.float32)
        if pcm.ndim > 1:
            pcm = pcm.mean(axis=1)
        if pcm.size == 0:
            raise ValueError("Empty audio signal provided.")
        eps = 1e-10
        peak = float(np.max(np.abs(pcm))) + eps
        return pcm / peak

    def _frame(self, pcm: np.ndarray, sr: int, frame_ms: int = 25, hop_ms: int = 10) -> np.ndarray:
        frame_len = max(1, int(sr * frame_ms / 1000))
        hop = max(1, int(sr * hop_ms / 1000))
        n_frames = max(1, (pcm.size - frame_len) // hop + 1)
        idx = np.arange(frame_len)
        frames = np.stack([pcm[idx + i * hop] for i in range(n_frames)])
        return frames

    def _compute_rms(self, pcm: np.ndarray) -> float:
        return float(np.sqrt(np.mean(pcm ** 2) + 1e-10))

    def _frame_rms(self, pcm: np.ndarray, sr: int) -> np.ndarray:
        framed = self._frame(pcm, sr)
        return np.sqrt((framed ** 2).mean(axis=1) + 1e-10)

    def _compute_silence_ratio(self, pcm: np.ndarray, global_rms: float) -> float:
        sr = self.sample_rate
        frame_rms = self._frame_rms(pcm, sr)
        threshold = max(global_rms * 0.1, 1e-4)
        silent = np.sum(frame_rms < threshold)
        return float(silent / max(1, frame_rms.size))

    def _voiced_mask(self, pcm: np.ndarray) -> np.ndarray:
        sr = self.sample_rate
        frame_rms = self._frame_rms(pcm, sr)
        energy_threshold = float(np.percentile(frame_rms, 30))
        return frame_rms > energy_threshold

    def _estimate_pitch(self, pcm: np.ndarray, sr: int, voiced_mask: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        if self.library == "librosa":
            try:
                f0, voiced_flag, _ = librosa.pyin(
                    pcm,
                    fmin=70.0,
                    fmax=400.0,
                    sr=sr,
                    frame_length=1024,
                    hop_length=512,
                )
                f0 = f0[voiced_flag]
                f0 = f0[np.isfinite(f0)]
                return f0, voiced_flag
            except Exception:
                pass

        # Numpy fallback: autocorrelation-based pitch tracking.
        frame_len = int(sr * 0.03)
        hop = int(sr * 0.01)
        if pcm.size < frame_len:
            return np.array([]), np.array([])

        n_frames = (pcm.size - frame_len) // hop
        pitches = []
        voiced_flags = []
        for i in range(n_frames):
            frame = pcm[i * hop: i * hop + frame_len]
            r = np.correlate(frame, frame, mode="full")[frame_len - 1:]
            r[: max(1, int(sr / 400))] = 0
            if r.size == 0 or r.max() <= 0:
                voiced_flags.append(False)
                continue
            lag = int(np.argmax(r))
            f0 = sr / lag if lag > 0 else 0.0
            if 70.0 <= f0 <= 400.0 and r[lag] > 0.3 * r[0]:
                pitches.append(f0)
                voiced_flags.append(True)
            else:
                voiced_flags.append(False)
        return np.array(pitches, dtype=np.float64), np.array(voiced_flags, dtype=bool)

    @staticmethod
    def _zero_crossing_rate(frame: np.ndarray) -> float:
        if frame.size < 2:
            return 0.0
        return float(np.mean(np.abs(np.diff(np.sign(frame))) / 2))

    def _compute_jitter(self, frame_rms: np.ndarray) -> float:
        if frame_rms.size < 3:
            return 0.0
        valid = frame_rms[frame_rms > 1e-6]
        if valid.size < 3:
            return 0.0
        diff = np.abs(np.diff(valid))
        return float(np.mean(diff) / np.mean(valid) + 1e-8)

    def _compute_shimmer(self, frame_rms: np.ndarray) -> float:
        if frame_rms.size < 3:
            return 0.0
        valid = frame_rms[frame_rms > 1e-6]
        if valid.size < 3:
            return 0.0
        return float(np.std(valid) / np.mean(valid) + 1e-8)

    def _compute_tremor(self, frame_rms: np.ndarray, sr: int) -> float:
        if frame_rms.size < 16:
            return 0.0
        n = frame_rms.size
        freqs = np.fft.rfftfreq(n, d=float(sr * 0.01))
        amp = np.abs(np.fft.rfft(frame_rms - frame_rms.mean()))
        band = (freqs >= TREMOR_LOW) & (freqs <= TREMOR_HIGH)
        if not np.any(band):
            return 0.0
        band_energy = float(np.sum(amp[band] ** 2))
        total_energy = float(np.sum(amp ** 2)) + 1e-10
        return float(band_energy / total_energy)

    @staticmethod
    def _compute_confidence(rms: float, silence_ratio: float, voiced_frames: int) -> float:
        confidence = 0.5
        if rms > 0.02:
            confidence += 0.2
        elif rms > 0.005:
            confidence += 0.1
        if silence_ratio < 0.45:
            confidence += 0.2
        else:
            confidence += 0.05
        if voiced_frames >= MIN_VOICED_FRAMES:
            confidence += 0.1
        return max(0.0, min(1.0, confidence))

    @staticmethod
    def _compute_acoustic_score(
        pitch_std: float,
        silence_ratio: float,
        jitter: float,
        shimmer: float,
        tremor_strength: float,
        signal_confidence: float,
    ) -> float:
        pitch_std_norm = min(1.0, pitch_std / config.ACOUSTIC_FEATURES["pitch_std_threshold"])
        silence_norm = min(1.0, silence_ratio / config.ACOUSTIC_FEATURES["silence_ratio_threshold"])
        jitter_norm = min(1.0, jitter / config.ACOUSTIC_FEATURES["jitter_threshold"])
        shimmer_norm = min(1.0, shimmer / config.ACOUSTIC_FEATURES["shimmer_threshold"])
        tremor_norm = min(1.0, tremor_strength * 4.0)

        raw = (
            0.30 * pitch_std_norm
            + 0.25 * silence_norm
            + 0.15 * jitter_norm
            + 0.15 * shimmer_norm
            + 0.15 * tremor_norm
        ) * 100.0

        confidence_penalty = (1.0 - signal_confidence) * 15.0
        score = max(0.0, raw - confidence_penalty)
        return min(100.0, score)


analyzer = AcousticAnalyzer()
