"""Risk assessment orchestration (FR4, FR5, FR10).

For each student: build features -> data-quality checks -> predictive model ->
(on failure) transparent rule fallback -> (on failure) "unavailable". Every result
stores method, model version, timestamp, data freshness and contributing factors.
No action is ever triggered automatically: outputs are queued for human review.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import date

import numpy as np
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..config import get_settings
from ..ml import model as model_service
from ..ml.explain import FACTOR_CODE, FEATURE_LABEL, describe
from ..ml.features import FEATURES, compute_features, feature_snapshot
from ..ml.rules import evaluate_rules
from ..models import RiskAssessment, Student
from .data_loader import load_frames

log = logging.getLogger("saews.risk")

LEVEL_ORDER = {"low": 0, "moderate": 1, "high": 2, "critical": 3}
GROUP_LABEL = {
    "attendance": "attendance records",
    "assessments": "class test / exam scores",
    "assignments": "homework submissions",
    "engagement": "online learning portal activity",
    "prior_gpa": "previous exam GPA",
}


def level_for_probability(p: float) -> str:
    s = get_settings()
    if p >= s.risk_threshold_critical:
        return "critical"
    if p >= s.risk_threshold_high:
        return "high"
    if p >= s.risk_threshold_moderate:
        return "moderate"
    return "low"


def _model_factors(features: dict, contrib: np.ndarray, top: int = 4) -> list[dict]:
    items = []
    for f, c in zip(FEATURES, contrib, strict=True):
        if features.get(f) is None or c <= 0.05:  # only factors that increase risk, ignore imputed values
            continue
        items.append({
            "feature": f,
            "code": FACTOR_CODE[f],
            "label": describe(f, features[f]),
            "name": FEATURE_LABEL[f],
            "value": features[f],
            "contribution": round(float(c), 3),
            "source": "model",
        })
    items.sort(key=lambda x: x["contribution"], reverse=True)
    return items[:top]


def assess_students(db: Session, student_ids: Iterable[int] | None = None, *, as_of: date | None = None,
                    generate_recommendations: bool = True) -> list[RiskAssessment]:
    """(Re)assess the given students (all if None). Commits and returns new assessments."""
    from .recommendations import propose_for_assessment  # avoid import cycle

    s = get_settings()
    as_of = as_of or date.today()
    ids = list(student_ids) if student_ids is not None else list(db.scalars(select(Student.id)))
    if not ids:
        return []
    frames, code_to_id = load_frames(db, ids)
    feats = compute_features(frames, as_of=as_of)

    # Score all eligible students with the model in one batch; any failure => fallback.
    model, proba, contrib, model_error = None, None, None, None
    try:
        model = model_service.load_active_model()
        proba, contrib = model.predict(feats[FEATURES])
    except model_service.ModelUnavailable as exc:
        model_error = str(exc)
        log.warning("Model unavailable, using rule-based fallback: %s", exc)

    results: list[RiskAssessment] = []
    for pos, (code, row) in enumerate(feats.iterrows()):
        sid = code_to_id.get(code)
        if sid is None:
            continue
        fsnap = feature_snapshot(row)
        completeness = float(row["completeness"])
        missing = list(row["missing_groups"])
        raw_age = row["data_age_days"]
        age = None if raw_age is None or (isinstance(raw_age, float) and np.isnan(raw_age)) else int(raw_age)
        warnings: list[str] = []
        if missing:
            warnings.append("Missing data: " + ", ".join(GROUP_LABEL[g] for g in missing) + ".")
        stale = age is not None and age > s.stale_after_days
        if stale:
            warnings.append(f"Most recent data is {age} days old; the assessment may not reflect the student's current situation.")

        ra = RiskAssessment(
            student_id=sid, features=fsnap, completeness=round(completeness, 2), missing_fields=missing,
            data_as_of=row["data_as_of"], data_age_days=age, warnings=warnings,
        )

        if completeness < s.min_data_completeness:
            ra.risk_level, ra.method, ra.reliable = "insufficient_data", "none", False
            ra.warnings.append("Not enough validated data to estimate risk. No prediction is shown.")
        elif model is not None and proba is not None:
            p = float(proba[pos])
            ra.probability = round(p, 4)
            ra.risk_level = level_for_probability(p)
            ra.method, ra.model_version = "model", model.version
            ra.factors = _model_factors(fsnap, contrib[pos])
            ra.reliable = not stale and not missing
        else:
            try:
                points, level, factors = evaluate_rules(fsnap)
                ra.rule_points, ra.risk_level, ra.factors = points, level, factors
                ra.method, ra.model_version = "rules_fallback", "rules-v1"
                ra.reliable = not stale and not missing
                ra.error = model_error
                ra.warnings.append("Predictive model unavailable — this is a rule-based (fallback) result.")
            except Exception as exc:  # noqa: BLE001
                log.exception("Rule fallback failed")
                ra.risk_level, ra.method, ra.reliable = "unavailable", "unavailable", False
                ra.error = f"{model_error}; rules: {exc}"
                ra.warnings.append("Risk prediction is currently unavailable.")
        if not ra.reliable and ra.risk_level in LEVEL_ORDER:
            ra.warnings.append("Treat this result as provisional until the data issues above are resolved.")
        results.append(ra)

    assessed_ids = [r.student_id for r in results]
    db.execute(update(RiskAssessment).where(RiskAssessment.student_id.in_(assessed_ids), RiskAssessment.is_current.is_(True))
               .values(is_current=False))
    db.add_all(results)
    db.flush()
    if generate_recommendations:
        for ra in results:
            propose_for_assessment(db, ra)
    db.commit()
    return results


def assess_in_background(student_ids: list[int] | None) -> None:
    """Entry point for FastAPI BackgroundTasks (own session)."""
    from ..database import SessionLocal

    with SessionLocal() as db:
        try:
            assess_students(db, student_ids)
        except Exception:  # noqa: BLE001
            log.exception("Background risk refresh failed")
