"""Administration: users and roles, audit log, model monitoring, risk refresh, retention (FR1, FR8, FR10)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..core.audit import audit
from ..core.deps import admin_only
from ..core.security import hash_password
from ..database import get_db
from ..ml.model import model_status, registry_path
from ..models import AuditLog, ModelRegistry, RiskAssessment, Role, Student, User
from ..services.retention import run_retention
from ..services.risk_engine import assess_in_background
from .serializers import iso, user_out

router = APIRouter(prefix="/admin", tags=["admin"])

RoleName = Literal["admin", "teacher", "advisor", "student", "analyst"]


class UserIn(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=200)
    role: RoleName
    password: str = Field(min_length=10, max_length=128)
    identifiable_access: bool = False
    student_code: str | None = Field(None, max_length=40, description="Link a student account to a student record")


class UserPatch(BaseModel):
    full_name: str | None = Field(None, min_length=2, max_length=200)
    role: RoleName | None = None
    is_active: bool | None = None
    identifiable_access: bool | None = None
    password: str | None = Field(None, min_length=10, max_length=128)


@router.get("/users")
def users(user: User = Depends(admin_only), db: Session = Depends(get_db)):
    return {"items": [user_out(u) for u in db.scalars(select(User).order_by(User.role, User.full_name))]}


@router.post("/users", status_code=201)
def create_user(body: UserIn, request: Request, user: User = Depends(admin_only), db: Session = Depends(get_db)):
    if db.scalar(select(User.id).where(func.lower(User.email) == body.email.lower())):
        raise HTTPException(409, "A user with this email already exists")
    u = User(email=body.email.lower(), full_name=body.full_name, role=body.role,
             password_hash=hash_password(body.password),
             identifiable_access=body.identifiable_access and body.role == Role.ANALYST)
    db.add(u)
    db.flush()
    if body.role == Role.STUDENT and body.student_code:
        st = db.scalar(select(Student).where(Student.student_code == body.student_code))
        if st is None:
            db.rollback()
            raise HTTPException(422, "Unknown student_code")
        st.user_id = u.id
    audit(db, "user.create", user=user, request=request, target_type="user", target_id=u.id,
          detail={"role": body.role})
    return user_out(u)


@router.patch("/users/{user_id}")
def update_user(user_id: int, body: UserPatch, request: Request, user: User = Depends(admin_only),
                db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if u is None:
        raise HTTPException(404, "User not found")
    if u.id == user.id and (body.role not in (None, Role.ADMIN) or body.is_active is False):
        raise HTTPException(409, "You cannot remove your own admin access")
    changes = body.model_dump(exclude_unset=True)
    if "password" in changes:
        u.password_hash = hash_password(changes.pop("password"))
        changes["password"] = "changed"
    for k, v in changes.items():
        if k != "password":
            setattr(u, k, v)
    if u.role != Role.ANALYST:
        u.identifiable_access = False
    audit(db, "user.update", user=user, request=request, target_type="user", target_id=u.id,
          detail={k: (v if k != "password" else "changed") for k, v in changes.items()})
    return user_out(u)


@router.get("/audit")
def audit_log(action: str | None = None, outcome: str | None = None, limit: int = 200,
              user: User = Depends(admin_only), db: Session = Depends(get_db)):
    q = select(AuditLog, User.email).outerjoin(User, User.id == AuditLog.actor_id).order_by(AuditLog.ts.desc())
    if action:
        q = q.where(AuditLog.action.like(f"{action}%"))
    if outcome:
        q = q.where(AuditLog.outcome == outcome)
    rows = db.execute(q.limit(max(1, min(limit, 1000)))).all()
    return {"items": [{"id": a.id, "ts": iso(a.ts), "actor": email, "actor_role": a.actor_role,
                       "action": a.action, "target_type": a.target_type, "target_id": a.target_id,
                       "outcome": a.outcome, "ip": a.ip, "detail": a.detail} for a, email in rows]}


@router.get("/model")
def model_monitor(user: User = Depends(admin_only), db: Session = Depends(get_db)):
    status = model_status()
    metrics = None
    if status["available"]:
        p = Path(get_settings().model_dir) / f"metrics_{status['version']}.json"
        if p.exists():
            metrics = json.loads(p.read_text(encoding="utf-8"))
    since = datetime.now(UTC) - timedelta(days=30)
    methods = dict(db.execute(select(RiskAssessment.method, func.count()).where(RiskAssessment.created_at >= since)
                              .group_by(RiskAssessment.method)).all())
    current_methods = dict(db.execute(select(RiskAssessment.method, func.count())
                                      .where(RiskAssessment.is_current.is_(True)).group_by(RiskAssessment.method)).all())
    errors = [{"created_at": iso(ra.created_at), "error": ra.error} for ra in db.scalars(
        select(RiskAssessment).where(RiskAssessment.error.is_not(None)).order_by(RiskAssessment.created_at.desc()).limit(10))]
    history = [{"version": m.version, "created_at": iso(m.created_at), "is_active": m.is_active,
                "auc": (m.metrics.get("model_at_alert_threshold") or {}).get("roc_auc")}
               for m in db.scalars(select(ModelRegistry).order_by(ModelRegistry.created_at.desc()).limit(10))]
    s = get_settings()
    return {"status": status, "registry_file": str(registry_path()), "metrics": metrics,
            "methods_last_30_days": methods, "current_methods": current_methods, "recent_errors": errors,
            "history": history,
            "settings": {"thresholds": {"moderate": s.risk_threshold_moderate, "high": s.risk_threshold_high,
                                        "critical": s.risk_threshold_critical},
                         "min_data_completeness": s.min_data_completeness, "stale_after_days": s.stale_after_days,
                         "retention_days": s.retention_days, "audit_retention_days": s.audit_retention_days,
                         "min_group_size": s.min_group_size}}


@router.post("/recompute", status_code=202)
def recompute(request: Request, background: BackgroundTasks, user: User = Depends(admin_only),
              db: Session = Depends(get_db)):
    background.add_task(assess_in_background, None)
    audit(db, "risk.recompute_all", user=user, request=request)
    return {"queued": True}


class RetentionIn(BaseModel):
    dry_run: bool = True


@router.post("/retention")
def retention(body: RetentionIn, request: Request, user: User = Depends(admin_only), db: Session = Depends(get_db)):
    result = run_retention(db, dry_run=body.dry_run)
    audit(db, "retention.run", user=user, request=request, detail=result)
    return result
