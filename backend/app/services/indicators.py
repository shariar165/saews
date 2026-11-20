"""Time series and snapshots of a student's indicators for dashboards (FR3) and follow-up (FR7)."""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ml.features import compute_features, feature_snapshot
from ..models import AssessmentScore, AssignmentSubmission, AttendanceRecord, Course, EngagementWeekly
from .data_loader import load_frames


def student_series(db: Session, student_id: int) -> dict:
    att_by_week: dict[int, list[int]] = defaultdict(list)
    for week, status in db.execute(select(AttendanceRecord.week, AttendanceRecord.status)
                                   .where(AttendanceRecord.student_id == student_id)):
        if status != "excused":
            att_by_week[week].append(1 if status in ("present", "late") else 0)
    attendance = [{"week": w, "rate": round(sum(v) / len(v), 3)} for w, v in sorted(att_by_week.items())]

    eng_by_week: dict[int, list[int]] = defaultdict(list)
    for week, logins in db.execute(select(EngagementWeekly.week, EngagementWeekly.logins)
                                   .where(EngagementWeekly.student_id == student_id)):
        eng_by_week[week].append(logins)
    engagement = [{"week": w, "logins": round(sum(v) / len(v), 2)} for w, v in sorted(eng_by_week.items())]

    scores = [
        {"course": c, "name": n, "week": w, "pct": round(100 * s / m, 1), "date": d.isoformat()}
        for c, n, w, s, m, d in db.execute(
            select(Course.code, AssessmentScore.assessment_name, AssessmentScore.week, AssessmentScore.score,
                   AssessmentScore.max_score, AssessmentScore.date)
            .join(Course, Course.id == AssessmentScore.course_id)
            .where(AssessmentScore.student_id == student_id).order_by(AssessmentScore.week))
    ]
    assignments = defaultdict(int)
    for (status,) in db.execute(select(AssignmentSubmission.status).where(AssignmentSubmission.student_id == student_id)):
        assignments[status] += 1
    return {
        "attendance": attendance,
        "engagement": engagement,
        "scores": scores,
        "assignments": {k: assignments.get(k, 0) for k in ("on_time", "late", "missing")},
    }


def snapshot(db: Session, student_id: int) -> dict:
    """Current feature values — stored on interventions to compare before/after."""
    frames, _ = load_frames(db, [student_id])
    feats = compute_features(frames)
    if feats.empty:
        return {}
    row = feats.iloc[0]
    snap = feature_snapshot(row)
    snap["data_as_of"] = row["data_as_of"].isoformat() if row["data_as_of"] else None
    return snap
