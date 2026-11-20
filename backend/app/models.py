"""ORM entities. Based on the SRS ERD (§7.4), extended for traceability, privacy and audit."""

from __future__ import annotations

import math
from datetime import UTC, date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class SafeFloat(TypeDecorator):
    """Float that stores NaN as NULL on every backend (SQLite does this implicitly; PostgreSQL keeps NaN,
    which then breaks JSON responses and SQL aggregates)."""

    impl = Float
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return None if isinstance(value, float) and math.isnan(value) else value

    def process_result_value(self, value, dialect):
        return None if isinstance(value, float) and math.isnan(value) else value


class Role:
    ADMIN = "admin"
    TEACHER = "teacher"
    ADVISOR = "advisor"
    STUDENT = "student"
    ANALYST = "analyst"
    ALL = (ADMIN, TEACHER, ADVISOR, STUDENT, ANALYST)
    STAFF = (ADMIN, TEACHER, ADVISOR)


# ---------------------------------------------------------------- identity
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Analysts may access identifiable data only if separately authorized (SRS §3).
    identifiable_access: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Student(Base):
    __tablename__ = "students"
    id: Mapped[int] = mapped_column(primary_key=True)
    student_code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(200))
    program: Mapped[str] = mapped_column(String(120), index=True)
    year_of_study: Mapped[int] = mapped_column(Integer)
    prior_gpa: Mapped[float | None] = mapped_column(SafeFloat)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), unique=True)
    advisor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    # Synthetic, evaluation-only attribute used for subgroup fairness checks. NEVER a model feature.
    equity_group: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user: Mapped[User | None] = relationship(foreign_keys=[user_id])
    advisor: Mapped[User | None] = relationship(foreign_keys=[advisor_id])
    enrollments: Mapped[list[Enrollment]] = relationship(back_populates="student", cascade="all, delete-orphan")


class Course(Base):
    __tablename__ = "courses"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    term: Mapped[str] = mapped_column(String(40))
    start_date: Mapped[date | None] = mapped_column(Date)
    teacher_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)

    teacher: Mapped[User | None] = relationship()


