"""Alert queue, risk summary, and human review of alerts (FR5)."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select, true
from sqlalchemy.orm import Session, selectinload

from ..core.audit import audit
from ..core.deps import get_student_for_user, staff_only, visible_student_ids_query
from ..database import get_db
from ..models import RiskAssessment, Student, StudentRequest, SupportPlan, User
from .serializers import assessment_out, iso, student_out

router = APIRouter(prefix="/risk", tags=["risk"])

ALERT_LEVELS = ["critical", "high", "moderate", "insufficient_data", "unavailable"]
LEVEL_SORT = {lvl: i for i, lvl in enumerate(ALERT_LEVELS)}


def _scoped(q, user: User, col):
    scope = visible_student_ids_query(user)
    return q if scope is None else q.where(col.in_(scope))


@router.get("/alerts")
def alerts(
    request: Request,
    level: str | None = None,
    review_status: str | None = None,
    method: str | None = None,
    limit: int = 500,
    user: User = Depends(staff_only),
    db: Session = Depends(get_db),
):
    q = (select(RiskAssessment, Student).join(Student, Student.id == RiskAssessment.student_id)
         .where(RiskAssessment.is_current.is_(True), RiskAssessment.risk_level.in_(ALERT_LEVELS))
         .options(selectinload(Student.advisor)))
    q = _scoped(q, user, RiskAssessment.student_id)
    if level:
        q = q.where(RiskAssessment.risk_level == level)
    if review_status:
        q = q.where(RiskAssessment.review_status == review_status)
    if method:
        q = q.where(RiskAssessment.method == method)
    rows = db.execute(q).all()
    items = [student_out(s, ra) for ra, s in rows]
    items.sort(key=lambda d: (LEVEL_SORT.get(d["assessment"]["risk_level"], 9), -(d["assessment"]["probability"] or 0)))
    audit(db, "risk.alerts.view", user=user, request=request, detail={"count": len(items)})
    return {"items": items[: max(1, min(limit, 2000))]}


@router.get("/summary")
def summary(user: User = Depends(staff_only), db: Session = Depends(get_db)):
    q = _scoped(select(RiskAssessment.risk_level, func.count()).where(RiskAssessment.is_current.is_(True))
                .group_by(RiskAssessment.risk_level), user, RiskAssessment.student_id)
    levels = dict(db.execute(q).all())
    unreviewed = db.scalar(_scoped(select(func.count()).select_from(RiskAssessment).where(
        RiskAssessment.is_current.is_(True), RiskAssessment.review_status == "unreviewed",
        RiskAssessment.risk_level.in_(["high", "critical"])), user, RiskAssessment.student_id))
    fallback = db.scalar(_scoped(select(func.count()).select_from(RiskAssessment).where(
        RiskAssessment.is_current.is_(True), RiskAssessment.method == "rules_fallback"), user, RiskAssessment.student_id))
    open_plans = db.scalar(_scoped(select(func.count()).select_from(SupportPlan).where(
        SupportPlan.status.in_(["planned", "in_progress"])), user, SupportPlan.student_id))
    open_requests = db.scalar(select(func.count()).select_from(StudentRequest).where(
        StudentRequest.status.in_(["open", "in_review"]),
        (StudentRequest.assigned_to == user.id) if user.role != "admin" else true()))
    last = db.scalar(_scoped(select(func.max(RiskAssessment.created_at)), user, RiskAssessment.student_id))
    return {
        "students": sum(levels.values()),
        "levels": {k: levels.get(k, 0) for k in ["low", "moderate", "high", "critical", "insufficient_data", "unavailable"]},
        "unreviewed_high": unreviewed or 0,
        "fallback_count": fallback or 0,
        "open_plans": open_plans or 0,
        "open_requests": open_requests or 0,
        "last_assessed_at": iso(last),
    }


class ReviewIn(BaseModel):
    note: str | None = Field(None, max_length=2000)


class FlagIn(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)
    data_issue: bool = False


def _load(db: Session, user: User, assessment_id: int, request: Request, action: str) -> RiskAssessment:
    ra = db.get(RiskAssessment, assessment_id)
    if ra is None:
        raise HTTPException(404, "Assessment not found")
    get_student_for_user(db, user, ra.student_id, request, action)
    return ra


@router.post("/{assessment_id}/review")
def review(assessment_id: int, body: ReviewIn, request: Request, user: User = Depends(staff_only),
           db: Session = Depends(get_db)):
    ra = _load(db, user, assessment_id, request, "risk.review")
    ra.review_status, ra.review_note = "reviewed", body.note
    ra.reviewed_by, ra.reviewed_at = user.id, datetime.now(UTC)
    audit(db, "risk.review", user=user, request=request, target_type="risk_assessment", target_id=ra.id)
    return assessment_out(ra)


@router.post("/{assessment_id}/flag")
def flag(assessment_id: int, body: FlagIn, request: Request, user: User = Depends(staff_only),
         db: Session = Depends(get_db)):
    """Flag an alert as inappropriate or based on incorrect data. Data issues open a correction request."""
    ra = _load(db, user, assessment_id, request, "risk.flag")
    ra.review_status, ra.review_note = "flagged", body.reason
    ra.reviewed_by, ra.reviewed_at = user.id, datetime.now(UTC)
    if body.data_issue:
        db.add(StudentRequest(student_id=ra.student_id, kind="correction", subject="Staff-reported data issue",
                              details=body.reason, target_record=f"risk_assessment:{ra.id}", status="open",
                              assigned_to=user.id, created_by=user.id))
    audit(db, "risk.flag", user=user, request=request, target_type="risk_assessment", target_id=ra.id,
          detail={"data_issue": body.data_issue})
    return assessment_out(ra)
