"""Plain-dict serializers for API responses."""

from __future__ import annotations

from datetime import UTC, datetime

from ..models import Intervention, Recommendation, RiskAssessment, Student, StudentRequest, StudyGoal, SupportPlan, User

LEVEL_LABEL = {
    "low": "Low",
    "moderate": "Moderate",
    "high": "High",
    "critical": "Critical",
    "insufficient_data": "Insufficient data",
    "unavailable": "Unavailable",
}
METHOD_LABEL = {
    "model": "Predictive model",
    "rules_fallback": "Rule-based (fallback)",
    "none": "Not assessed",
    "unavailable": "Prediction unavailable",
}


def iso(v):
    """ISO-8601 string. Naive datetimes (SQLite drops tzinfo) are stored as UTC, so mark them as such."""
    if v is None:
        return None
    if isinstance(v, datetime) and v.tzinfo is None:
        v = v.replace(tzinfo=UTC)
    return v.isoformat()


_dt = iso


def user_out(u: User | None) -> dict | None:
    if u is None:
        return None
    return {"id": u.id, "email": u.email, "full_name": u.full_name, "role": u.role, "is_active": u.is_active,
            "identifiable_access": u.identifiable_access, "last_login_at": _dt(u.last_login_at)}


def user_brief(u: User | None) -> dict | None:
    return None if u is None else {"id": u.id, "full_name": u.full_name, "role": u.role}


def assessment_out(ra: RiskAssessment | None) -> dict | None:
    if ra is None:
        return None
    return {
        "id": ra.id,
        "student_id": ra.student_id,
        "created_at": _dt(ra.created_at),
        "is_current": ra.is_current,
        "risk_level": ra.risk_level,
        "risk_label": LEVEL_LABEL.get(ra.risk_level, ra.risk_level),
        "probability": ra.probability,
        "rule_points": ra.rule_points,
        "method": ra.method,
        "method_label": METHOD_LABEL.get(ra.method, ra.method),
        "model_version": ra.model_version,
        "reliable": ra.reliable,
        "data_as_of": _dt(ra.data_as_of),
        "data_age_days": ra.data_age_days,
        "completeness": ra.completeness,
        "missing_fields": ra.missing_fields,
        "warnings": ra.warnings,
        "factors": ra.factors,
        "features": ra.features,
        "review_status": ra.review_status,
        "review_note": ra.review_note,
        "reviewed_at": _dt(ra.reviewed_at),
    }


def student_out(s: Student, ra: RiskAssessment | None = None, *, include_assessment: bool = True) -> dict:
    d = {
        "id": s.id,
        "student_code": s.student_code,
        "full_name": s.full_name,
        "program": s.program,
        "year_of_study": s.year_of_study,
        "prior_gpa": s.prior_gpa,
        "advisor": user_brief(s.advisor),
    }
    if include_assessment:
        d["assessment"] = assessment_out(ra)
    return d


def recommendation_out(r: Recommendation) -> dict:
    return {"id": r.id, "student_id": r.student_id, "assessment_id": r.assessment_id, "code": r.catalog_code,
            "title": r.title, "rationale": r.rationale, "text": r.edited_text or r.rationale, "edited": bool(r.edited_text),
            "score": r.score, "status": r.status, "review_note": r.review_note, "reviewed_at": _dt(r.reviewed_at),
            "created_at": _dt(r.created_at)}


def intervention_out(i: Intervention) -> dict:
    return {"id": i.id, "plan_id": i.plan_id, "action_type": i.action_type, "notes": i.notes, "status": i.status,
            "outcome": i.outcome, "performed_by": user_brief(i.performer), "performed_at": _dt(i.performed_at),
            "baseline_snapshot": i.baseline_snapshot, "followup_snapshot": i.followup_snapshot}


def plan_out(p: SupportPlan, *, include_student: bool = False) -> dict:
    d = {"id": p.id, "student_id": p.student_id, "recommendation_id": p.recommendation_id, "title": p.title,
         "description": p.description, "owner": user_brief(p.owner), "due_date": _dt(p.due_date), "status": p.status,
         "created_at": _dt(p.created_at), "updated_at": _dt(p.updated_at),
         "interventions": [intervention_out(i) for i in p.interventions]}
    if include_student:
        d["student"] = {"id": p.student.id, "student_code": p.student.student_code, "full_name": p.student.full_name}
    return d


def request_out(r: StudentRequest, *, include_student: bool = True) -> dict:
    d = {"id": r.id, "student_id": r.student_id, "kind": r.kind, "subject": r.subject, "details": r.details,
         "target_record": r.target_record, "status": r.status, "assigned_to": user_brief(r.assignee),
         "resolution": r.resolution, "created_at": _dt(r.created_at), "resolved_at": _dt(r.resolved_at)}
    if include_student:
        d["student"] = {"id": r.student.id, "student_code": r.student.student_code, "full_name": r.student.full_name}
    return d


def goal_out(g: StudyGoal) -> dict:
    return {"id": g.id, "title": g.title, "target_date": _dt(g.target_date), "status": g.status,
            "created_at": _dt(g.created_at)}
