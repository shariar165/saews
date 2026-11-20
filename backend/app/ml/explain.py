"""Plain-language reason codes for model contributions (FR5)."""

from __future__ import annotations

FACTOR_CODE = {
    "attendance_rate": "LOW_ATTENDANCE",
    "attendance_trend": "LOW_ATTENDANCE",
    "avg_score": "LOW_SCORES",
    "score_trend": "LOW_SCORES",
    "missing_rate": "MISSING_WORK",
    "late_rate": "MISSING_WORK",
    "engagement_change": "LOW_ENGAGEMENT",
    "avg_logins": "LOW_ENGAGEMENT",
    "prior_gpa": "PRIOR_ACADEMIC",
}

FEATURE_LABEL = {
    "attendance_rate": "Attendance rate",
    "attendance_trend": "Recent attendance change",
    "avg_score": "Average assessment score",
    "score_trend": "Recent score change",
    "missing_rate": "Missing assignments",
    "late_rate": "Late submissions",
    "engagement_change": "Recent learning-platform activity change",
    "avg_logins": "Learning-platform logins",
    "prior_gpa": "Prior GPA",
}


def describe(feature: str, value: float | None) -> str:
    if value is None:
        return f"{FEATURE_LABEL.get(feature, feature)}: no data"
    if feature == "attendance_rate":
        return f"Attendance is {value:.0%} across enrolled courses"
    if feature == "attendance_trend":
        return f"Attendance changed by {value * 100:+.0f} percentage points in the last 4 weeks"
    if feature == "avg_score":
        return f"Average assessment score is {value:.0f}%"
    if feature == "score_trend":
        return f"The two most recent assessment scores changed by {value:+.0f} points versus earlier ones"
    if feature == "missing_rate":
        return f"{value:.0%} of assignments are missing"
    if feature == "late_rate":
        return f"{value:.0%} of assignments were submitted late"
    if feature == "engagement_change":
        return f"Learning-platform activity changed by {value:+.0%} in recent weeks"
    if feature == "avg_logins":
        return f"Averages {value:.1f} learning-platform logins per course each week"
    if feature == "prior_gpa":
        return f"Prior GPA is {value:.2f}"
    return f"{feature} = {value}"
