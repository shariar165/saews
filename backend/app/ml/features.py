"""Feature engineering shared by training (historical cohort) and live scoring (database).

Input is a dict of DataFrames using the same column names as the CSV import formats:
  students:    student_code, prior_gpa
  attendance:  student_code, course_code, date, week, status
  assessments: student_code, course_code, assessment_name, date, week, score, max_score
  assignments: student_code, course_code, assignment_name, due_date, week, status
  engagement:  student_code, course_code, week, week_start, logins, activity_minutes

Only approved academic and engagement indicators are used. Demographic or sensitive
attributes are never features (SRS §1.3, §6.2).
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

FEATURES: list[str] = [
    "attendance_rate",
    "attendance_trend",
    "avg_score",
    "score_trend",
    "missing_rate",
    "late_rate",
    "engagement_change",
    "avg_logins",
    "prior_gpa",
]

# Feature -> data group (used for completeness / missing-data warnings)
FEATURE_GROUP = {
    "attendance_rate": "attendance",
    "attendance_trend": "attendance",
    "avg_score": "assessments",
    "score_trend": "assessments",
    "missing_rate": "assignments",
    "late_rate": "assignments",
    "engagement_change": "engagement",
    "avg_logins": "engagement",
    "prior_gpa": "prior_gpa",
}
DATA_GROUPS = ["attendance", "assessments", "assignments", "engagement", "prior_gpa"]

RECENT_WEEKS = 4


def _empty(cols: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=cols)


def _recent_vs_earlier(df: pd.DataFrame, value_col: str, recent_weeks: int) -> pd.DataFrame:
    """Per student: overall mean, recent-window mean and earlier-window mean of ``value_col``."""
    if df.empty:
        return pd.DataFrame(columns=["overall", "recent", "earlier"])
    df = df.copy()
    df["max_week"] = df.groupby("student_code")["week"].transform("max")
    df["is_recent"] = df["week"] > (df["max_week"] - recent_weeks)
    overall = df.groupby("student_code")[value_col].mean().rename("overall")
    split = df.groupby(["student_code", "is_recent"])[value_col].mean().unstack()
    recent = split.get(True, pd.Series(dtype=float)).rename("recent")
    earlier = split.get(False, pd.Series(dtype=float)).rename("earlier")
    return pd.concat([overall, recent, earlier], axis=1)


def compute_features(frames: dict[str, pd.DataFrame], as_of: date | None = None) -> pd.DataFrame:
    """Return one row per student_code with FEATURES plus data-quality metadata columns:
    ``completeness``, ``missing_groups`` (list), ``data_as_of`` (date|None), ``data_age_days``."""
    as_of = as_of or date.today()
    students = frames.get("students", _empty(["student_code", "prior_gpa"]))
    out = pd.DataFrame(index=pd.Index(students["student_code"].astype(str).unique(), name="student_code"))

    latest_dates: list[pd.Series] = []

    # --- attendance: present/late count as attended; excused sessions are excluded
    att = frames.get("attendance", _empty(["student_code", "week", "status", "date"]))
    att = att[att["status"] != "excused"].copy() if not att.empty else att
    if not att.empty:
        att["attended"] = att["status"].isin(["present", "late"]).astype(float)
        a = _recent_vs_earlier(att, "attended", RECENT_WEEKS)
        out["attendance_rate"] = a["overall"]
        out["attendance_trend"] = a["recent"] - a["earlier"]
        latest_dates.append(pd.to_datetime(att["date"]).groupby(att["student_code"]).max())

    # --- assessments: percentage scores; trend = last two assessments vs earlier ones
    sc = frames.get("assessments", _empty(["student_code", "week", "score", "max_score", "date"]))
    if not sc.empty:
        sc = sc.copy()
        sc["pct"] = 100.0 * sc["score"].astype(float) / sc["max_score"].astype(float)
        sc = sc.sort_values(["student_code", "week"])
        sc["rank_desc"] = sc.groupby("student_code")["week"].rank(method="first", ascending=False)
        sc["is_recent"] = sc["rank_desc"] <= 2
        out["avg_score"] = sc.groupby("student_code")["pct"].mean()
        split = sc.groupby(["student_code", "is_recent"])["pct"].mean().unstack()
        if True in split and False in split:
            out["score_trend"] = split[True] - split[False]
        latest_dates.append(pd.to_datetime(sc["date"]).groupby(sc["student_code"]).max())

    # --- assignments
    asg = frames.get("assignments", _empty(["student_code", "status", "due_date"]))
    if not asg.empty:
        g = asg.groupby("student_code")["status"]
        out["missing_rate"] = g.apply(lambda s: float((s == "missing").mean()))
        out["late_rate"] = g.apply(lambda s: float((s == "late").mean()))
        latest_dates.append(pd.to_datetime(asg["due_date"]).groupby(asg["student_code"]).max())

    # --- engagement: logins per course-week; change = recent 3 weeks vs earlier, relative
    eng = frames.get("engagement", _empty(["student_code", "week", "logins", "week_start"]))
    if not eng.empty:
        eng = eng.copy()
        eng["logins"] = eng["logins"].astype(float)
        e = _recent_vs_earlier(eng, "logins", 3)
        out["avg_logins"] = e["overall"]
        change = (e["recent"] - e["earlier"]) / e["earlier"].clip(lower=0.5)
        out["engagement_change"] = change.clip(-1.0, 3.0)
        latest_dates.append(
            (pd.to_datetime(eng["week_start"]) + pd.Timedelta(days=6)).groupby(eng["student_code"]).max()
        )

    # --- prior GPA
    if "prior_gpa" in students:
        gpa = pd.to_numeric(students.set_index(students["student_code"].astype(str))["prior_gpa"], errors="coerce")
        out["prior_gpa"] = gpa[~gpa.index.duplicated()]

    for f in FEATURES:
        if f not in out:
            out[f] = np.nan
    out = out[FEATURES].astype(float)

    # --- data-quality metadata
    group_present = pd.DataFrame(index=out.index)
    for grp in DATA_GROUPS:
        cols = [f for f, g in FEATURE_GROUP.items() if g == grp]
        group_present[grp] = out[cols].notna().any(axis=1)
    out["completeness"] = group_present.mean(axis=1)
    out["missing_groups"] = group_present.apply(lambda r: [g for g in DATA_GROUPS if not r[g]], axis=1)

    if latest_dates:
        latest = pd.concat(latest_dates, axis=1).max(axis=1)
        latest = latest.reindex(out.index)
        out["data_as_of"] = latest.apply(lambda t: t.date() if pd.notna(t) else None)
    else:
        out["data_as_of"] = None
    out["data_age_days"] = out["data_as_of"].apply(lambda d: (as_of - d).days if d else None)
    return out


def feature_snapshot(row: pd.Series) -> dict:
    """JSON-safe dict of feature values (None for missing)."""
    return {f: (None if pd.isna(row[f]) else round(float(row[f]), 4)) for f in FEATURES}
