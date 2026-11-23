"""Generative-AI assistant endpoints. Every route reuses the normal role and per-record checks, so the AI can
never see more than the signed-in user can. All output is a labelled draft; nothing is applied automatically
except that personalized suggestion text replaces the template text of still-*proposed* suggestions, which
staff must still approve, edit or dismiss."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai import service
from ..ai.client import AIUnavailable, is_enabled
from ..config import get_settings
from ..core.deps import get_current_user, get_student_for_user, my_student, require_roles, staff_only
from ..core.ratelimit import limiter
from ..database import get_db
from ..models import Recommendation, RiskAssessment, Role, StudyGoal, SupportPlan, User
from .serializers import recommendation_out

router = APIRouter(prefix="/ai", tags=["AI assistant"])
student_only = require_roles(Role.STUDENT)
_limit = limiter.shared_limit(get_settings().ai_rate_limit, scope="ai")  # one budget across all AI routes


def _unavailable(e: AIUnavailable) -> HTTPException:
    return HTTPException(503, str(e))


def _require_enabled() -> None:
    if not is_enabled():
        raise HTTPException(503, "The AI assistant is not enabled on this server.")


@router.get("/status")
def status(user: User = Depends(get_current_user)):
    enabled = is_enabled()
    features = {
        Role.STUDENT: ["goal_plan"],
        Role.ANALYST: [],
    }.get(user.role, ["case_summary", "rec_personalize", "outcome_note", "support_message"])
    return {"enabled": enabled, "model": get_settings().ai_model if enabled else None,
            "features": features if enabled else [], "label": service.AI_LABEL}


# F1 ---------------------------------------------------------------------------------------------
def _current_assessment(db: Session, student_id: int) -> RiskAssessment | None:
    return db.scalar(select(RiskAssessment).where(RiskAssessment.student_id == student_id,
                                                  RiskAssessment.is_current.is_(True)))


@router.get("/students/{student_id}/case-summary")
def get_case_summary(student_id: int, request: Request, user: User = Depends(staff_only),
                     db: Session = Depends(get_db)):
    """The stored summary for the *current* assessment, if one was generated. Never calls the AI."""
    st = get_student_for_user(db, user, student_id, request, "ai.case_summary")
    ra = _current_assessment(db, st.id)
    item = service.latest(db, "case_summary", "assessment", ra.id) if ra else None
    return {"item": service.output_out(item)}


@router.post("/students/{student_id}/case-summary")
@_limit
def create_case_summary(student_id: int, request: Request, refresh: bool = False, user: User = Depends(staff_only),
                        db: Session = Depends(get_db)):
    st = get_student_for_user(db, user, student_id, request, "ai.case_summary")
    _require_enabled()
    ra = _current_assessment(db, st.id)
    if ra is None or ra.risk_level in ("insufficient_data", "unavailable"):
        raise HTTPException(409, "There is no usable risk assessment to summarize for this student.")
    if not refresh and (cached := service.latest(db, "case_summary", "assessment", ra.id)):
        return {"item": service.output_out(cached), "cached": True}
    try:
        row = service.case_summary(db, user, request, st, ra)
    except AIUnavailable as e:
        raise _unavailable(e) from e
    return {"item": service.output_out(row), "cached": False}


# F2 ---------------------------------------------------------------------------------------------
@router.post("/students/{student_id}/recommendations/personalize")
@_limit
def personalize(student_id: int, request: Request, user: User = Depends(staff_only), db: Session = Depends(get_db)):
    """Rewrite the template text of this student's *proposed* suggestions for this student's situation."""
    st = get_student_for_user(db, user, student_id, request, "ai.rec_personalize")
    _require_enabled()
    recs = list(db.scalars(select(Recommendation).where(Recommendation.student_id == st.id,
                                                        Recommendation.status == "proposed",
                                                        Recommendation.ai_drafted.is_(False))
                           .order_by(Recommendation.id)))
    if not recs:
        raise HTTPException(409, "There are no new proposed suggestions to personalize.")
    try:
        updated = service.personalize_recommendations(db, user, request, st, _current_assessment(db, st.id), recs)
    except AIUnavailable as e:
        raise _unavailable(e) from e
    return {"items": [recommendation_out(r) for r in updated]}


# F3 / F4 ----------------------------------------------------------------------------------------
def _plan(db: Session, user: User, plan_id: int, request: Request, action: str) -> SupportPlan:
    plan = db.get(SupportPlan, plan_id)
    if plan is None:
        raise HTTPException(404, "Support plan not found")
    get_student_for_user(db, user, plan.student_id, request, action)
    return plan


@router.post("/plans/{plan_id}/outcome-note")
@_limit
def outcome_note(plan_id: int, request: Request, user: User = Depends(staff_only), db: Session = Depends(get_db)):
    plan = _plan(db, user, plan_id, request, "ai.outcome_note")
    _require_enabled()
    if not plan.interventions:
        raise HTTPException(409, "Record at least one intervention before drafting an outcome note.")
    try:
        row = service.outcome_note(db, user, request, plan)
    except AIUnavailable as e:
        raise _unavailable(e) from e
    return {"item": service.output_out(row)}


class MessageIn(BaseModel):
    audience: Literal["guardian", "student"] = "guardian"
    language: Literal["bn", "en"] = "bn"


@router.post("/plans/{plan_id}/message")
@_limit
def support_message(plan_id: int, body: MessageIn, request: Request, user: User = Depends(staff_only),
                    db: Session = Depends(get_db)):
    """Draft a message about an agreed support plan, for staff to copy and send themselves."""
    plan = _plan(db, user, plan_id, request, "ai.support_message")
    _require_enabled()
    if plan.status == "cancelled":
        raise HTTPException(409, "This support plan was cancelled.")
    try:
        row = service.support_message(db, user, request, plan, audience=body.audience, language=body.language)
    except AIUnavailable as e:
        raise _unavailable(e) from e
    return {"item": service.output_out(row, data=service.filled_message(row, student=plan.student, sender=user))}


# F5 ---------------------------------------------------------------------------------------------
class GoalPlanIn(BaseModel):
    language: Literal["bn", "en"] = "en"
    refresh: bool = False


@router.post("/me/goals/{goal_id}/plan")
@_limit
def goal_plan(goal_id: int, body: GoalPlanIn, request: Request, user: User = Depends(student_only),
              db: Session = Depends(get_db)):
    st = my_student(db, user)
    goal = db.get(StudyGoal, goal_id)
    if goal is None or goal.student_id != st.id:
        raise HTTPException(404, "Goal not found")
    _require_enabled()
    if not body.refresh and (cached := service.latest(db, "goal_plan", "goal", goal.id, body.language)):
        return {"item": service.output_out(cached), "cached": True}
    try:
        row = service.goal_plan(db, user, request, st, goal, language=body.language)
    except AIUnavailable as e:
        raise _unavailable(e) from e
    return {"item": service.output_out(row), "cached": False}
