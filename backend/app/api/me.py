"""Student portal (FR3, FR6, FR8): own progress, approved support plan, study goals,
and help / correction requests. Students never see risk labels or unapproved recommendations."""

from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..core.audit import audit
from ..core.deps import my_student, require_roles
from ..database import get_db
from ..models import Course, Enrollment, Recommendation, Role, StudentRequest, StudyGoal, SupportPlan, User
from ..services.indicators import student_series
from .serializers import goal_out, iso, request_out, user_brief

router = APIRouter(prefix="/me", tags=["student portal"])
student_only = require_roles(Role.STUDENT)


@router.get("/profile")
def profile(user: User = Depends(student_only), db: Session = Depends(get_db)):
    st = my_student(db, user)
    courses = db.execute(select(Course.code, Course.title).join(Enrollment).where(Enrollment.student_id == st.id)).all()
    return {"student_code": st.student_code, "full_name": st.full_name, "program": st.program,
            "year_of_study": st.year_of_study, "advisor": user_brief(st.advisor),
            "courses": [{"code": c, "title": t} for c, t in courses]}


@router.get("/indicators")
def indicators(user: User = Depends(student_only), db: Session = Depends(get_db)):
    return student_series(db, my_student(db, user).id)


@router.get("/support")
def support(user: User = Depends(student_only), db: Session = Depends(get_db)):
    """Only staff-approved recommendations and their plans are visible to the student."""
    st = my_student(db, user)
    recs = db.scalars(select(Recommendation).where(Recommendation.student_id == st.id,
                                                   Recommendation.status == "approved"))
    plans = db.scalars(select(SupportPlan).where(SupportPlan.student_id == st.id,
                                                 SupportPlan.status != "cancelled")
                       .options(selectinload(SupportPlan.owner)).order_by(SupportPlan.due_date))
    return {
        "recommendations": [{"id": r.id, "title": r.title, "text": r.edited_text or r.rationale,
                             "ai_assisted": bool(r.ai_drafted), "approved_at": iso(r.reviewed_at)} for r in recs],
        "plans": [{"id": p.id, "title": p.title, "description": p.description, "owner": user_brief(p.owner),
                   "due_date": p.due_date.isoformat() if p.due_date else None, "status": p.status} for p in plans],
    }


# ---------------------------------------------------------------- goals
class GoalIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    target_date: date | None = None


class GoalPatch(BaseModel):
    title: str | None = Field(None, min_length=3, max_length=200)
    target_date: date | None = None
    status: Literal["active", "achieved", "dropped"] | None = None


@router.get("/goals")
def goals(user: User = Depends(student_only), db: Session = Depends(get_db)):
    st = my_student(db, user)
    rows = db.scalars(select(StudyGoal).where(StudyGoal.student_id == st.id).order_by(StudyGoal.created_at.desc()))
    return {"items": [goal_out(g) for g in rows]}


@router.post("/goals", status_code=201)
def add_goal(body: GoalIn, user: User = Depends(student_only), db: Session = Depends(get_db)):
    st = my_student(db, user)
    g = StudyGoal(student_id=st.id, title=body.title, target_date=body.target_date)
    db.add(g)
    db.commit()
    return goal_out(g)


def _goal(db: Session, user: User, goal_id: int) -> StudyGoal:
    g = db.get(StudyGoal, goal_id)
    if g is None or g.student_id != my_student(db, user).id:
        raise HTTPException(404, "Goal not found")
    return g


@router.patch("/goals/{goal_id}")
def update_goal(goal_id: int, body: GoalPatch, user: User = Depends(student_only), db: Session = Depends(get_db)):
    g = _goal(db, user, goal_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(g, k, v)
    db.commit()
    return goal_out(g)


@router.delete("/goals/{goal_id}", status_code=204)
def delete_goal(goal_id: int, user: User = Depends(student_only), db: Session = Depends(get_db)):
    db.delete(_goal(db, user, goal_id))
    db.commit()


# ---------------------------------------------------------------- requests
class RequestIn(BaseModel):
    kind: Literal["help", "correction"]
    subject: str = Field(min_length=3, max_length=200)
    details: str = Field(min_length=5, max_length=4000)
    target_record: str | None = Field(None, max_length=200)


def route_reviewer(db: Session, student) -> int | None:
    """Advisor first; otherwise a teacher of one of the student's courses; otherwise an admin."""
    if student.advisor_id:
        return student.advisor_id
    teacher = db.scalar(select(Course.teacher_id).join(Enrollment).where(
        Enrollment.student_id == student.id, Course.teacher_id.is_not(None)).limit(1))
    if teacher:
        return teacher
    return db.scalar(select(User.id).where(User.role == Role.ADMIN, User.is_active.is_(True)).limit(1))


@router.get("/requests")
def my_requests(user: User = Depends(student_only), db: Session = Depends(get_db)):
    st = my_student(db, user)
    rows = db.scalars(select(StudentRequest).where(StudentRequest.student_id == st.id)
                      .order_by(StudentRequest.created_at.desc()))
    return {"items": [request_out(r, include_student=False) for r in rows]}


@router.post("/requests", status_code=201)
def create_request(body: RequestIn, request: Request, user: User = Depends(student_only),
                   db: Session = Depends(get_db)):
    """Request help, or correction of an inaccurate record; routed to an authorized reviewer (AT-07)."""
    st = my_student(db, user)
    r = StudentRequest(student_id=st.id, kind=body.kind, subject=body.subject, details=body.details,
                       target_record=body.target_record, assigned_to=route_reviewer(db, st), created_by=user.id)
    db.add(r)
    db.flush()
    audit(db, f"request.{body.kind}.create", user=user, request=request, target_type="student_request",
          target_id=r.id, detail={"assigned_to": r.assigned_to})
    return request_out(r, include_student=False)
