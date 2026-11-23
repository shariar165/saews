"""CSV import with validation (FR2 / AT-02).

Flow: upload -> validate (dry run, row-level error report) -> commit only if zero errors.
Every batch is recorded with filename, SHA-256, uploader and outcome for traceability.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import date

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    AssessmentScore,
    AssignmentSubmission,
    AttendanceRecord,
    Course,
    EngagementWeekly,
    Enrollment,
    Role,
    Student,
    User,
)

# column -> (type, required, options)
SPECS: dict[str, dict] = {
    "students": {
        "label": "Students",
        "roles": [Role.ADMIN],
        "columns": {
            "student_code": ("str", True, {"max": 40}),
            "full_name": ("str", True, {"max": 200}),
            "program": ("str", True, {"max": 120}),
            "year_of_study": ("int", True, {"min": 1, "max": 12}),  # class
            "prior_gpa": ("float", False, {"min": 0, "max": 5}),  # previous exam GPA (5.00 scale)
            "advisor_email": ("str", False, {"max": 255}),
        },
        "key": ["student_code"],
    },
    "enrollments": {
        "label": "Subject enrollments",
        "roles": [Role.ADMIN],
        "columns": {"student_code": ("str", True, {}), "course_code": ("str", True, {})},
        "key": ["student_code", "course_code"],
    },
    "attendance": {
        "label": "Attendance",
        "roles": [Role.ADMIN, Role.TEACHER],
        "columns": {
            "student_code": ("str", True, {}), "course_code": ("str", True, {}),
            "date": ("date", True, {}), "week": ("int", True, {"min": 1, "max": 30}),
            "status": ("enum", True, {"values": ["present", "late", "absent", "excused"]}),
        },
        "key": ["student_code", "course_code", "date"],
    },
    "assessments": {
        "label": "Class test / exam scores",
        "roles": [Role.ADMIN, Role.TEACHER],
        "columns": {
            "student_code": ("str", True, {}), "course_code": ("str", True, {}),
            "assessment_name": ("str", True, {"max": 120}), "date": ("date", True, {}),
            "week": ("int", True, {"min": 1, "max": 30}),
            "score": ("float", True, {"min": 0}), "max_score": ("float", True, {"min": 0.0001}),
        },
        "key": ["student_code", "course_code", "assessment_name"],
    },
    "assignments": {
        "label": "Homework submissions",
        "roles": [Role.ADMIN, Role.TEACHER],
        "columns": {
            "student_code": ("str", True, {}), "course_code": ("str", True, {}),
            "assignment_name": ("str", True, {"max": 120}), "due_date": ("date", True, {}),
            "week": ("int", True, {"min": 1, "max": 30}),
            "status": ("enum", True, {"values": ["on_time", "late", "missing"]}),
        },
        "key": ["student_code", "course_code", "assignment_name"],
    },
    "engagement": {
        "label": "Online learning portal activity (weekly)",
        "roles": [Role.ADMIN, Role.TEACHER],
        "columns": {
            "student_code": ("str", True, {}), "course_code": ("str", True, {}),
            "week": ("int", True, {"min": 1, "max": 30}), "week_start": ("date", True, {}),
            "logins": ("int", True, {"min": 0, "max": 1000}),
            "activity_minutes": ("int", True, {"min": 0, "max": 100000}),
        },
        "key": ["student_code", "course_code", "week"],
    },
}
INDICATOR_KINDS = {"attendance", "assessments", "assignments", "engagement"}
MAX_ERRORS = 200


@dataclass
class ValidationResult:
    total: int = 0
    rows: list[dict] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def add(self, row: int | None, column: str | None, message: str) -> None:
        if len(self.errors) < MAX_ERRORS:
            self.errors.append({"row": row, "column": column, "message": message})


def _parse(value: str, typ: str, opts: dict):
    v = value.strip()
    if typ == "str":
        if "max" in opts and len(v) > opts["max"]:
            raise ValueError(f"longer than {opts['max']} characters")
        return v
    if typ == "int":
        try:
            n = int(float(v))
            if float(v) != n:
                raise ValueError
        except ValueError:
            raise ValueError(f"'{v}' is not a whole number") from None
    elif typ == "float":
        try:
            n = float(v)
        except ValueError:
            raise ValueError(f"'{v}' is not a number") from None
    elif typ == "date":
        try:
            return date.fromisoformat(v)
        except ValueError:
            raise ValueError(f"'{v}' is not a valid date (use YYYY-MM-DD)") from None
    elif typ == "enum":
        if v.lower() not in opts["values"]:
            raise ValueError(f"'{v}' must be one of: {', '.join(opts['values'])}")
        return v.lower()
    else:  # pragma: no cover
        raise ValueError("unknown type")
    if "min" in opts and n < opts["min"]:
        raise ValueError(f"{n} is below the minimum of {opts['min']}")
    if "max" in opts and n > opts["max"]:
        raise ValueError(f"{n} is above the maximum of {opts['max']}")
    return n


def template_csv(kind: str) -> str:
    return ",".join(SPECS[kind]["columns"]) + "\n"


def validate_csv(db: Session, kind: str, content: str, user: User) -> ValidationResult:
    res = ValidationResult()
    spec = SPECS.get(kind)
    if spec is None:
        res.add(None, None, f"Unknown import type '{kind}'")
        return res
    try:
        df = pd.read_csv(io.StringIO(content), dtype=str, keep_default_na=False, skipinitialspace=True)
    except Exception as exc:  # noqa: BLE001
        res.add(None, None, f"File could not be parsed as CSV: {exc}")
        return res
    df.columns = [str(c).strip().lower() for c in df.columns]
    res.total = len(df)
    if df.empty:
        res.add(None, None, "The file contains no data rows")
        return res

    cols = spec["columns"]
    missing = [c for c, (_, req, _) in cols.items() if req and c not in df.columns]
    if missing:
        res.add(None, None, "Missing required column(s): " + ", ".join(missing))
        return res
    unknown = [c for c in df.columns if c not in cols]
    if unknown:
        res.add(None, None, "Unexpected column(s): " + ", ".join(unknown))
        return res

    students = {c: (i, adv) for c, i, adv in db.execute(select(Student.student_code, Student.id, Student.advisor_id))}
    courses = {c: (i, t) for c, i, t in db.execute(select(Course.code, Course.id, Course.teacher_id))}
    enrolled = set(db.execute(select(Enrollment.student_id, Enrollment.course_id)).all())
    advisors = {e.lower(): i for e, i in db.execute(select(User.email, User.id).where(User.role == Role.ADVISOR))}

    seen: dict[tuple, int] = {}
    for idx, raw in enumerate(df.to_dict("records")):
        line = idx + 2  # header is line 1
        clean: dict = {}
        row_ok = True
        for col, (typ, required, opts) in cols.items():
            value = str(raw.get(col, "") or "")
            if not value.strip():
                if required:
                    res.add(line, col, "Required value is missing")
                    row_ok = False
                clean[col] = None
                continue
            try:
                clean[col] = _parse(value, typ, opts)
            except ValueError as exc:
                res.add(line, col, str(exc))
                row_ok = False
        if not row_ok:
            continue

        key = tuple(clean[k] for k in spec["key"])
        if key in seen:
            res.add(line, None, f"Duplicate of row {seen[key]} ({', '.join(map(str, key))})")
            continue
        seen[key] = line

        # cross-reference checks
        if kind == "students":
            if clean.get("advisor_email") and clean["advisor_email"].lower() not in advisors:
                res.add(line, "advisor_email", "No advisor account with this email")
                continue
        else:
            st = students.get(clean["student_code"])
            co = courses.get(clean["course_code"])
            if st is None:
                res.add(line, "student_code", f"Unknown student '{clean['student_code']}'")
                continue
            if co is None:
                res.add(line, "course_code", f"Unknown course '{clean['course_code']}'")
                continue
            if user.role == Role.TEACHER and co[1] != user.id:
                res.add(line, "course_code", f"You are not the teacher of course '{clean['course_code']}'")
                continue
            if kind in INDICATOR_KINDS and (st[0], co[0]) not in enrolled:
                res.add(line, None, f"Student '{clean['student_code']}' is not enrolled in '{clean['course_code']}'")
                continue
            clean["student_id"], clean["course_id"] = st[0], co[0]
        if kind == "assessments" and clean["score"] > clean["max_score"]:
            res.add(line, "score", f"Score {clean['score']} exceeds max_score {clean['max_score']}")
            continue
        res.rows.append(clean)
    return res


def commit_rows(db: Session, kind: str, rows: list[dict], batch_id: int) -> set[int]:
    """Upsert validated rows. Returns affected student ids. Caller commits."""
    affected: set[int] = set()
    if kind == "students":
        advisors = {e.lower(): i for e, i in db.execute(select(User.email, User.id).where(User.role == Role.ADVISOR))}
        existing = {s.student_code: s for s in db.scalars(select(Student))}
        for r in rows:
            st = existing.get(r["student_code"]) or Student(student_code=r["student_code"])
            st.full_name, st.program, st.year_of_study = r["full_name"], r["program"], int(r["year_of_study"])
            if r.get("prior_gpa") is not None:
                st.prior_gpa = float(r["prior_gpa"])
            if r.get("advisor_email"):
                st.advisor_id = advisors[r["advisor_email"].lower()]
            db.add(st)
        db.flush()
        return {s.id for s in db.scalars(select(Student).where(Student.student_code.in_([r["student_code"] for r in rows])))}
    if kind == "enrollments":
        have = set(db.execute(select(Enrollment.student_id, Enrollment.course_id)).all())
        for r in rows:
            if (r["student_id"], r["course_id"]) not in have:
                db.add(Enrollment(student_id=r["student_id"], course_id=r["course_id"]))
            affected.add(r["student_id"])
        return affected

    model, key_col, fields = {
        "attendance": (AttendanceRecord, "date", ["date", "week", "status"]),
        "assessments": (AssessmentScore, "assessment_name", ["assessment_name", "date", "week", "score", "max_score"]),
        "assignments": (AssignmentSubmission, "assignment_name", ["assignment_name", "due_date", "week", "status"]),
        "engagement": (EngagementWeekly, "week", ["week", "week_start", "logins", "activity_minutes"]),
    }[kind]
    sids = {r["student_id"] for r in rows}
    existing = {
        (o.student_id, o.course_id, getattr(o, key_col)): o
        for o in db.scalars(select(model).where(model.student_id.in_(sids)))
    }
    for r in rows:
        obj = existing.get((r["student_id"], r["course_id"], r[key_col]))
        if obj is None:
            obj = model(student_id=r["student_id"], course_id=r["course_id"])
            db.add(obj)
        for f in fields:
            setattr(obj, f, r[f])
        obj.import_batch_id = batch_id
        affected.add(r["student_id"])
    return affected
