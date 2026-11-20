from fastapi import APIRouter

from ..config import get_settings
from ..ml.model import model_status

router = APIRouter(tags=["meta"])

DEMO_ACCOUNTS = [
    {"role": "teacher", "email": "teacher1@saews.demo", "note": "Teaches SE331, SE221, CSE311, CSE331 (SE & CS students)"},
    {"role": "teacher", "email": "teacher2@saews.demo", "note": "Teaches CSE215, MAT211, BUS101, ACC201, ENG101"},
    {"role": "advisor", "email": "advisor1@saews.demo", "note": "Advises SE students"},
    {"role": "advisor", "email": "advisor2@saews.demo", "note": "Advises CS and BBA students"},
    {"role": "student", "email": "student@saews.demo", "note": "Student portal"},
    {"role": "analyst", "email": "analyst@saews.demo", "note": "Aggregate, de-identified view"},
    {"role": "admin", "email": "admin@saews.demo", "note": "Users, imports, model, audit"},
]
DEMO_PASSWORD = "Demo@2026!"


@router.get("/health")
def health():
    m = model_status()
    return {"status": "ok", "model_available": m["available"], "model_version": m["version"]}


@router.get("/meta")
def meta():
    s = get_settings()
    out = {"app_name": s.app_name, "demo_mode": s.demo_mode,
           "thresholds": {"moderate": s.risk_threshold_moderate, "high": s.risk_threshold_high,
                          "critical": s.risk_threshold_critical},
           "stale_after_days": s.stale_after_days}
    if s.demo_mode:
        out["demo_accounts"] = DEMO_ACCOUNTS
        out["demo_password"] = DEMO_PASSWORD
    return out