class Enrollment(Base):
    __tablename__ = "enrollments"
    __table_args__ = (UniqueConstraint("student_id", "course_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)

    student: Mapped[Student] = relationship(back_populates="enrollments")
    course: Mapped[Course] = relationship()


# ---------------------------------------------------------------- raw indicators
class AttendanceRecord(Base):
    __tablename__ = "attendance_records"
    __table_args__ = (UniqueConstraint("student_id", "course_id", "date"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date)
    week: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(10))  # present | late | absent | excused
    import_batch_id: Mapped[int | None] = mapped_column(ForeignKey("import_batches.id", ondelete="SET NULL"))


class AssessmentScore(Base):
    __tablename__ = "assessment_scores"
    __table_args__ = (UniqueConstraint("student_id", "course_id", "assessment_name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    assessment_name: Mapped[str] = mapped_column(String(120))
    date: Mapped[date] = mapped_column(Date)
    week: Mapped[int] = mapped_column(Integer)
    score: Mapped[float] = mapped_column(SafeFloat)
    max_score: Mapped[float] = mapped_column(SafeFloat)
    import_batch_id: Mapped[int | None] = mapped_column(ForeignKey("import_batches.id", ondelete="SET NULL"))


class AssignmentSubmission(Base):
    __tablename__ = "assignment_submissions"
    __table_args__ = (UniqueConstraint("student_id", "course_id", "assignment_name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    assignment_name: Mapped[str] = mapped_column(String(120))
    due_date: Mapped[date] = mapped_column(Date)
    week: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(10))  # on_time | late | missing
    import_batch_id: Mapped[int | None] = mapped_column(ForeignKey("import_batches.id", ondelete="SET NULL"))


class EngagementWeekly(Base):
    __tablename__ = "engagement_weekly"
    __table_args__ = (UniqueConstraint("student_id", "course_id", "week"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    week: Mapped[int] = mapped_column(Integer)
    week_start: Mapped[date] = mapped_column(Date)
    logins: Mapped[int] = mapped_column(Integer)
    activity_minutes: Mapped[int] = mapped_column(Integer)
    import_batch_id: Mapped[int | None] = mapped_column(ForeignKey("import_batches.id", ondelete="SET NULL"))


class ImportBatch(Base):
    __tablename__ = "import_batches"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(30))
    filename: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(60), default="csv_upload")
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(20))  # validated | rejected | committed
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    valid_rows: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[list] = mapped_column(JSON, default=list)
    content: Mapped[str | None] = mapped_column(Text)  # staged file content, cleared after commit
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    uploader: Mapped[User | None] = relationship()


# ---------------------------------------------------------------- AI outputs
class RiskAssessment(Base):
    __tablename__ = "risk_assessments"
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    # low | moderate | high | critical | insufficient_data | unavailable
    risk_level: Mapped[str] = mapped_column(String(20), index=True)
    probability: Mapped[float | None] = mapped_column(SafeFloat)
    rule_points: Mapped[int | None] = mapped_column(Integer)
    method: Mapped[str] = mapped_column(String(20))  # model | rules_fallback | none | unavailable
    model_version: Mapped[str | None] = mapped_column(String(60))
    reliable: Mapped[bool] = mapped_column(Boolean, default=True)
    data_as_of: Mapped[date | None] = mapped_column(Date)
    data_age_days: Mapped[int | None] = mapped_column(Integer)
    completeness: Mapped[float] = mapped_column(SafeFloat, default=0.0)
    missing_fields: Mapped[list] = mapped_column(JSON, default=list)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    factors: Mapped[list] = mapped_column(JSON, default=list)
    features: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    review_status: Mapped[str] = mapped_column(String(20), default="unreviewed")  # unreviewed|reviewed|flagged
    review_note: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    student: Mapped[Student] = relationship()


class ModelRegistry(Base):
    __tablename__ = "model_registry"
    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[str] = mapped_column(String(60), unique=True)
    algorithm: Mapped[str] = mapped_column(String(120))
    features: Mapped[list] = mapped_column(JSON, default=list)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    fairness: Mapped[dict] = mapped_column(JSON, default=dict)
    artifact_path: Mapped[str] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ---------------------------------------------------------------- support workflow
class RecommendationCatalog(Base):
    __tablename__ = "recommendation_catalog"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(40))
    trigger_codes: Mapped[list] = mapped_column(JSON, default=list)
    min_level: Mapped[str] = mapped_column(String(20), default="moderate")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Recommendation(Base):
    __tablename__ = "recommendations"
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), index=True)
    assessment_id: Mapped[int | None] = mapped_column(ForeignKey("risk_assessments.id", ondelete="SET NULL"))
    catalog_code: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(200))
    rationale: Mapped[str] = mapped_column(Text)
    score: Mapped[float] = mapped_column(SafeFloat, default=0.0)
    status: Mapped[str] = mapped_column(String(20), default="proposed")  # proposed | approved | dismissed
    edited_text: Mapped[str | None] = mapped_column(Text)
    review_note: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SupportPlan(Base):
    __tablename__ = "support_plans"
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), index=True)
    recommendation_id: Mapped[int | None] = mapped_column(ForeignKey("recommendations.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    due_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="planned")  # planned|in_progress|completed|cancelled
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    student: Mapped[Student] = relationship()
    owner: Mapped[User | None] = relationship(foreign_keys=[owner_id])
    interventions: Mapped[list[Intervention]] = relationship(
        back_populates="plan", cascade="all, delete-orphan", order_by="Intervention.performed_at"
    )


class Intervention(Base):
    __tablename__ = "interventions"
    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("support_plans.id", ondelete="CASCADE"), index=True)
    action_type: Mapped[str] = mapped_column(String(40))
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="scheduled")  # scheduled|done|missed
    outcome: Mapped[str | None] = mapped_column(Text)
    performed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    performed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    baseline_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    followup_snapshot: Mapped[dict | None] = mapped_column(JSON)

    plan: Mapped[SupportPlan] = relationship(back_populates="interventions")
    performer: Mapped[User | None] = relationship()


class StudentRequest(Base):
    __tablename__ = "student_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # help | correction | alert_flag
    subject: Mapped[str] = mapped_column(String(200))
    details: Mapped[str] = mapped_column(Text)
    target_record: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="open")  # open|in_review|resolved|rejected
    assigned_to: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    resolution: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    student: Mapped[Student] = relationship()
    assignee: Mapped[User | None] = relationship(foreign_keys=[assigned_to])


class StudyGoal(Base):
    __tablename__ = "study_goals"
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    target_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | achieved | dropped
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ---------------------------------------------------------------- governance
class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    actor_role: Mapped[str | None] = mapped_column(String(20))
    action: Mapped[str] = mapped_column(String(60), index=True)
    target_type: Mapped[str | None] = mapped_column(String(40))
    target_id: Mapped[str | None] = mapped_column(String(60))
    outcome: Mapped[str] = mapped_column(String(20), default="success", index=True)  # success|denied|error
    ip: Mapped[str | None] = mapped_column(String(64))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
