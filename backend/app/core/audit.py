"""Audit logging helper (FR8). Every access to identifiable data, export, login and
permission change is recorded with actor, target and outcome."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from ..models import AuditLog, User


def client_ip(request: Request | None) -> str | None:
    if request is None or request.client is None:
        return None
    return request.client.host


def audit(
    db: Session,
    action: str,
    *,
    user: User | None = None,
    request: Request | None = None,
    target_type: str | None = None,
    target_id: Any = None,
    outcome: str = "success",
    detail: dict | None = None,
    commit: bool = True,
) -> AuditLog:
    entry = AuditLog(
        actor_id=user.id if user else None,
        actor_role=user.role if user else None,
        action=action,
        target_type=target_type,
        target_id=None if target_id is None else str(target_id),
        outcome=outcome,
        ip=client_ip(request),
        detail=detail or {},
    )
    db.add(entry)
    if commit:
        db.commit()
    return entry
