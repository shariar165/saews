"""Unit tests: security, features, rules, explanations, recommendations, validation."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from backend.app.core.security import create_access_token, decode_access_token, hash_password, verify_password
from backend.app.ml.explain import describe
from backend.app.ml.features import FEATURES, compute_features
from backend.app.ml.rules import evaluate_rules
from backend.app.models import RiskAssessment
from backend.app.services.imports import _parse
from backend.app.services.recommendations import propose_for_assessment


def test_password_hashing_is_argon2_and_verifies():
    h = hash_password("CorrectHorse!42")
    assert h.startswith("$argon2id$")
    assert verify_password("CorrectHorse!42", h)
    assert not verify_password("wrong", h)
    assert not verify_password("x", "not-a-hash")


def test_tokens_roundtrip_and_reject_tampering():
    t = create_access_token(7, "teacher")
    assert decode_access_token(t)["sub"] == "7"
    assert decode_access_token(t[:-2] + "xx") is None


def _frames():
    d0 = date(2026, 9, 7)
    att = [{"student_code": "A", "course_code": "C", "date": date(2026, 9, 7 + w * 7 % 60 if False else 7), "week": w,
            "status": "present" if w <= 4 else "absent"} for w in range(1, 9)]
    for i, r in enumerate(att):
        r["date"] = pd.Timestamp(d0) + pd.Timedelta(days=7 * i)
    sc = [{"student_code": "A", "course_code": "C", "assessment_name": f"Q{w}", "date": pd.Timestamp(d0) + pd.Timedelta(days=7 * w),
           "week": w, "score": s, "max_score": 20.0} for w, s in [(2, 18), (4, 16), (6, 8), (8, 6)]]
    asg = [{"student_code": "A", "course_code": "C", "assignment_name": f"A{i}", "due_date": pd.Timestamp(d0), "week": i,
            "status": st} for i, st in enumerate(["on_time", "late", "missing", "missing"], 1)]
    eng = [{"student_code": "A", "course_code": "C", "week": w, "week_start": pd.Timestamp(d0) + pd.Timedelta(days=7 * (w - 1)),
            "logins": 6 if w <= 5 else 1, "activity_minutes": 60} for w in range(1, 9)]
    students = pd.DataFrame([{"student_code": "A", "prior_gpa": 2.9}, {"student_code": "B", "prior_gpa": None}])
    return {"students": students, "attendance": pd.DataFrame(att), "assessments": pd.DataFrame(sc),
            "assignments": pd.DataFrame(asg), "engagement": pd.DataFrame(eng)}


def test_compute_features_values_and_quality():
    f = compute_features(_frames(), as_of=date(2026, 11, 20))
    a = f.loc["A"]
    assert a["attendance_rate"] == 0.5
    assert a["attendance_trend"] == -1.0  # last 4 weeks all absent vs earlier all present
    assert round(a["avg_score"], 1) == 60.0
    assert a["score_trend"] < -40
    assert a["missing_rate"] == 0.5 and a["late_rate"] == 0.25
    assert a["engagement_change"] < -0.5
    assert a["completeness"] == 1.0 and a["missing_groups"] == []
    b = f.loc["B"]
    assert b["completeness"] == 0.0 and set(b["missing_groups"]) == {"attendance", "assessments", "assignments", "engagement", "prior_gpa"}
    assert list(f.columns[: len(FEATURES)]) == FEATURES


def test_rules_engine_levels_and_no_double_counting():
    pts, level, factors = evaluate_rules({"attendance_rate": 0.5, "avg_score": 45, "missing_rate": 0.5, "engagement_change": -0.8})
    assert pts == 2 + 2 + 2 + 1 and level == "critical"
    assert len([f for f in factors if f["feature"] == "attendance_rate"]) == 1
    assert evaluate_rules({"attendance_rate": 0.95, "avg_score": 80})[1] == "low"
    assert evaluate_rules({"attendance_rate": None, "avg_score": np.nan})[0] == 0


def test_explanations_are_plain_language():
    assert describe("attendance_rate", 0.64) == "Attendance is 64% across enrolled subjects"
    assert "−" not in describe("attendance_trend", -0.2) and "-20" in describe("attendance_trend", -0.2)
    assert describe("avg_score", None).endswith("no data")


def test_recommendations_follow_factors_and_level(db):
    from sqlalchemy import select

    from backend.app.models import Student

    st = db.scalar(select(Student).where(Student.student_code == "S20260010"))
    ra = RiskAssessment(student_id=st.id, risk_level="low", method="model", factors=[])
    assert propose_for_assessment(db, ra) == []
    ra = RiskAssessment(student_id=st.id, risk_level="critical", method="model", factors=[
        {"code": "LOW_ATTENDANCE", "label": "Attendance is 50%", "contribution": 1.2},
        {"code": "MISSING_WORK", "label": "40% missing", "contribution": 0.8}])
    db.add(ra)
    db.flush()
    codes = {r.catalog_code for r in propose_for_assessment(db, ra)}
    db.rollback()
    assert "ATTENDANCE_FOLLOWUP" in codes and "ADVISOR_MEETING" in codes and "WELLBEING_INFO" in codes
    assert "TUTORING" not in codes  # no LOW_SCORES factor


def test_import_field_parsing():
    assert _parse("2026-10-01", "date", {}) == date(2026, 10, 1)
    assert _parse("Present", "enum", {"values": ["present", "absent"]}) == "present"
    for bad, typ, opts in [("abc", "int", {}), ("3.5", "int", {}), ("2026-02-30", "date", {}), ("-1", "float", {"min": 0})]:
        try:
            _parse(bad, typ, opts)
        except ValueError:
            continue
        raise AssertionError(f"{bad!r} should be rejected as {typ}")
