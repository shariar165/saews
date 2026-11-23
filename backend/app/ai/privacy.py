"""The only gateway from SAEWS data to the AI model (data minimization, SRS §6.2).

Context builders return plain JSON-able dicts that contain academic indicators only. They never include the
student's name, student code, email, guardian details or the evaluation-only ``equity_group``. Free text written
by staff or students (plan descriptions, notes, goals) is scrubbed of the student's name, code, emails and phone
numbers before it is sent. Messages that need the student's name use the placeholder ``{student}``, which the
server fills in after the AI has answered, so the name never leaves SAEWS.
"""

from __future__ import annotations

import re
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Course, Enrollment, Recommendation, RiskAssessment, Student, StudyGoal, SupportPlan
from ..services.indicators import student_series

STUDENT_PLACEHOLDER = "{student}"
SENDER_PLACEHOLDER = "{sender}"
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
_PHONE = re.compile(r"(\+?88)?0?1[3-9]\d{8}\b|\b\d{3}[-\s]?\d{3,4}[-\s]?\d{4}\b")


def scrub(text: str | None, student: Student) -> str | None:
    """Remove direct identifiers from free text before it is sent to the AI model."""
    if not text:
        return text
    out = _EMAIL.sub("[email]", text)
    out = _PHONE.sub("[phone]", out)
    if student.student_code:
        out = re.sub(re.escape(student.student_code), "the student", out, flags=re.IGNORECASE)
    name = (student.full_name or "").strip()
    if name:
        out = re.sub(re.escape(name), "the student", out, flags=re.IGNORECASE)
        for part in sorted(set(name.split()), key=len, reverse=True):
            if len(part) >= 3:
                out = re.sub(rf"\b{re.escape(part)}\b", "the student", out, flags=re.IGNORECASE)
    return out


def _courses(db: Session, student: Student) -> list[dict]:
    rows = db.execute(select(Course.code, Course.title).join(Enrollment)
                      .where(Enrollment.student_id == student.id).order_by(Course.code)).all()
    return [{"code": c, "subject": t} for c, t in rows]


def _profile(db: Session, student: Student) -> dict:
    return {
        "program": student.program,
        "class": student.year_of_study,
        "previous_exam_gpa_out_of_5": student.prior_gpa,
        "subjects": _courses(db, student),
    }


def _indicator_summary(db: Session, student: Student, recent_weeks: int = 8) -> dict:
    series = student_series(db, student.id)
    scores_by_course: dict[str, list] = {}
    for sc in series["scores"]:
        scores_by_course.setdefault(sc["course"], []).append({"assessment": sc["name"], "week": sc["week"],
                                                              "percent": sc["pct"]})
    return {
        "weekly_attendance_rate": [{"week": a["week"], "rate": a["rate"]} for a in series["attendance"][-recent_weeks:]],
        "weekly_portal_logins_per_subject": [{"week": e["week"], "logins": e["logins"]}
                                             for e in series["engagement"][-recent_weeks:]],
        "scores_by_subject": scores_by_course,
        "homework_counts": series["assignments"],
    }


def case_context(db: Session, student: Student, ra: RiskAssessment) -> dict:
    """F1: everything staff already see on the profile page, minus identifiers."""
    plans = db.scalars(select(SupportPlan).where(SupportPlan.student_id == student.id,
                                                 SupportPlan.status.in_(["planned", "in_progress"])))
    return {
        "student_profile": _profile(db, student),
        "risk_assessment": {
            "risk_level": ra.risk_level,
            "estimated_probability": None if ra.probability is None else round(ra.probability, 2),
            "method": ra.method,
            "reliable": ra.reliable,
            "data_completeness": ra.completeness,
            "data_age_days": ra.data_age_days,
            "missing_data": ra.missing_fields,
            "data_quality_warnings": ra.warnings,
            "contributing_factors": [{"factor": f.get("label"), "weight": f.get("contribution")} for f in ra.factors or []],
            "feature_values": ra.features,
        },
        "indicators": _indicator_summary(db, student),
        "open_support_plans": [{"title": scrub(p.title, student), "status": p.status} for p in plans],
    }


def recommendations_context(db: Session, student: Student, ra: RiskAssessment | None,
                            recs: list[Recommendation]) -> dict:
    """F2: the proposed catalogue items plus the facts that triggered them."""
    return {
        "student_profile": _profile(db, student),
        "risk_level": ra.risk_level if ra else None,
        "contributing_factors": [f.get("label") for f in (ra.factors if ra else None) or []],
        "data_quality_warnings": ra.warnings if ra else [],
        "indicators": _indicator_summary(db, student),
        "proposed_actions": [{"id": r.id, "title": r.title, "current_text": scrub(r.rationale, student)} for r in recs],
    }


def _snapshot_view(snap: dict | None) -> dict | None:
    if not snap:
        return None
    keep = ("attendance_rate", "avg_score", "missing_rate", "late_rate", "avg_logins", "engagement_change", "data_as_of")
    return {k: snap.get(k) for k in keep if k in snap}


def plan_context(db: Session, plan: SupportPlan, *, include_interventions: bool = True) -> dict:
    """F3/F4: one support plan with its interventions and before/after indicator snapshots."""
    student = plan.student
    d = {
        "student_profile": _profile(db, student),
        "plan": {
            "title": scrub(plan.title, student),
            "description": scrub(plan.description, student),
            "status": plan.status,
            "due_date": plan.due_date.isoformat() if plan.due_date else None,
            "owner_role": plan.owner.role if plan.owner else None,
        },
    }
    if include_interventions:
        d["interventions"] = [{
            "action": iv.action_type,
            "status": iv.status,
            "date": iv.performed_at.date().isoformat() if iv.performed_at else None,
            "notes": scrub(iv.notes, student),
            "outcome": scrub(iv.outcome, student),
            "indicators_before": _snapshot_view(iv.baseline_snapshot),
            "indicators_after": _snapshot_view(iv.followup_snapshot),
        } for iv in plan.interventions]
    return d


def goal_context(db: Session, student: Student, goal: StudyGoal) -> dict:
    """F5: the student's own goal, subjects, own indicators and *approved* support only (no risk labels)."""
    approved = db.scalars(select(Recommendation).where(Recommendation.student_id == student.id,
                                                       Recommendation.status == "approved"))
    return {
        "today": date.today().isoformat(),
        "goal": {"title": scrub(goal.title, student),
                 "target_date": goal.target_date.isoformat() if goal.target_date else None},
        "student_profile": _profile(db, student),
        "my_indicators": _indicator_summary(db, student, recent_weeks=6),
        "support_already_agreed_with_school": [r.title for r in approved],
        "has_class_advisor": student.advisor_id is not None,
    }


def fill_placeholders(text: str, *, student_name: str, sender_name: str | None) -> str:
    out = text.replace(STUDENT_PLACEHOLDER, student_name)
    return out.replace(SENDER_PLACEHOLDER, sender_name or "")
