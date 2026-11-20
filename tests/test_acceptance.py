"""Acceptance tests mapped to SRS Appendix A (AT-01 .. AT-08)."""

from __future__ import annotations

import io

from sqlalchemy import func, select

from backend.app.ml import model as model_service
from backend.app.models import (
    AttendanceRecord,
    AuditLog,
    Recommendation,
    Student,
    StudentRequest,
    SupportPlan,
    User,
)
from backend.app.services.risk_engine import assess_students

from .conftest import student_not_taught_by, student_taught_by


# AT-01 ------------------------------------------------------------------------------------------
def test_at01_unauthorized_profile_access_is_denied_and_logged(as_role, db):
    other = student_not_taught_by(db, "teacher1@saews.demo")
    assert other is not None
    c = as_role("teacher1@saews.demo")
    r = c.get(f"/api/students/{other.id}")
    assert r.status_code == 403
    entry = db.scalar(select(AuditLog).where(AuditLog.action == "student.view", AuditLog.outcome == "denied",
                                             AuditLog.target_id == str(other.id)))
    assert entry is not None and entry.actor_role == "teacher"


def test_at01_student_cannot_view_other_students_or_staff_endpoints(as_role, db):
    c = as_role("student@saews.demo")
    assert c.get("/api/students/2").status_code == 403  # staff-only endpoint, role check
    assert c.get("/api/risk/alerts").status_code == 403
    assert c.get("/api/me/profile").status_code == 200


def test_at01_analyst_cannot_open_individual_profile(as_role, db):
    st = db.scalar(select(Student).limit(1))
    assert as_role("analyst@saews.demo").get(f"/api/students/{st.id}").status_code == 403


def test_unauthenticated_requests_are_rejected(client):
    assert client.get("/api/students").status_code == 401
    assert client.get("/api/me/profile").status_code == 401


def test_teacher_sees_own_students(as_role, db):
    st = student_taught_by(db, "teacher1@saews.demo")
    r = as_role("teacher1@saews.demo").get(f"/api/students/{st.id}")
    assert r.status_code == 200
    assert r.json()["student_code"] == st.student_code


# AT-02 ------------------------------------------------------------------------------------------
def _upload(c, kind: str, csv_text: str, name: str = "data.csv"):
    return c.post("/api/imports/validate", data={"kind": kind},
                  files={"file": (name, io.BytesIO(csv_text.encode()), "text/csv")})


def test_at02_missing_columns_rejected(as_role, db):
    c = as_role("admin@saews.demo")
    r = _upload(c, "attendance", "student_code,course_code,date\nS20260001,SE331,2026-10-01\n")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "rejected"
    assert "Missing required column" in body["errors"][0]["message"]
    assert c.post(f"/api/imports/{body['id']}/commit").status_code == 409


def test_at02_invalid_rows_reported_and_nothing_saved(as_role, db):
    st = db.scalar(select(Student).where(Student.student_code == "S20260004"))
    course = st.enrollments[0].course.code
    before = db.scalar(select(func.count()).select_from(AttendanceRecord))
    csv_text = (
        "student_code,course_code,date,week,status\n"
        f"{st.student_code},{course},2026-13-01,3,present\n"   # bad date
        f"{st.student_code},{course},2026-10-01,3,sleeping\n"   # bad enum
        f"UNKNOWN,{course},2026-10-01,3,present\n"             # unknown student
        f"{st.student_code},{course},2026-10-02,99,present\n"   # week out of range
        f"{st.student_code},{course},2026-10-03,3,present\n"    # valid
        f"{st.student_code},{course},2026-10-03,3,absent\n"     # duplicate key
    )
    body = _upload(as_role("admin@saews.demo"), "attendance", csv_text).json()
    assert body["status"] == "rejected"
    lines = {e["row"] for e in body["errors"]}
    assert lines == {2, 3, 4, 5, 7}
    after = db.scalar(select(func.count()).select_from(AttendanceRecord))
    assert after == before


def test_at02_valid_file_commits_and_teacher_scope_enforced(as_role, db):
    st = student_taught_by(db, "teacher1@saews.demo")
    teacher = db.scalar(select(User).where(User.email == "teacher1@saews.demo"))
    course = next(e.course.code for e in st.enrollments if e.course.teacher_id == teacher.id)
    other_course = next((e.course.code for e in st.enrollments if e.course.teacher_id != teacher.id), None)
    c = as_role("teacher1@saews.demo")
    ok = _upload(c, "attendance", f"student_code,course_code,date,week,status\n{st.student_code},{course},2026-11-30,11,present\n").json()
    assert ok["status"] == "validated", ok
    r = c.post(f"/api/imports/{ok['id']}/commit")
    assert r.status_code == 200 and r.json()["status"] == "committed"
    if other_course:
        bad = _upload(c, "attendance", f"student_code,course_code,date,week,status\n{st.student_code},{other_course},2026-11-30,11,present\n").json()
        assert bad["status"] == "rejected"
        assert "not the teacher" in bad["errors"][0]["message"]


