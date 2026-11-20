"""Data import endpoints (FR2)."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..config import get_settings
from ..core.audit import audit
from ..core.deps import require_roles
from ..database import get_db
from ..models import ImportBatch, Role, User
from ..services.imports import SPECS, commit_rows, template_csv, validate_csv
from ..services.risk_engine import assess_in_background
from .serializers import iso, user_brief

router = APIRouter(prefix="/imports", tags=["imports"])
importer = require_roles(Role.ADMIN, Role.TEACHER)


def batch_out(b: ImportBatch) -> dict:
    return {"id": b.id, "kind": b.kind, "filename": b.filename, "sha256": b.sha256, "source": b.source,
            "status": b.status, "total_rows": b.total_rows, "valid_rows": b.valid_rows, "errors": b.errors,
            "uploaded_by": user_brief(b.uploader), "created_at": iso(b.created_at),
            "committed_at": iso(b.committed_at)}


@router.get("/kinds")
def kinds(user: User = Depends(importer)):
    return {"items": [
        {"kind": k, "label": v["label"], "allowed": user.role in v["roles"],
         "columns": [{"name": c, "type": t, "required": r, **({"values": o["values"]} if "values" in o else {})}
                     for c, (t, r, o) in v["columns"].items()]}
        for k, v in SPECS.items()
    ]}


@router.get("/template/{kind}", response_class=PlainTextResponse)
def template(kind: str, user: User = Depends(importer)):
    if kind not in SPECS:
        raise HTTPException(404, "Unknown import type")
    return PlainTextResponse(template_csv(kind), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{kind}_template.csv"'})


@router.get("")
def history(user: User = Depends(importer), db: Session = Depends(get_db)):
    q = select(ImportBatch).options(selectinload(ImportBatch.uploader)).order_by(ImportBatch.created_at.desc()).limit(50)
    if user.role != Role.ADMIN:
        q = q.where(ImportBatch.uploaded_by == user.id)
    return {"items": [batch_out(b) for b in db.scalars(q)]}


@router.post("/validate")
async def validate(request: Request, kind: str = Form(...), file: UploadFile = File(...),
                   user: User = Depends(importer), db: Session = Depends(get_db)):
    s = get_settings()
    if kind not in SPECS:
        raise HTTPException(422, "Unknown import type")
    if user.role not in SPECS[kind]["roles"]:
        audit(db, "import.validate", user=user, request=request, outcome="denied", detail={"kind": kind})
        raise HTTPException(403, f"Your role cannot import '{kind}' data")
    name = (file.filename or "upload.csv")[:255]
    if not name.lower().endswith(".csv"):
        raise HTTPException(422, "Only .csv files are accepted")
    raw = await file.read(s.max_upload_bytes + 1)
    if len(raw) > s.max_upload_bytes:
        raise HTTPException(413, f"File exceeds the {s.max_upload_bytes // (1024 * 1024)} MB limit")
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(422, "File must be UTF-8 encoded CSV") from None

    result = validate_csv(db, kind, content, user)
    batch = ImportBatch(kind=kind, filename=name, sha256=hashlib.sha256(raw).hexdigest(), uploaded_by=user.id,
                        status="validated" if result.ok else "rejected", total_rows=result.total,
                        valid_rows=len(result.rows) if result.ok else 0, errors=result.errors,
                        content=content if result.ok else None)
    db.add(batch)
    db.flush()
    audit(db, "import.validate", user=user, request=request, target_type="import_batch", target_id=batch.id,
          outcome="success" if result.ok else "error",
          detail={"kind": kind, "rows": result.total, "errors": len(result.errors)})
    db.refresh(batch)
    return batch_out(batch)


@router.post("/{batch_id}/commit")
def commit(batch_id: int, request: Request, background: BackgroundTasks, user: User = Depends(importer),
           db: Session = Depends(get_db)):
    batch = db.get(ImportBatch, batch_id)
    if batch is None or (user.role != Role.ADMIN and batch.uploaded_by != user.id):
        raise HTTPException(404, "Import batch not found")
    if batch.status != "validated" or not batch.content:
        raise HTTPException(409, "Only a successfully validated batch can be committed")
    # Re-validate against the current database state before writing.
    result = validate_csv(db, batch.kind, batch.content, user)
    if not result.ok:
        batch.status, batch.errors, batch.content = "rejected", result.errors, None
        audit(db, "import.commit", user=user, request=request, target_type="import_batch", target_id=batch.id,
              outcome="error", detail={"reason": "revalidation failed"})
        raise HTTPException(409, "Data changed since validation; please validate the file again")
    affected = commit_rows(db, batch.kind, result.rows, batch.id)
    batch.status, batch.valid_rows, batch.content = "committed", len(result.rows), None
    batch.committed_at = datetime.now(UTC)
    audit(db, "import.commit", user=user, request=request, target_type="import_batch", target_id=batch.id,
          detail={"kind": batch.kind, "rows": len(result.rows), "students": len(affected)})
    if affected:
        background.add_task(assess_in_background, sorted(affected))
    db.refresh(batch)
    out = batch_out(batch)
    out["students_refreshing"] = len(affected)
    return out
