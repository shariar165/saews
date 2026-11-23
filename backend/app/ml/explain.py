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
    "avg_score": "Average class test / exam score",
    "score_trend": "Recent score change",
    "missing_rate": "Missing homework",
    "late_rate": "Late homework",
    "engagement_change": "Recent online learning portal activity change",
    "avg_logins": "Online learning portal logins",
    "prior_gpa": "Previous exam GPA",
}


def describe(feature: str, value: float | None) -> str:
    if value is None:
        return f"{FEATURE_LABEL.get(feature, feature)}: no data"
    if feature == "attendance_rate":
        return f"Attendance is {value:.0%} across enrolled subjects"
    if feature == "attendance_trend":
        return f"Attendance changed by {value * 100:+.0f} percentage points in the last 4 weeks"
    if feature == "avg_score":
        return f"Average class test / exam score is {value:.0f}%"
    if feature == "score_trend":
        return f"The two most recent class test / exam scores changed by {value:+.0f} points versus earlier ones"
    if feature == "missing_rate":
        return f"{value:.0%} of homework is missing"
    if feature == "late_rate":
        return f"{value:.0%} of homework was submitted late"
    if feature == "engagement_change":
        return f"Online learning portal activity changed by {value:+.0%} in recent weeks"
    if feature == "avg_logins":
        return f"Averages {value:.1f} online learning portal logins per subject each week"
    if feature == "prior_gpa":
        return f"Previous exam GPA is {value:.2f} / 5.00"
    return f"{feature} = {value}"
