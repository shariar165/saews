r"""Create the database schema and load a synthetic demo school & college.

    .\.venv\Scripts\python.exe -m backend.app.seed.generate [--students 300] [--reset]

All people and records are fictional. Demo accounts share the password printed below.
"""

from __future__ import annotations

import argparse
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..api.meta import DEMO_PASSWORD
from ..config import PROJECT_ROOT, get_settings
from ..core.security import hash_password
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
from ..services.recommendations import ensure_catalog
from .synthetic import COURSES, generate_cohort, level_of, term_start_for

TEACHER_COURSES = {
    # Mathematics, science and accounting. College Humanities students take none of these, so they are
    # outside teacher1's scope (used by the access-control acceptance test AT-01).
    "teacher1@saews.demo": ["SSC-MATH", "SSC-PHY", "SSC-CHEM", "SSC-ACC",
                            "HSC-PHY", "HSC-CHEM", "HSC-ACC"],
    # Languages, ICT, business and humanities
    "teacher2@saews.demo": ["SSC-BAN", "SSC-ENG", "SSC-FIN", "SSC-HIST", "SSC-GEO",
                            "HSC-BAN", "HSC-ENG", "HSC-ICT", "HSC-BOM", "HSC-CIV", "HSC-ECO"],
}
DEMO_USERS = [
    ("admin@saews.demo", "Nadia Admin", Role.ADMIN),
    ("teacher1@saews.demo", "Hasan Teacher", Role.TEACHER),
    ("teacher2@saews.demo", "Farzana Teacher", Role.TEACHER),
    ("advisor1@saews.demo", "Kamrul Advisor", Role.ADVISOR),
    ("advisor2@saews.demo", "Shirin Advisor", Role.ADVISOR),
    ("analyst@saews.demo", "Imtiaz Analyst", Role.ANALYST),
    ("student@saews.demo", None, Role.STUDENT),  # name taken from the linked student record
]


def run_migrations() -> None:
    from alembic.config import Config

    from alembic import command

    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", get_settings().database_url)
    command.upgrade(cfg, "head")


def seed(db: Session, n_students: int = 300, seed_value: int = 42, today: date | None = None) -> dict:
    today = today or date.today()
    if db.scalar(select(User.id).limit(1)) is not None:
        raise RuntimeError("Database already contains data. Use --reset to recreate it.")
    pw = hash_password(DEMO_PASSWORD)

    users: dict[str, User] = {}
    for email, name, role in DEMO_USERS:
        u = User(email=email, full_name=name or "Student", role=role, password_hash=pw)
        db.add(u)
        users[email] = u
    db.flush()

    start = term_start_for(today)
    term = f"Second Term {start.year}"
    courses: dict[str, Course] = {}
    for email, codes in TEACHER_COURSES.items():
        for code in codes:
            c = Course(code=code, title=COURSES[code], term=term, start_date=start, teacher_id=users[email].id)
            db.add(c)
            courses[code] = c
    db.flush()

    cohort = generate_cohort(n_students, seed=seed_value, term_start=start, special_cases=True)
    students: dict[str, Student] = {}
    for r in cohort.students.to_dict("records"):
        # Class advisors: advisor1 for school (Class 9-10), advisor2 for college (Class 11-12).
        advisor = users["advisor1@saews.demo"] if level_of(r["program"]) == "School" else users["advisor2@saews.demo"]
        st = Student(student_code=r["student_code"], full_name=r["full_name"], program=r["program"],
                     year_of_study=r["year_of_study"], prior_gpa=r["prior_gpa"], advisor_id=advisor.id,
                     equity_group=r["equity_group"])
        db.add(st)
        students[st.student_code] = st
    db.flush()

    # Demo student login -> the first (declining) student.
    first = students[cohort.students.iloc[0]["student_code"]]
    first.user_id = users["student@saews.demo"].id
    users["student@saews.demo"].full_name = first.full_name

    sid = {c: s.id for c, s in students.items()}
    cid = {c: x.id for c, x in courses.items()}
    db.bulk_insert_mappings(Enrollment, [{"student_id": sid[r["student_code"]], "course_id": cid[r["course_code"]]}
                                         for r in cohort.enrollments.to_dict("records")])

    def rows(df, extra):
        return [{"student_id": sid[r["student_code"]], "course_id": cid[r["course_code"]],
                 **{k: r[k] for k in extra}} for r in df.to_dict("records")]

    db.bulk_insert_mappings(AttendanceRecord, rows(cohort.attendance, ["date", "week", "status"]))
    db.bulk_insert_mappings(AssessmentScore, rows(cohort.assessments,
                                                  ["assessment_name", "date", "week", "score", "max_score"]))
    db.bulk_insert_mappings(AssignmentSubmission, rows(cohort.assignments,
                                                       ["assignment_name", "due_date", "week", "status"]))
    db.bulk_insert_mappings(EngagementWeekly, rows(cohort.engagement,
                                                   ["week", "week_start", "logins", "activity_minutes"]))
    ensure_catalog(db)
    db.commit()
    return {"students": len(students), "courses": len(courses), "attendance_rows": len(cohort.attendance),
            "term_start": start.isoformat()}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--students", type=int, default=300)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--reset", action="store_true", help="delete the SQLite database file first")
    p.add_argument("--skip-assess", action="store_true")
    args = p.parse_args()

    s = get_settings()
    if args.reset and s.database_url.startswith("sqlite:///"):
        from pathlib import Path

        from ..database import engine

        engine.dispose()
        db_path = Path(s.database_url.removeprefix("sqlite:///"))
        for suffix in ("", "-wal", "-shm"):
            Path(str(db_path) + suffix).unlink(missing_ok=True)
    if s.database_url.startswith("sqlite:///"):
        from pathlib import Path

        Path(s.database_url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)

    run_migrations()
    from ..database import SessionLocal

    with SessionLocal() as db:
        info = seed(db, args.students, args.seed)
        print(f"Seeded {info['students']} students, {info['courses']} courses "
              f"({info['attendance_rows']} attendance rows), term start {info['term_start']}.")
        if not args.skip_assess:
            from ..services.risk_engine import assess_students

            results = assess_students(db)
            by_method: dict[str, int] = {}
            for r in results:
                by_method[r.method] = by_method.get(r.method, 0) + 1
            print(f"Initial risk assessment: {len(results)} students, methods: {by_method}")
    print(f"\nDemo password for all accounts: {DEMO_PASSWORD}")
    for email, _, role in DEMO_USERS:
        print(f"  {role:<8} {email}")


if __name__ == "__main__":
    main()
