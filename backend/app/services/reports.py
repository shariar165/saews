"""Aggregate analytics and exports (FR9) with de-identification for analysts (AT-08)."""

from __future__ import annotations

import csv
import hashlib
import hmac
import io
from collections import Counter, defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import (
    AttendanceRecord,
    Course,
    Enrollment,
    Intervention,
    RiskAssessment,
    Role,
    Student,
    SupportPlan,
    User,
)

LEVELS = ["low", "moderate", "high", "critical", "insufficient_data", "unavailable"]


def pseudonym(student_code: str) -> str:
    key = get_settings().jwt_secret.encode()
    return "P-" + hmac.new(key, student_code.encode(), hashlib.sha256).hexdigest()[:10].upper()


def suppress(n: int, apply: bool) -> int | None:
    """Small-cell suppression: counts 1..k-1 become None ("<k")."""
    if apply and 0 < n < get_settings().min_group_size:
        return None
    return n


def _scope_student_ids(db: Session, user: User) -> list[int] | None:
    from ..core.deps import visible_student_ids_query

    if user.role in (Role.ADMIN, Role.ANALYST):
        return None
    q = visible_student_ids_query(user)
    return list(db.scalars(q))


def summary(db: Session, user: User) -> dict:
    deidentify = user.role == Role.ANALYST
    ids = _scope_student_ids(db, user)
    q = select(RiskAssessment.risk_level, RiskAssessment.method, Student.program).join(
        Student, Student.id == RiskAssessment.student_id).where(RiskAssessment.is_current.is_(True))
    if ids is not None:
        q = q.where(RiskAssessment.student_id.in_(ids))
    rows = db.execute(q).all()

    overall = Counter(r[0] for r in rows)
    methods = Counter(r[1] for r in rows)
    by_program: dict[str, Counter] = defaultdict(Counter)
    for level, _, program in rows:
        by_program[program][level] += 1

    # by course
    cq = select(Course.code, Course.title, RiskAssessment.risk_level).join(
        Enrollment, Enrollment.course_id == Course.id).join(
        RiskAssessment, (RiskAssessment.student_id == Enrollment.student_id) & RiskAssessment.is_current.is_(True))
    if user.role == Role.TEACHER:
        cq = cq.where(Course.teacher_id == user.id)
    elif ids is not None:
        cq = cq.where(Enrollment.student_id.in_(ids))
    by_course: dict[str, Counter] = defaultdict(Counter)
    titles = {}
    for code, title, level in db.execute(cq):
        by_course[code][level] += 1
        titles[code] = title

    pq = select(SupportPlan.status, func.count()).group_by(SupportPlan.status)
    iq = select(Intervention.status, func.count()).join(SupportPlan).group_by(Intervention.status)
    if ids is not None:
        pq = pq.where(SupportPlan.student_id.in_(ids))
        iq = iq.where(SupportPlan.student_id.in_(ids))
    plans = dict(db.execute(pq).all())
    interventions = dict(db.execute(iq).all())

    def counts(c: Counter) -> dict:
        return {lvl: suppress(c.get(lvl, 0), deidentify) for lvl in LEVELS}

    return {
        "deidentified": deidentify,
        "min_group_size": get_settings().min_group_size,
        "total_students": len(rows),
        "overall": counts(overall),
        "methods": {k: suppress(v, deidentify) for k, v in methods.items()},
        "by_program": {p: counts(c) for p, c in sorted(by_program.items())},
        "by_course": {c: {"title": titles[c], "counts": counts(v)} for c, v in sorted(by_course.items())},
        "plans": {k: suppress(v, deidentify) for k, v in plans.items()},
        "interventions": {k: suppress(v, deidentify) for k, v in interventions.items()},
    }


def attendance_trends(db: Session, user: User) -> dict:
    """Weekly attendance rate per course (aggregate only)."""
    q = select(Course.code, AttendanceRecord.week, AttendanceRecord.status, func.count()).join(
        Course, Course.id == AttendanceRecord.course_id).where(AttendanceRecord.status != "excused").group_by(
        Course.code, AttendanceRecord.week, AttendanceRecord.status)
    if user.role == Role.TEACHER:
        q = q.where(Course.teacher_id == user.id)
    elif user.role == Role.ADVISOR:
        q = q.where(AttendanceRecord.student_id.in_(select(Student.id).where(Student.advisor_id == user.id)))
    agg: dict[str, dict[int, list[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for code, week, status, n in db.execute(q):
        cell = agg[code][week]
        cell[1] += n
        if status in ("present", "late"):
            cell[0] += n
    return {
        code: [{"week": w, "rate": round(a / t, 3) if t else None} for w, (a, t) in sorted(weeks.items())]
        for code, weeks in sorted(agg.items())
    }


EXPORT_COLUMNS_IDENTIFIABLE = ["student_code", "full_name", "program", "year_of_study", "risk_level", "probability",
                               "method", "model_version", "assessed_at", "data_as_of", "top_factor", "review_status"]
EXPORT_COLUMNS_DEIDENTIFIED = ["pseudonym", "program", "year_of_study", "risk_level", "method", "data_as_of"]


def export_csv(db: Session, user: User, identifiable: bool) -> tuple[str, int]:
    ids = _scope_student_ids(db, user)
    q = select(Student, RiskAssessment).join(RiskAssessment, (RiskAssessment.student_id == Student.id)
                                              & RiskAssessment.is_current.is_(True)).order_by(Student.student_code)
    if ids is not None:
        q = q.where(Student.id.in_(ids))
    buf = io.StringIO()
    w = csv.writer(buf)
    cols = EXPORT_COLUMNS_IDENTIFIABLE if identifiable else EXPORT_COLUMNS_DEIDENTIFIED
    w.writerow(cols)
    n = 0
    for st, ra in db.execute(q):
        if identifiable:
            top = ra.factors[0]["label"] if ra.factors else ""
            w.writerow([st.student_code, st.full_name, st.program, st.year_of_study, ra.risk_level, ra.probability,
                        ra.method, ra.model_version, ra.created_at.isoformat(timespec="seconds"),
                        ra.data_as_of.isoformat() if ra.data_as_of else "", top, ra.review_status])
        else:
            w.writerow([pseudonym(st.student_code), st.program, st.year_of_study, ra.risk_level, ra.method,
                        ra.data_as_of.isoformat() if ra.data_as_of else ""])
        n += 1
    return buf.getvalue(), n


def can_export_identifiable(user: User) -> bool:
    if user.role in (Role.ADMIN, Role.TEACHER, Role.ADVISOR):
        return True
    return user.role == Role.ANALYST and user.identifiable_access
