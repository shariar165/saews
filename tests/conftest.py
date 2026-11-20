"""Test fixtures: an isolated SQLite database and model directory per test session.

Environment variables are set BEFORE the application is imported so settings, engine
and rate limiter pick them up.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="saews_test_"))
os.environ["EWS_DATABASE_URL"] = f"sqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ["EWS_MODEL_DIR"] = str(_TMP / "model")
os.environ["EWS_RATE_LIMIT_ENABLED"] = "false"
os.environ["EWS_JWT_SECRET"] = "test-secret-not-for-production-0123456789"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from backend.app.api.meta import DEMO_PASSWORD  # noqa: E402
from backend.app.database import Base, SessionLocal, engine  # noqa: E402
from backend.app.main import app  # noqa: E402
from backend.app.ml.model import reset_cache  # noqa: E402
from backend.app.ml.train import train_model  # noqa: E402
from backend.app.models import Student, User  # noqa: E402
from backend.app.seed.generate import seed  # noqa: E402
from backend.app.services.risk_engine import assess_students  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _database():
    Base.metadata.create_all(engine)
    train_model(n_students=500, seed=3, verbose=False)
    with SessionLocal() as db:
        seed(db, n_students=60, seed_value=11)
        assess_students(db)
    yield
    reset_cache()
    engine.dispose()


@pytest.fixture()
def db():
    with SessionLocal() as session:
        yield session


@pytest.fixture()
def client():
    return TestClient(app)


def login(client: TestClient, email: str, password: str = DEMO_PASSWORD) -> TestClient:
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return client


@pytest.fixture()
def as_role(client):
    def _as(email: str) -> TestClient:
        c = TestClient(app)
        return login(c, email)
    return _as


def student_not_taught_by(db, teacher_email: str) -> Student:
    """A student with no enrollment in any course taught by this teacher."""
    from backend.app.models import Course, Enrollment

    teacher = db.scalar(select(User).where(User.email == teacher_email))
    taught = select(Enrollment.student_id).join(Course).where(Course.teacher_id == teacher.id)
    return db.scalar(select(Student).where(Student.id.not_in(taught)).limit(1))


def student_taught_by(db, teacher_email: str) -> Student:
    from backend.app.models import Course, Enrollment

    teacher = db.scalar(select(User).where(User.email == teacher_email))
    return db.scalar(select(Student).join(Enrollment).join(Course).where(Course.teacher_id == teacher.id).limit(1))
