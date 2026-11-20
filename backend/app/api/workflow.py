"""Human-in-the-loop support workflow: recommendations, support plans, interventions,
and the staff inbox for student help/correction requests (FR6, FR7, FR8)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..core.audit import audit
from ..core.deps import get_student_for_user, staff_only, visible_student_ids_query
from ..database import get_db
from ..models import Intervention, Recommendation, Role, StudentRequest, SupportPlan, User
from ..services.indicators import snapshot
from .serializers import plan_out, recommendation_out, request_out

router = APIRouter(tags=["workflow"])


def _now():
    return datetime.now(UTC)


def _valid_owner(db: Session, owner_id: int | None, default: User) -> int:
    if owner_id is None:
        return default.id
    owner = db.get(User, owner_id)
    if owner is None or not owner.is_active or owner.role not in (Role.TEACHER, Role.ADVISOR, Role.ADMIN):
        raise HTTPException(422, "Plan owner must be an active staff member")
    return owner.id


# ------------------------------------------------------------------ recommendations
class ApproveIn(BaseModel):
    edited_text: str | None = Field(None, max_length=4000)
    note: str | None = Field(None, max_length=2000)
    owner_id: int | None = None
    due_date: date | None = None


class DismissIn(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)


def _load_rec(db: Session, user: User, rec_id: int, request: Request, action: str) -> Recommendation:
    rec = db.get(Recommendation, rec_id)
    if rec is None:
        raise HTTPException(404, "Recommendation not found")
    get_student_for_user(db, user, rec.student_id, request, action)
    if rec.status != "proposed":
        raise HTTPException(409, f"Recommendation has already been {rec.status}")
    return rec


@router.post("/recommendations/{rec_id}/approve")
def approve(rec_id: int, body: ApproveIn, request: Request, user: User = Depends(staff_only),
            db: Session = Depends(get_db)):
    """Approve (optionally edit) a recommendation; this creates a support plan with owner and due date (AT-06)."""
    rec = _load_rec(db, user, rec_id, request, "recommendation.approve")
    rec.status, rec.review_note = "approved", body.note
    if body.edited_text and body.edited_text.strip() != rec.rationale:
        rec.edited_text = body.edited_text.strip()
    rec.reviewed_by, rec.reviewed_at = user.id, _now()
    plan = SupportPlan(student_id=rec.student_id, recommendation_id=rec.id, title=rec.title,
                       description=rec.edited_text or rec.rationale, owner_id=_valid_owner(db, body.owner_id, user),
                       due_date=body.due_date or (date.today() + timedelta(days=14)), status="planned",
                       created_by=user.id)
    db.add(plan)
    db.flush()
    audit(db, "recommendation.approve", user=user, request=request, target_type="recommendation", target_id=rec.id,
          detail={"plan_id": plan.id, "edited": bool(rec.edited_text)})
    db.refresh(plan)
    return {"recommendation": recommendation_out(rec), "plan": plan_out(plan)}


@router.post("/recommendations/{rec_id}/dismiss")
def dismiss(rec_id: int, body: DismissIn, request: Request, user: User = Depends(staff_only),
            db: Session = Depends(get_db)):
    rec = _load_rec(db, user, rec_id, request, "recommendation.dismiss")
    rec.status, rec.review_note = "dismissed", body.reason
    rec.reviewed_by, rec.reviewed_at = user.id, _now()
    audit(db, "recommendation.dismiss", user=user, request=request, target_type="recommendation", target_id=rec.id)
    return recommendation_out(rec)


# ------------------------------------------------------------------ plans
class PlanIn(BaseModel):
    student_id: int
    title: str = Field(min_length=3, max_length=200)
    description: str | None = Field(None, max_length=4000)
    owner_id: int | None = None
    due_date: date | None = None


class PlanPatch(BaseModel):
    status: Literal["planned", "in_progress", "completed", "cancelled"] | None = None
    due_date: date | None = None
    owner_id: int | None = None
    description: str | None = Field(None, max_length=4000)


@router.get("/plans")
def list_plans(status: str | None = None, mine: bool = False, user: User = Depends(staff_only),
               db: Session = Depends(get_db)):
    q = (select(SupportPlan).options(selectinload(SupportPlan.interventions), selectinload(SupportPlan.owner),
                                     selectinload(SupportPlan.student))
         .order_by(SupportPlan.due_date.asc().nulls_last()))
    scope = visible_student_ids_query(user)
    if scope is not None:
        q = q.where(SupportPlan.student_id.in_(scope))
    if status:
        q = q.where(SupportPlan.status == status)
    if mine:
        q = q.where(SupportPlan.owner_id == user.id)
    return {"items": [plan_out(p, include_student=True) for p in db.scalars(q)]}


@router.post("/plans", status_code=201)
def create_plan(body: PlanIn, request: Request, user: User = Depends(staff_only), db: Session = Depends(get_db)):
    get_student_for_user(db, user, body.student_id, request, "plan.create")
    plan = SupportPlan(student_id=body.student_id, title=body.title, description=body.description,
                       owner_id=_valid_owner(db, body.owner_id, user),
                       due_date=body.due_date or (date.today() + timedelta(days=14)), created_by=user.id)
    db.add(plan)
    db.flush()
    audit(db, "plan.create", user=user, request=request, target_type="support_plan", target_id=plan.id)
    db.refresh(plan)
    return plan_out(plan)


def _load_plan(db: Session, user: User, plan_id: int, request: Request, action: str) -> SupportPlan:
    plan = db.get(SupportPlan, plan_id)
    if plan is None:
        raise HTTPException(404, "Support plan not found")
    get_student_for_user(db, user, plan.student_id, request, action)
    return plan


@router.patch("/plans/{plan_id}")
def update_plan(plan_id: int, body: PlanPatch, request: Request, user: User = Depends(staff_only),
                db: Session = Depends(get_db)):
    plan = _load_plan(db, user, plan_id, request, "plan.update")
    changes = body.model_dump(exclude_unset=True)
    if "owner_id" in changes:
        changes["owner_id"] = _valid_owner(db, changes["owner_id"], user)
    for k, v in changes.items():
        setattr(plan, k, v)
    audit(db, "plan.update", user=user, request=request, target_type="support_plan", target_id=plan.id,
          detail={k: str(v) for k, v in changes.items()})
    db.refresh(plan)
    return plan_out(plan)


# ------------------------------------------------------------------ interventions
ACTION_TYPES = ["advisor_meeting", "tutoring_session", "study_plan_review", "attendance_followup",
                "email_or_message", "referral", "other"]


class InterventionIn(BaseModel):
    action_type: Literal["advisor_meeting", "tutoring_session", "study_plan_review", "attendance_followup",
                         "email_or_message", "referral", "other"]
    notes: str | None = Field(None, max_length=4000)
    status: Literal["scheduled", "done", "missed"] = "scheduled"
    performed_at: datetime | None = None


class InterventionPatch(BaseModel):
    status: Literal["scheduled", "done", "missed"] | None = None
    outcome: str | None = Field(None, max_length=4000)
    notes: str | None = Field(None, max_length=4000)
    capture_followup: bool = False


@router.post("/plans/{plan_id}/interventions", status_code=201)
def add_intervention(plan_id: int, body: InterventionIn, request: Request, user: User = Depends(staff_only),
                     db: Session = Depends(get_db)):
    plan = _load_plan(db, user, plan_id, request, "intervention.create")
    iv = Intervention(plan_id=plan.id, action_type=body.action_type, notes=body.notes, status=body.status,
                      performed_by=user.id, performed_at=body.performed_at or _now(),
                      baseline_snapshot=snapshot(db, plan.student_id))
    db.add(iv)
    if plan.status == "planned":
        plan.status = "in_progress"
    db.flush()
    audit(db, "intervention.create", user=user, request=request, target_type="intervention", target_id=iv.id)
    db.refresh(plan)
    return plan_out(plan)


@router.patch("/interventions/{iv_id}")
def update_intervention(iv_id: int, body: InterventionPatch, request: Request, user: User = Depends(staff_only),
                        db: Session = Depends(get_db)):
    iv = db.get(Intervention, iv_id)
    if iv is None:
        raise HTTPException(404, "Intervention not found")
    plan = _load_plan(db, user, iv.plan_id, request, "intervention.update")
    for k in ("status", "outcome", "notes"):
        v = getattr(body, k)
        if v is not None:
            setattr(iv, k, v)
    if body.capture_followup or body.outcome:
        iv.followup_snapshot = snapshot(db, plan.student_id)
    audit(db, "intervention.update", user=user, request=request, target_type="intervention", target_id=iv.id)
    db.refresh(plan)
    return plan_out(plan)


# ------------------------------------------------------------------ requests inbox
class RequestPatch(BaseModel):
    status: Literal["open", "in_review", "resolved", "rejected"]
    resolution: str | None = Field(None, max_length=4000)


@router.get("/requests")
def inbox(status: str | None = None, user: User = Depends(staff_only), db: Session = Depends(get_db)):
    q = (select(StudentRequest).options(selectinload(StudentRequest.student), selectinload(StudentRequest.assignee))
         .order_by(StudentRequest.created_at.desc()))
    if user.role != Role.ADMIN:
        q = q.where(StudentRequest.assigned_to == user.id)
    if status:
        q = q.where(StudentRequest.status == status)
    return {"items": [request_out(r) for r in db.scalars(q)]}


@router.patch("/requests/{req_id}")
def update_request(req_id: int, body: RequestPatch, request: Request, user: User = Depends(staff_only),
                   db: Session = Depends(get_db)):
    r = db.get(StudentRequest, req_id)
    if r is None:
        raise HTTPException(404, "Request not found")
    if user.role != Role.ADMIN and r.assigned_to != user.id:
        audit(db, "request.update", user=user, request=request, target_type="student_request", target_id=r.id,
              outcome="denied")
        raise HTTPException(403, "This request is assigned to another reviewer")
    if body.status in ("resolved", "rejected") and not (body.resolution and body.resolution.strip()):
        raise HTTPException(422, "Please record a resolution note when closing a request")
    r.status = body.status
    if body.resolution is not None:
        r.resolution = body.resolution
    r.resolved_at = _now() if body.status in ("resolved", "rejected") else None
    audit(db, "request.update", user=user, request=request, target_type="student_request", target_id=r.id,
          detail={"status": body.status})
    return request_out(r)
