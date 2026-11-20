"""Student list, profile, indicators and per-student workflow views (FR3, FR4, FR5)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from ..core.audit import audit
from ..core.deps import get_student_for_user, staff_only, visible_student_ids_query
from ..database import get_db
from ..models import (
    Course,
    Enrollment,
    Recommendation,
    RiskAssessment,
    Role,
    Student,
    StudentRequest,
    SupportPlan,
    User,
)
from ..services.indicators import student_series
from ..services.risk_engine import assess_students
from .serializers import assessment_out, plan_out, recommendation_out, request_out, student_out, user_brief

router = APIRouter(prefix="/students", tags=["students"])

LEVEL_SORT = {"critical": 0, "high": 1, "moderate": 2, "insufficient_data": 3, "unavailable": 4, "low": 5}


@router.get("")
def list_students(
    request: Request,
    search: str | None = Query(None, max_length=100),
    level: str | None = None,
    program: str | None = None,
    course: str | None = None,
    user: User = Depends(staff_only),
    db: Session = Depends(get_db),
):
    q = (select(Student, RiskAssessment)
         .outerjoin(RiskAssessment, (RiskAssessment.student_id == Student.id) & RiskAssessment.is_current.is_(True))
         .options(selectinload(Student.advisor)))
    scope = visible_student_ids_query(user)
    if scope is not None:
        q = q.where(Student.id.in_(scope))
    if search:
        like = f"%{search.strip()}%"
        q = q.where(or_(Student.full_name.ilike(like), Student.student_code.ilike(like)))
    if level:
        q = q.where(RiskAssessment.risk_level == level)
    if program:
        q = q.where(Student.program == program)
    if course:
        q = q.where(Student.id.in_(select(Enrollment.student_id).join(Course).where(Course.code == course)))
    rows = db.execute(q).all()
    items = [student_out(s, ra) for s, ra in rows]
    items.sort(key=lambda d: (LEVEL_SORT.get((d["assessment"] or {}).get("risk_level"), 9),
                              -((d["assessment"] or {}).get("probability") or 0), d["student_code"]))
    audit(db, "student.list", user=user, request=request, detail={"count": len(items), "search": search or None})
    programs = sorted({s.program for s, _ in rows})
    return {"items": items, "programs": programs}


@router.get("/{student_id}")
def get_student(student_id: int, request: Request, user: User = Depends(staff_only), db: Session = Depends(get_db)):
    st = get_student_for_user(db, user, student_id, request, "student.view")
    ra = db.scalar(select(RiskAssessment).where(RiskAssessment.student_id == st.id, RiskAssessment.is_current.is_(True)))
    courses = db.execute(select(Course.code, Course.title, User.full_name).join(Enrollment, Enrollment.course_id == Course.id)
                         .outerjoin(User, User.id == Course.teacher_id).where(Enrollment.student_id == st.id)).all()
    audit(db, "student.view", user=user, request=request, target_type="student", target_id=st.id)
    out = student_out(st, ra)
    out["courses"] = [{"code": c, "title": t, "teacher": tn} for c, t, tn in courses]
    return out


@router.get("/{student_id}/indicators")
def indicators(student_id: int, request: Request, user: User = Depends(staff_only), db: Session = Depends(get_db)):
    st = get_student_for_user(db, user, student_id, request, "student.view")
    return student_series(db, st.id)


@router.get("/{student_id}/assessments")
def assessment_history(student_id: int, request: Request, user: User = Depends(staff_only), db: Session = Depends(get_db)):
    st = get_student_for_user(db, user, student_id, request, "student.view")
    rows = db.scalars(select(RiskAssessment).where(RiskAssessment.student_id == st.id)
                      .order_by(RiskAssessment.created_at.desc()).limit(50))
    return {"items": [assessment_out(r) for r in rows]}


@router.post("/{student_id}/assess")
def assess_now(student_id: int, request: Request, user: User = Depends(staff_only), db: Session = Depends(get_db)):
    st = get_student_for_user(db, user, student_id, request, "risk.assess")
    [ra] = assess_students(db, [st.id])
    audit(db, "risk.assess", user=user, request=request, target_type="student", target_id=st.id,
          detail={"level": ra.risk_level, "method": ra.method})
    return assessment_out(ra)


@router.get("/{student_id}/recommendations")
def recommendations(student_id: int, request: Request, user: User = Depends(staff_only), db: Session = Depends(get_db)):
    st = get_student_for_user(db, user, student_id, request, "student.view")
    rows = db.scalars(select(Recommendation).where(Recommendation.student_id == st.id)
                      .order_by(Recommendation.status != "proposed", Recommendation.created_at.desc()))
    return {"items": [recommendation_out(r) for r in rows]}


@router.get("/{student_id}/plans")
def plans(student_id: int, request: Request, user: User = Depends(staff_only), db: Session = Depends(get_db)):
    st = get_student_for_user(db, user, student_id, request, "student.view")
    rows = db.scalars(select(SupportPlan).where(SupportPlan.student_id == st.id)
                      .options(selectinload(SupportPlan.interventions), selectinload(SupportPlan.owner))
                      .order_by(SupportPlan.created_at.desc()))
    return {"items": [plan_out(p) for p in rows]}


@router.get("/{student_id}/requests")
def student_requests(student_id: int, request: Request, user: User = Depends(staff_only), db: Session = Depends(get_db)):
    st = get_student_for_user(db, user, student_id, request, "student.view")
    rows = db.scalars(select(StudentRequest).where(StudentRequest.student_id == st.id)
                      .order_by(StudentRequest.created_at.desc()))
    return {"items": [request_out(r) for r in rows]}


staff_router = APIRouter(tags=["students"])


@staff_router.get("/staff")
def list_staff(user: User = Depends(staff_only), db: Session = Depends(get_db)):
    """Staff who can own support plans."""
    rows = db.scalars(select(User).where(User.role.in_([Role.TEACHER, Role.ADVISOR]), User.is_active.is_(True))
                      .order_by(User.full_name))
    return {"items": [user_brief(u) for u in rows]}
