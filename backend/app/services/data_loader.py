"""Load raw indicator tables from the database into the DataFrame format used by ml.features."""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AssessmentScore, AssignmentSubmission, AttendanceRecord, Course, EngagementWeekly, Student


def _df(db: Session, stmt, cols: list[str]) -> pd.DataFrame:
    rows = db.execute(stmt).all()
    return pd.DataFrame([tuple(r) for r in rows], columns=cols)


def load_frames(db: Session, student_ids: Iterable[int] | None = None) -> tuple[dict[str, pd.DataFrame], dict[str, int]]:
    """Return (frames, code_to_id)."""
    ids = list(student_ids) if student_ids is not None else None

    def scoped(stmt, col):
        return stmt.where(col.in_(ids)) if ids is not None else stmt

    students = _df(db, scoped(select(Student.id, Student.student_code, Student.prior_gpa), Student.id),
                   ["id", "student_code", "prior_gpa"])
    code_to_id = dict(zip(students["student_code"], students["id"], strict=True))

    att = _df(db, scoped(select(Student.student_code, Course.code, AttendanceRecord.date, AttendanceRecord.week,
                                AttendanceRecord.status)
                         .join(Student, Student.id == AttendanceRecord.student_id)
                         .join(Course, Course.id == AttendanceRecord.course_id), AttendanceRecord.student_id),
              ["student_code", "course_code", "date", "week", "status"])
    sc = _df(db, scoped(select(Student.student_code, Course.code, AssessmentScore.assessment_name, AssessmentScore.date,
                               AssessmentScore.week, AssessmentScore.score, AssessmentScore.max_score)
                        .join(Student, Student.id == AssessmentScore.student_id)
                        .join(Course, Course.id == AssessmentScore.course_id), AssessmentScore.student_id),
             ["student_code", "course_code", "assessment_name", "date", "week", "score", "max_score"])
    asg = _df(db, scoped(select(Student.student_code, Course.code, AssignmentSubmission.assignment_name,
                                AssignmentSubmission.due_date, AssignmentSubmission.week, AssignmentSubmission.status)
                         .join(Student, Student.id == AssignmentSubmission.student_id)
                         .join(Course, Course.id == AssignmentSubmission.course_id), AssignmentSubmission.student_id),
              ["student_code", "course_code", "assignment_name", "due_date", "week", "status"])
    eng = _df(db, scoped(select(Student.student_code, Course.code, EngagementWeekly.week, EngagementWeekly.week_start,
                                EngagementWeekly.logins, EngagementWeekly.activity_minutes)
                         .join(Student, Student.id == EngagementWeekly.student_id)
                         .join(Course, Course.id == EngagementWeekly.course_id), EngagementWeekly.student_id),
              ["student_code", "course_code", "week", "week_start", "logins", "activity_minutes"])

    frames = {"students": students, "attendance": att, "assessments": sc, "assignments": asg, "engagement": eng}
    return frames, code_to_id
