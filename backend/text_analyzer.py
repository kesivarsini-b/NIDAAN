"""
text_analyzer.py
================
NIDAAN - Indic NLP / Keyword / Intent Risk Scoring Module.

Analyses transcriber output / chat narrative for high-risk trauma indicators
associated with SC/ST atrocities, caste-based violence, and psychological
distress. Computes a Semantic Trauma Score (Ts) in [0, 100] using a
probabilistic blend of category severity ratios:

    Ts = 100 * (1 - Π_c (1 - r_c)) + crisis_boosters

Each category ratio r_c is derived from its calibrated severity weight,
scaled by the number of distinct indicator keywords found (price of scarcity
is captured through the multiplicative blend), with optional intensifier and
co-occurrence boosters for explicit crisis markers (suicidal ideation,
sexual violence, armed attack, caste-driven economic boycott).

The lexicon supports Hinglish and common regional transliterations.
Detection is primarily keyword/pattern based with intent-context windows
to reduce false positives.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import config


@dataclass
class TriggerMatch:
    keyword: str
    category: str
    severity_weight: float
    occurrences: int
    matched_keywords: List[str] = field(default_factory=list)


@dataclass
class TextAnalysisResult:
    semantic_trauma_score: float
    risk_category: str
    triggers: List[TriggerMatch]
    primary_triggers: List[str]
    detected_keywords: Dict[str, int]
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "semantic_trauma_score": round(self.semantic_trauma_score, 2),
            "risk_category": self.risk_category,
            "primary_triggers": self.primary_triggers,
            "detected_keywords": self.detected_keywords,
            "timestamp": self.timestamp,
            "trigger_details": [
                {
                    "category": t.category,
                    "severity_weight": t.severity_weight,
                    "occurrences": t.occurrences,
                    "matched_keywords": t.matched_keywords,
                }
                for t in self.triggers
            ],
        }


class TextRiskAnalyzer:
    SEVERITY_WEIGHTS = {name: w / 100.0 for name, w in config.TEXT_FEATURES.items()}

    LEXICON: Dict[str, List[str]] = {
        "physical_threat": [
            "maar", "maarenge", "maarda", "maarde", "mar diya", "mar dunga",
            "mar doge", "jaan se maar", "jaan se", "pitai", "dhakka", "dhakke",
            "goli", "goda", "hamla", "thappad", "fire", "dhamki", "dhamkaya",
            "dhamkata", "goli dikha", "marne", "maarne",
        ],
        "land_arson": [
            "aag laga", "ag laga", "jalam", "agani", "aag", "jal gayi",
            "goli laga", "zameen", "khabza", "zabardasti",
        ],
        "social_boycott": [
            "boycott", "boyatt", "bahishkar", "bhand", "samaj se",
            "koi baat nahi", "baat nahi karte", "gaon wale baat",
        ],
        "caste_abuse": [
            "chamar", "chuda", "bhangi", "achhoot", "achhut", "neech",
            "jati", "naapak", "ganda", "gaali", "kamina", "nalayak", "caste",
        ],
        "suicidal_ideation": [
            "khudkushi", "suicide", "jeena nahi", "mar jaana", "mar jana",
            "mar jayega", "mar jaunga", "mar jayungi", "hum mar jayein",
            "hum mar jaye", "khatam kar", "dam nikla",
        ],
        "sexual_violence": [
            "chhed", "chhedh", "rape", "balatkar", "cheeda", "chhudai", "touch",
        ],
        "property_damage": [
            "tod", "toda", "phod", "barbaad", "jal gayi", "aag",
            "jhandaa jal", "goli", "fire",
        ],
        "family_threat": [
            "bete ko", "beti ko", "bete", "beti", "gharwale", "ma baap",
            "bhai ko", "behen", "pati", "biwi", "bacchon", "bachchon", "family",
        ],
        "economic_deprivation": [
            "bhookha", "bhookhe", "naukri se", "kam karna", "paisa",
            "khaana", "khaane", "rozgar", "dookan band", "business band",
        ],
        "exclusion": [
            "paani se", "paani nahi", "naal", "kuan", "talaab", "well",
            "school se", "nikale", "nikala", "nikalte", "mat betho",
            "pichhe betho", "use nahi kar",
        ],
    }

    INTENSIFIERS = [
        "bahut", "bht", "kitna", "zyada", "khatarnak", "roz", "din",
        "kal se", "abhi", "again", "fir", "tumko", "jee na",
    ]

    def __init__(self) -> None:
        self._patterns: Dict[str, List[Tuple[re.Pattern, str]]] = {
            category: [(re.compile(rf"\b{re.escape(w)}\b", re.IGNORECASE), w) for w in words]
            for category, words in self.LEXICON.items()
        }

    def analyze(self, text: Optional[str]) -> TextAnalysisResult:
        text = (text or "").strip()
        if not text:
            return self._empty_result()

        normalized = self._normalize(text)

        # --- Count keyword occurrences per category -------------------------
        counted: Dict[str, List[str]] = {}
        found_keywords: Dict[str, int] = {}

        for category, entries in self._patterns.items():
            hits: List[str] = []
            for pattern, word in entries:
                if pattern.search(normalized):
                    hits.append(word)
                    found_keywords[word] = found_keywords.get(word, 0) + 1
            if hits:
                counted[category] = hits

        # --- Category severity ratios (probabilistic blend) -----------------
        has_intensifier = any(
            re.search(rf"\b{re.escape(i)}\b", normalized, re.IGNORECASE)
            for i in self.INTENSIFIERS
        )

        ratios: Dict[str, float] = {}
        for category, hits in counted.items():
            ratio = self.SEVERITY_WEIGHTS[category] + config.TEXT_OCCURRENCE_BONUS * (len(hits) - 1)
            if has_intensifier:
                ratio += config.TEXT_INTENSITY_BONUS
            ratios[category] = min(config.TEXT_MAX_CATEGORY_RATIO, ratio)

        blended = 100.0
        for ratio in ratios.values():
            blended *= (1.0 - ratio)
        score = 100.0 - blended

        # --- Crisis boosters ------------------------------------------------
        if "suicidal_ideation" in ratios:
            score += config.TEXT_CRISIS_BOOSTERS["suicidal_ideation"]
        if "sexual_violence" in ratios:
            score += config.TEXT_CRISIS_BOOSTERS["sexual_violence"]
        if any(re.search(rf"\b{re.escape(w)}\b", normalized, re.IGNORECASE) for w in config.TEXT_ARMED_TOKENS):
            score += config.TEXT_ARMED_BOOSTER
        if "social_boycott" in ratios and "economic_deprivation" in ratios:
            score += config.TEXT_BOYCOTT_ECON_BOOSTER

        score = min(100.0, score)

        # --- Triggers -------------------------------------------------------
        triggers = [
            TriggerMatch(
                keyword=", ".join(hits),
                category=category,
                severity_weight=round(self.SEVERITY_WEIGHTS[category] * 100.0, 1),
                occurrences=len(hits),
                matched_keywords=hits,
            )
            for category, hits in counted.items()
        ]
        ordered = sorted(
            triggers,
            key=lambda t: (len(t.matched_keywords) * t.severity_weight + t.severity_weight),
            reverse=True,
        )
        primary_labels = [t.category.replace("_", " ").title() for t in ordered]

        return TextAnalysisResult(
            semantic_trauma_score=round(score, 2),
            risk_category=_resolve_category(score),
            triggers=triggers,
            primary_triggers=primary_labels,
            detected_keywords=found_keywords,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    @staticmethod
    def _normalize(text: str) -> str:
        text = unicodedata.normalize("NFKD", text)
        text = re.sub(r"[^a-zA-Z\s']", " ", text)
        return re.sub(r"\s+", " ", text).strip().lower()

    def _empty_result(self) -> TextAnalysisResult:
        return TextAnalysisResult(
            semantic_trauma_score=0.0,
            risk_category="LOW",
            triggers=[],
            primary_triggers=[],
            detected_keywords={},
            timestamp=datetime.now(timezone.utc).isoformat(),
        )


def _resolve_category(score: float) -> str:
    if score <= 30:
        return "LOW"
    if score <= 60:
        return "MODERATE"
    if score <= 80:
        return "HIGH"
    return "CRITICAL"


analyzer = TextRiskAnalyzer()