"""Retention rules (FR8): purge records older than the configured retention periods."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import AuditLog, ImportBatch, RiskAssessment


def run_retention(db: Session, dry_run: bool = True) -> dict:
    s = get_settings()
    now = datetime.now(UTC)
    audit_cutoff = now - timedelta(days=s.audit_retention_days)
    data_cutoff = now - timedelta(days=s.retention_days)

    targets = {
        "audit_logs": (AuditLog, AuditLog.ts < audit_cutoff),
        "historical_risk_assessments": (RiskAssessment, (RiskAssessment.created_at < data_cutoff)
                                        & RiskAssessment.is_current.is_(False)),
        "import_batches": (ImportBatch, ImportBatch.created_at < data_cutoff),
    }
    result = {"dry_run": dry_run, "audit_cutoff": audit_cutoff.isoformat(timespec="seconds"),
              "data_cutoff": data_cutoff.isoformat(timespec="seconds"), "counts": {}}
    for name, (model, cond) in targets.items():
        result["counts"][name] = db.scalar(select(func.count()).select_from(model).where(cond)) or 0
        if not dry_run:
            db.execute(delete(model).where(cond))
    # Staged file contents are only needed until commit/rejection.
    if not dry_run:
        db.query(ImportBatch).filter(ImportBatch.status != "validated").update({ImportBatch.content: None})
        db.commit()
    return result
