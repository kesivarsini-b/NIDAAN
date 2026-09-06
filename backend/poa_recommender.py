"""
poa_recommender.py
==================
NIDAAN - SC/ST (Prevention of Atrocities) Act Action Mapper.

Maps the fused SVI Risk Tier to statutory administrative actions under the
Scheduled Castes and the Scheduled Tribes (Prevention of Atrocities) Act,
1989, as amended in 2015.

Tier Action Mapping
-------------------
LOW (0-30):
    - Auto-docketing of complaint, routine inquiry status SMS.
    - No immediate escalation.

MODERATE (31-60):
    - Priority callback by welfare officer within 24h.
    - Scheduled follow-up review.

HIGH (61-80):
    - Route to senior counselor / trauma specialist.
    - Trigger tele-medical assistance referral.
    - Escalate to DSP-level officer.

CRITICAL (81-100):
    - Auto-bypass call queue.
    - Immediate notification to District Police PCR.
    - Activate Witness Protection Cell under Sec 15A(1).
    - Emergency medical dispatch if required.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import config


@dataclass
class ActionStep:
    step: int
    action: str
    owner: str
    sla: str
    channel: str
    statute: Optional[str] = None  # explicit SC/ST (PoA) Act, 1989 clause anchor


@dataclass
class ActionPlan:
    risk_tier: str
    priority: str
    poa_sections: List[str]
    steps: List[ActionStep]
    escalation_contacts: List[str] = field(default_factory=list)
    legal_framework: str = (
        "Scheduled Castes and the Scheduled Tribes "
        "(Prevention of Atrocities) Act, 1989 (as amended 2015)"
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "risk_tier": self.risk_tier,
            "priority": self.priority,
            "legal_framework": self.legal_framework,
            "poa_sections": self.poa_sections,
            "escalation_contacts": self.escalation_contacts,
            "steps": [
                {
                    "step": s.step,
                    "action": s.action,
                    "owner": s.owner,
                    "sla": s.sla,
                    "channel": s.channel,
                    "statute": s.statute,
                }
                for s in self.steps
            ],
        }


class POARecommender:
    """
    Statutory action mapper keyed on risk tier. The recommend_actions method
    accepts either a SVI score (float) or a risk category string and returns
    the full action plan.
    """

    PLANS: Dict[str, ActionPlan] = {
        "LOW": ActionPlan(
            risk_tier="LOW",
            priority="ROUTINE",
            poa_sections=["Sec 3(2)(i)", "Sec 21(2)"],
            steps=[
                ActionStep(1, "Auto-docket complaint in NHAA case management system", "NHAA Docket Desk", "Immediate", "Internal", "PoA Act 1989 · Sec 3(2)(i)"),
                ActionStep(2, "Send routine inquiry status SMS to complainant", "Automated Messaging", "Within 2 hours", "SMS 14566", "PoA Act 1989 · Sec 21(2)"),
            ],
            escalation_contacts=["NHAA Operator Desk", "District Welfare Officer (routine course)"],
        ),
        "MODERATE": ActionPlan(
            risk_tier="MODERATE",
            priority="PRIORITY",
            poa_sections=["Sec 3(1)(r)", "Sec 18A", "Sec 22"],
            steps=[
                ActionStep(1, "Priority callback by District Welfare Officer", "District Welfare Officer", "Within 24 hours", "Phone 14566", "PoA Act 1989 · Sec 3(1)(r)"),
                ActionStep(2, "Schedule structured 48-hour safety recheck", "Welfare Office", "48 hours", "Automated reminder", "PoA Act 1989 · Sec 18A"),
                ActionStep(3, "Document preliminary First Information Report guidance", "Legal Aid Cell", "Within 24 hours", "Document", "PoA Act 1989 · Sec 18A / Sec 22"),
            ],
            escalation_contacts=["District Welfare Officer", "District Legal Service Authority (DLSA)"],
        ),
        "HIGH": ActionPlan(
            risk_tier="HIGH",
            priority="HIGH",
            poa_sections=["Sec 3(2)(v)", "Sec 4", "Sec 6", "Sec 8"],
            steps=[
                ActionStep(1, "Route call to senior counselor / trauma specialist", "Senior Counselor", "Immediate", "Live transfer", "PoA Act 1989 · Sec 3(2)(v)"),
                ActionStep(2, "Trigger tele-medical assistance referral", "Tele-Medicine Desk", "Within 15 minutes", "Referral form + call", "PoA Act 1989 · Sec 4"),
                ActionStep(3, "Escalate to DSP-level officer with case summary", "Deputy SP (Crime/SC-ST)", "Within 30 minutes", "High-priority ticket", "PoA Act 1989 · Sec 6 / Sec 3(2)(v)"),
                ActionStep(4, "Offer temporary protective accommodation options", "Protection Officer", "Within 2 hours", "Case conference", "PoA Act 1989 · Sec 8"),
            ],
            escalation_contacts=["DSP (SC-ST Cell)", "Senior Counselor", "District Hospital Telemedicine Unit"],
        ),
        "CRITICAL": ActionPlan(
            risk_tier="CRITICAL",
            priority="EMERGENCY",
            poa_sections=["Sec 3(2)(v)", "Sec 15A(1)", "Sec 15A(2)", "Sec 21(2)"],
            steps=[
                ActionStep(1, "Auto-bypass call queue (emergency transfer)", "Switchboard Bot", "Immediate", "Live transfer", "PoA Act 1989 · Sec 3(2)(v)"),
                ActionStep(2, "Notify District Police PCR (armed response assessment)", "District Police PCR", "Within 1 minute", "Emergency notification", "PoA Act 1989 · Sec 21(2)"),
                ActionStep(3, "Activate Witness Protection Cell under Sec 15A(1)", "Witness Protection Cell", "Within 5 minutes", "Secure channel", "PoA Act 1989 · Sec 15A(1) — Witness Protection"),
                ActionStep(4, "Send victim location / details to nearest police station", "NHAA Operations", "Within 5 minutes", "Encrypted dispatch", "PoA Act 1989 · Sec 15A(1) / Sec 21(2)"),
                ActionStep(5, "Request emergency medical / ambulance dispatch if life-threatened", "Tele-Medicine / 108", "Within 10 minutes", "Ambulance dispatch", "PoA Act 1989 · Sec 21(2)"),
                ActionStep(6, "Open trauma-informed care session for immediate stabilization", "On-call Psychologist", "Immediate", "Live session", "PoA Act 1989 · Sec 15A(1)"),
            ],
            escalation_contacts=[
                "District Police PCR (Emergency)",
                "Witness Protection Cell (Sec 15A)",
                "Special Officer for SC/ST",
                "Tele-Medicine Emergency Desk (108)",
            ],
        ),
    }

    DEFAULT_CONTACTS = [
        "NHAA National Helpline 14566",
        "District Special Officer (SC/ST)",
    ]

    def recommend_for_score(self, svi_score: float) -> ActionPlan:
        tier = self._tier_for_score(svi_score)
        return self.recommend_for_tier(tier)

    def recommend_for_tier(self, risk_tier: str) -> ActionPlan:
        key = risk_tier.upper().strip()
        if key not in self.PLANS:
            key = "LOW"
        return self.PLANS[key]

    def recommend_actions(self, risk_tier_or_score) -> Dict[str, Any]:
        if isinstance(risk_tier_or_score, (int, float)):
            plan = self.recommend_for_score(float(risk_tier_or_score))
        else:
            plan = self.recommend_for_tier(str(risk_tier_or_score))
        return plan.to_dict()

    @staticmethod
    def _tier_for_score(score: float) -> str:
        score = max(0.0, min(100.0, float(score)))
        if score <= 30:
            return "LOW"
        if score <= 60:
            return "MODERATE"
        if score <= 80:
            return "HIGH"
        return "CRITICAL"

    def all_plans(self) -> Dict[str, Any]:
        return {tier: plan.to_dict() for tier, plan in self.PLANS.items()}


recommender = POARecommender()
