"""Authentication and authorization dependencies (FR1, FR8 — least privilege)."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import false, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import Course, Enrollment, Role, Student, User
from .audit import audit
from .security import decode_access_token


def _token_from_request(request: Request) -> str | None:
    token = request.cookies.get(get_settings().cookie_name)
    if token:
        return token
    header = request.headers.get("Authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return None


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = _token_from_request(request)
    payload = decode_access_token(token) if token else None
    if not payload:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    user = db.get(User, int(payload["sub"]))
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    return user


def require_roles(*roles: str) -> Callable[..., User]:
    def checker(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
        if user.role not in roles:
            audit(
                db,
                "access.denied",
                user=user,
                request=request,
                target_type="endpoint",
                target_id=request.url.path,
                outcome="denied",
                detail={"required_roles": list(roles)},
            )
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have permission to perform this action")
        return user

    return checker


staff_only = require_roles(Role.ADMIN, Role.TEACHER, Role.ADVISOR)
admin_only = require_roles(Role.ADMIN)


def visible_student_ids_query(user: User):
    """SELECT of student ids this user may see individually. None => all (admin)."""
    if user.role == Role.ADMIN:
        return None
    if user.role == Role.TEACHER:
        return (
            select(Enrollment.student_id)
            .join(Course, Course.id == Enrollment.course_id)
            .where(Course.teacher_id == user.id)
        )
    if user.role == Role.ADVISOR:
        return select(Student.id).where(Student.advisor_id == user.id)
    if user.role == Role.STUDENT:
        return select(Student.id).where(Student.user_id == user.id)
    return select(Student.id).where(false())  # analysts: aggregate only


def can_view_student(db: Session, user: User, student: Student) -> bool:
    if user.role == Role.ADMIN:
        return True
    if user.role == Role.ADVISOR:
        return student.advisor_id == user.id
    if user.role == Role.STUDENT:
        return student.user_id == user.id
    if user.role == Role.TEACHER:
        q = (
            select(Enrollment.id)
            .join(Course, Course.id == Enrollment.course_id)
            .where(Enrollment.student_id == student.id, Course.teacher_id == user.id)
            .limit(1)
        )
        return db.scalar(q) is not None
    return False


def get_student_for_user(db: Session, user: User, student_id: int, request: Request, action: str) -> Student:
    """Load a student and enforce per-record authorization; denied attempts are audited (AT-01)."""
    student = db.get(Student, student_id)
    if student is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Student not found")
    if not can_view_student(db, user, student):
        audit(db, action, user=user, request=request, target_type="student", target_id=student_id, outcome="denied")
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You are not authorized to view this student's records")
    return student


def my_student(db: Session, user: User) -> Student:
    student = db.scalar(select(Student).where(Student.user_id == user.id))
    if student is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No student record is linked to this account")
    return student