def test_at02_non_csv_rejected(as_role):
    r = _upload(as_role("admin@saews.demo"), "attendance", "x", name="data.xlsx")
    assert r.status_code == 422


# AT-03 ------------------------------------------------------------------------------------------
def test_at03_assessment_has_level_timestamp_version_and_factors(as_role, db):
    st = db.scalar(select(Student).where(Student.student_code == "S20260001"))  # declining demo student
    a = as_role("admin@saews.demo").post(f"/api/students/{st.id}/assess").json()
    assert a["risk_level"] in {"low", "moderate", "high", "critical"}
    assert a["method"] == "model" and a["model_version"].startswith("lr-")
    assert a["created_at"] and a["data_as_of"]
    assert 0 <= a["probability"] <= 1
    assert a["factors"], "a declining student should have contributing factors"
    assert all("label" in f and f["contribution"] > 0 for f in a["factors"])


# AT-04 ------------------------------------------------------------------------------------------
def test_at04_missing_data_gives_no_prediction(db):
    st = db.scalar(select(Student).where(Student.student_code == "S20260002"))  # enrolled, no records
    [ra] = assess_students(db, [st.id])
    assert ra.risk_level == "insufficient_data"
    assert ra.probability is None and ra.reliable is False
    assert any("Not enough validated data" in w for w in ra.warnings)


def test_at04_stale_data_is_flagged_provisional(db):
    st = db.scalar(select(Student).where(Student.student_code == "S20260003"))  # data stops at week 4
    [ra] = assess_students(db, [st.id])
    assert ra.reliable is False
    assert ra.data_age_days > 21
    assert any("days old" in w for w in ra.warnings)


# AT-05 ------------------------------------------------------------------------------------------
def test_at05_model_unavailable_uses_labelled_rule_fallback(db, monkeypatch):
    def broken():
        raise model_service.ModelUnavailable("simulated outage")

    monkeypatch.setattr(model_service, "load_active_model", broken)
    st = db.scalar(select(Student).where(Student.student_code == "S20260001"))
    [ra] = assess_students(db, [st.id])
    assert ra.method == "rules_fallback"
    assert ra.model_version == "rules-v1" and ra.probability is None
    assert any("fallback" in w for w in ra.warnings)
    assert "simulated outage" in (ra.error or "")


def test_at05_both_engines_failing_marks_unavailable(db, monkeypatch):
    from backend.app.services import risk_engine

    monkeypatch.setattr(model_service, "load_active_model",
                        lambda: (_ for _ in ()).throw(model_service.ModelUnavailable("down")))
    monkeypatch.setattr(risk_engine, "evaluate_rules", lambda f: (_ for _ in ()).throw(RuntimeError("rules down")))
    st = db.scalar(select(Student).where(Student.student_code == "S20260001"))
    [ra] = assess_students(db, [st.id])
    assert ra.risk_level == "unavailable" and ra.method == "unavailable"


def test_at05_corrupt_registry_is_handled(tmp_path, monkeypatch):
    from backend.app.config import get_settings

    (tmp_path / "registry.json").write_text("{not json")
    monkeypatch.setattr(get_settings(), "model_dir", str(tmp_path))
    status = model_service.model_status()
    assert status["available"] is False and "unreadable" in status["error"]


# AT-06 ------------------------------------------------------------------------------------------
def test_at06_approving_recommendation_saves_plan_owner_due_date_status(as_role, db):
    teacher = db.scalar(select(User).where(User.email == "teacher1@saews.demo"))
    advisor = db.scalar(select(User).where(User.email == "advisor1@saews.demo"))
    from backend.app.models import Course, Enrollment

    taught = select(Enrollment.student_id).join(Course).where(Course.teacher_id == teacher.id)
    rec = db.scalar(select(Recommendation).where(Recommendation.status == "proposed",
                                                 Recommendation.student_id.in_(taught)).limit(1))
    assert rec is not None, "seed data should produce proposed recommendations"
    c = as_role("teacher1@saews.demo")
    r = c.post(f"/api/recommendations/{rec.id}/approve",
               json={"edited_text": "Weekly tutoring on Tuesdays", "owner_id": advisor.id, "due_date": "2026-12-15"})
    assert r.status_code == 200, r.text
    plan = r.json()["plan"]
    assert plan["owner"]["id"] == advisor.id and plan["due_date"] == "2026-12-15" and plan["status"] == "planned"
    db.expire_all()
    saved = db.get(SupportPlan, plan["id"])
    assert saved.recommendation_id == rec.id and saved.description == "Weekly tutoring on Tuesdays"
    # second approval is rejected
    assert c.post(f"/api/recommendations/{rec.id}/approve", json={}).status_code == 409


