import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

HOST = os.getenv("NIDAAN_HOST", "0.0.0.0")
PORT = int(os.getenv("NIDAAN_PORT", "8000"))
DEBUG = os.getenv("NIDAAN_DEBUG", "true").lower() == "true"
LOG_LEVEL = os.getenv("NIDAAN_LOG_LEVEL", "INFO")

SVI_AUDIO_WEIGHT = float(os.getenv("NIDAAN_SVI_AUDIO_WEIGHT", "0.4"))
SVI_TEXT_WEIGHT = float(os.getenv("NIDAAN_SVI_TEXT_WEIGHT", "0.6"))
WS_PUSH_INTERVAL = float(os.getenv("NIDAAN_WS_PUSH_INTERVAL", "1.5"))
AUDIO_SAMPLE_RATE = int(os.getenv("NIDAAN_AUDIO_SAMPLE_RATE", "16000"))
AUDIO_CHUNK_DURATION_MS = int(os.getenv("NIDAAN_AUDIO_CHUNK_DURATION_MS", "500"))
MAX_CONCURRENT_STREAMS = int(os.getenv("NIDAAN_MAX_CONCURRENT_STREAMS", "50"))

DATA_DIR = BASE_DIR / os.getenv("NIDAAN_DATA_DIR", "./data")
SCENARIOS_PATH = DATA_DIR / "synthetic_scenarios.json"

RISK_THRESHOLDS = {
    "LOW": (0, 30),
    "MODERATE": (31, 60),
    "HIGH": (61, 80),
    "CRITICAL": (81, 100),
}

ACOUSTIC_FEATURES = {
    "pitch_std_threshold": 25.0,
    "silence_ratio_threshold": 0.45,
    "jitter_threshold": 0.02,
    "shimmer_threshold": 0.05,
    "tremor_freq_low": 3.0,
    "tremor_freq_high": 8.0,
    "min_voiced_frames": 10,
}

TEXT_FEATURES = {
    "physical_threat": 30,
    "land_arson": 28,
    "social_boycott": 22,
    "caste_abuse": 24,
    "suicidal_ideation": 52,
    "sexual_violence": 50,
    "property_damage": 20,
    "family_threat": 16,
    "economic_deprivation": 15,
    "exclusion": 16,
}

# Calibrated constants for the semantic trauma scoring model.
TEXT_OCCURRENCE_BONUS = 0.06
TEXT_INTENSITY_BONUS = 0.03
TEXT_MAX_CATEGORY_RATIO = 0.55
TEXT_CRISIS_BOOSTERS = {
    "suicidal_ideation": 30,
    "sexual_violence": 20,
}
TEXT_ARMED_TOKENS = ("goli", "fire")
TEXT_ARMED_BOOSTER = 20
TEXT_BOYCOTT_ECON_BOOSTER = 10
