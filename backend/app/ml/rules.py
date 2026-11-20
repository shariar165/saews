"""Transparent rule-based engine.

Used (a) as the clearly-labelled fallback when the predictive model is unavailable (FR10)
and (b) as the simple baseline the model is compared against (SRS §2.2).
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    feature: str
    op: str  # "<" | "<=" | ">="
    threshold: float
    points: int
    code: str
    text: str


RULES: list[Rule] = [
    Rule("attendance_rate", "<", 0.70, 2, "LOW_ATTENDANCE", "Attendance is below 70%"),
    Rule("attendance_rate", "<", 0.80, 1, "LOW_ATTENDANCE", "Attendance is below 80%"),
    Rule("attendance_trend", "<=", -0.15, 1, "LOW_ATTENDANCE", "Attendance dropped by 15+ points recently"),
    Rule("avg_score", "<", 50, 2, "LOW_SCORES", "Average assessment score is below 50%"),
    Rule("avg_score", "<", 60, 1, "LOW_SCORES", "Average assessment score is below 60%"),
    Rule("score_trend", "<=", -10, 1, "LOW_SCORES", "Recent scores fell by 10+ points"),
    Rule("missing_rate", ">=", 0.40, 2, "MISSING_WORK", "40% or more of assignments are missing"),
    Rule("missing_rate", ">=", 0.20, 1, "MISSING_WORK", "20% or more of assignments are missing"),
    Rule("engagement_change", "<=", -0.50, 1, "LOW_ENGAGEMENT", "Learning-platform activity halved recently"),
]

# Only the most severe rule per (feature, op) family counts — e.g. <70% supersedes <80%.
LEVEL_BY_POINTS = [(6, "critical"), (4, "high"), (2, "moderate"), (0, "low")]


def _hit(value: float | None, rule: Rule) -> bool:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return False
    if rule.op == "<":
        return value < rule.threshold
    if rule.op == "<=":
        return value <= rule.threshold
    return value >= rule.threshold


def evaluate_rules(features: dict[str, float | None]) -> tuple[int, str, list[dict]]:
    """Return (points, level, factors)."""
    points = 0
    factors: list[dict] = []
    seen_features: set[str] = set()
    for rule in RULES:  # ordered most-severe first within a feature
        key = f"{rule.feature}{rule.op}"
        if key in seen_features:
            continue
        if _hit(features.get(rule.feature), rule):
            seen_features.add(key)
            points += rule.points
            factors.append(
                {
                    "feature": rule.feature,
                    "code": rule.code,
                    "label": rule.text,
                    "value": features.get(rule.feature),
                    "contribution": float(rule.points),
                    "source": "rule",
                }
            )
    level = next(lvl for threshold, lvl in LEVEL_BY_POINTS if points >= threshold)
    factors.sort(key=lambda f: f["contribution"], reverse=True)
    return points, level, factors