def test_intervention_records_baseline_and_followup(as_role, db):
    plan = db.scalar(select(SupportPlan).limit(1))
    if plan is None:
        st = student_taught_by(db, "teacher1@saews.demo")
        plan_id = as_role("teacher1@saews.demo").post("/api/plans", json={"student_id": st.id, "title": "Check-in"}).json()["id"]
    else:
        plan_id = plan.id
    owner_email = "admin@saews.demo"
    c = as_role(owner_email)
    p = c.post(f"/api/plans/{plan_id}/interventions", json={"action_type": "advisor_meeting", "notes": "Met"}).json()
    iv = p["interventions"][-1]
    assert iv["baseline_snapshot"].get("attendance_rate") is not None or iv["baseline_snapshot"] == {}
    p2 = c.patch(f"/api/interventions/{iv['id']}", json={"status": "done", "outcome": "Agreed study plan"}).json()
    assert p2["interventions"][-1]["followup_snapshot"] is not None
    assert p["status"] == "in_progress"


def test_students_only_see_approved_recommendations(as_role, db):
    st = db.scalar(select(Student).where(Student.student_code == "S20260001"))
    proposed = db.scalars(select(Recommendation).where(Recommendation.student_id == st.id,
                                                       Recommendation.status == "proposed")).all()
    support = as_role("student@saews.demo").get("/api/me/support").json()
    shown = {r["id"] for r in support["recommendations"]}
    assert not shown & {r.id for r in proposed}


# AT-07 ------------------------------------------------------------------------------------------
def test_at07_correction_request_logged_and_routed(as_role, db):
    c = as_role("student@saews.demo")
    r = c.post("/api/me/requests", json={"kind": "correction", "subject": "Wrong attendance",
                                         "details": "I attended SE331 in week 7", "target_record": "SE331 week 7"})
    assert r.status_code == 201, r.text
    req_id = r.json()["id"]
    db.expire_all()
    req = db.get(StudentRequest, req_id)
    st = db.get(Student, req.student_id)
    assert req.assigned_to == st.advisor_id is not None
    assert db.scalar(select(AuditLog).where(AuditLog.action == "request.correction.create",
                                            AuditLog.target_id == str(req_id))) is not None
    advisor = db.get(User, st.advisor_id)
    inbox = as_role(advisor.email).get("/api/requests").json()["items"]
    assert any(i["id"] == req_id for i in inbox)
    # another advisor cannot resolve it
    other = "advisor2@saews.demo" if advisor.email == "advisor1@saews.demo" else "advisor1@saews.demo"
    assert as_role(other).patch(f"/api/requests/{req_id}", json={"status": "resolved", "resolution": "x"}).status_code == 403
    ok = as_role(advisor.email).patch(f"/api/requests/{req_id}", json={"status": "resolved", "resolution": "Corrected"})
    assert ok.status_code == 200 and ok.json()["status"] == "resolved"


# AT-08 ------------------------------------------------------------------------------------------
def test_at08_analyst_identifiable_export_denied_deidentified_allowed(as_role, db):
    c = as_role("analyst@saews.demo")
    assert c.get("/api/reports/export?identifiable=true").status_code == 403
    assert db.scalar(select(AuditLog).where(AuditLog.action == "report.export", AuditLog.outcome == "denied")) is not None
    r = c.get("/api/reports/export?identifiable=false")
    assert r.status_code == 200
    text = r.text
    header = text.splitlines()[0]
    assert "full_name" not in header and "student_code" not in header and "pseudonym" in header
    names = [s.full_name for s in db.scalars(select(Student).limit(20))]
    assert not any(n in text for n in names)
    assert "S2026" not in text


def test_at08_analyst_summary_is_suppressed(as_role):
    s = as_role("analyst@saews.demo").get("/api/reports/summary").json()
    assert s["deidentified"] is True
    for counts in s["by_program"].values():
        assert all(v is None or v == 0 or v >= s["min_group_size"] for v in counts.values())


def test_at08_authorized_analyst_can_export_identifiable(as_role, db):
    admin = as_role("admin@saews.demo")
    analyst = db.scalar(select(User).where(User.email == "analyst@saews.demo"))
    assert admin.patch(f"/api/admin/users/{analyst.id}", json={"identifiable_access": True}).status_code == 200
    try:
        r = as_role("analyst@saews.demo").get("/api/reports/export?identifiable=true")
        assert r.status_code == 200 and "full_name" in r.text.splitlines()[0]
    finally:
        admin.patch(f"/api/admin/users/{analyst.id}", json={"identifiable_access": False})
