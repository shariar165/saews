"""Aggregate analytics and exports (FR9)."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..core.audit import audit
from ..core.deps import require_roles
from ..database import get_db
from ..models import Role, User
from ..services import reports as svc

router = APIRouter(prefix="/reports", tags=["reports"])
reporter = require_roles(Role.ADMIN, Role.TEACHER, Role.ADVISOR, Role.ANALYST)


@router.get("/summary")
def summary(request: Request, user: User = Depends(reporter), db: Session = Depends(get_db)):
    out = svc.summary(db, user)
    audit(db, "report.summary", user=user, request=request, detail={"deidentified": out["deidentified"]})
    return out


@router.get("/trends")
def trends(user: User = Depends(reporter), db: Session = Depends(get_db)):
    return {"attendance_by_course": svc.attendance_trends(db, user)}


@router.get("/export")
def export(request: Request, identifiable: bool = False, user: User = Depends(reporter), db: Session = Depends(get_db)):
    """CSV export. Identifiable exports need explicit authorization (AT-08)."""
    if identifiable and not svc.can_export_identifiable(user):
        audit(db, "report.export", user=user, request=request, outcome="denied", detail={"identifiable": True})
        raise HTTPException(403, "You are not authorized to export identifiable student data. "
                                 "A de-identified export is available instead.")
    body, n = svc.export_csv(db, user, identifiable)
    audit(db, "report.export", user=user, request=request, detail={"identifiable": identifiable, "rows": n})
    kind = "identifiable" if identifiable else "deidentified"
    return Response(body, media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="risk_report_{kind}_{date.today()}.csv"'})
