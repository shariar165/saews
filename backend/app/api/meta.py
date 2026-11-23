from fastapi import APIRouter

from ..config import get_settings
from ..ml.model import model_status

router = APIRouter(tags=["meta"])

DEMO_ACCOUNTS = [
    {"role": "teacher", "email": "teacher1@saews.demo", "note": "Teaches Mathematics, Science & Accounting (SSC + HSC)"},
    {"role": "teacher", "email": "teacher2@saews.demo", "note": "Teaches Bangla, English, ICT, Business & Humanities (SSC + HSC)"},
    {"role": "advisor", "email": "advisor1@saews.demo", "note": "Class advisor for school students (Class 9–10)"},
    {"role": "advisor", "email": "advisor2@saews.demo", "note": "Class advisor for college students (Class 11–12)"},
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
