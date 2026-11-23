"""Personalized, non-punitive support recommendations (FR6).

A rules-based catalogue maps reason codes to supportive actions; candidates are ranked
by the strength of the contributing factors. Every recommendation starts as "proposed"
and must be approved, edited or dismissed by authorized staff before a student sees it.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Recommendation, RecommendationCatalog, RiskAssessment

LEVEL_RANK = {"low": 0, "moderate": 1, "high": 2, "critical": 3}

DEFAULT_CATALOG = [
    {"code": "ATTENDANCE_FOLLOWUP", "category": "attendance", "trigger_codes": ["LOW_ATTENDANCE"], "min_level": "moderate",
     "title": "Supportive attendance follow-up",
     "description": "Reach out privately to understand barriers to attending (class routine, travel, health, family responsibilities) and agree a realistic attendance plan."},
    {"code": "TUTORING", "category": "academic", "trigger_codes": ["LOW_SCORES"], "min_level": "moderate",
     "title": "Remedial classes or peer tutoring",
     "description": "Offer teacher-led remedial classes or peer tutoring focused on the topics behind recent low class-test and exam marks."},
    {"code": "STUDY_PLAN", "category": "academic", "trigger_codes": ["MISSING_WORK", "LOW_SCORES"], "min_level": "moderate",
     "title": "Structured weekly study plan",
     "description": "Co-create a weekly study plan with milestones for upcoming class tests, exams and homework."},
    {"code": "DEADLINE_SUPPORT", "category": "academic", "trigger_codes": ["MISSING_WORK"], "min_level": "moderate",
     "title": "Homework catch-up and deadline planning",
     "description": "Review missing or late homework, prioritize what can still be submitted, and discuss any extensions allowed under school/college policy."},
    {"code": "ENGAGEMENT_CHECKIN", "category": "engagement", "trigger_codes": ["LOW_ENGAGEMENT"], "min_level": "moderate",
     "title": "Online learning portal check-in",
     "description": "Check whether the student can access the online learning portal and subject materials (device, connectivity, accessibility needs) and point them to key resources."},
    {"code": "ADVISOR_MEETING", "category": "advising", "trigger_codes": ["*"], "min_level": "high",
     "title": "Class advisor check-in meeting",
     "description": "Schedule a supportive one-to-one meeting with the class advisor to review progress and options, involving the guardian where appropriate."},
    {"code": "WELLBEING_INFO", "category": "wellbeing", "trigger_codes": ["*"], "min_level": "critical",
     "title": "Share student support information",
     "description": "Offer information about the school counsellor, stipend/financial support and wellbeing services. Do not assume a cause — let the student decide whether to use them."},
]


def ensure_catalog(db: Session) -> None:
    existing = set(db.scalars(select(RecommendationCatalog.code)))
    for item in DEFAULT_CATALOG:
        if item["code"] not in existing:
            db.add(RecommendationCatalog(**item))
    db.flush()


def propose_for_assessment(db: Session, ra: RiskAssessment, limit: int = 3) -> list[Recommendation]:
    level = LEVEL_RANK.get(ra.risk_level)
    if level is None or level < LEVEL_RANK["moderate"]:
        return []
    weights: dict[str, float] = {}
    labels: dict[str, list[str]] = {}
    for f in ra.factors or []:
        weights[f["code"]] = weights.get(f["code"], 0.0) + float(f.get("contribution") or 0)
        labels.setdefault(f["code"], []).append(f["label"])

    # Skip actions that are already proposed or approved for this student.
    open_codes = set(db.scalars(select(Recommendation.catalog_code).where(
        Recommendation.student_id == ra.student_id, Recommendation.status.in_(["proposed", "approved"]))))

    candidates = []
    for item in db.scalars(select(RecommendationCatalog).where(RecommendationCatalog.active.is_(True))):
        if LEVEL_RANK.get(item.min_level, 1) > level or item.code in open_codes:
            continue
        if "*" in item.trigger_codes:
            score = 0.5 + level * 0.1
            reasons = [f"Overall risk level is {ra.risk_level}."]
        else:
            matched = [c for c in item.trigger_codes if c in weights]
            if not matched:
                continue
            score = sum(weights[c] for c in matched)
            reasons = [lbl for c in matched for lbl in labels[c]]
        candidates.append((score, item, reasons))

    # Up to `limit` need-specific actions, plus any level-based actions (advisor meeting, support info).
    specific = sorted((c for c in candidates if "*" not in c[1].trigger_codes), key=lambda t: t[0], reverse=True)
    general = [c for c in candidates if "*" in c[1].trigger_codes]
    created = []
    for score, item, reasons in specific[:limit] + general:
        rec = Recommendation(student_id=ra.student_id, assessment_id=ra.id, catalog_code=item.code, title=item.title,
                             rationale=item.description + " Why suggested: " + " ".join(reasons), score=round(score, 3))
        db.add(rec)
        created.append(rec)
    return created
