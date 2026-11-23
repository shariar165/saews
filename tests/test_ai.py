"""Generative-AI assistant (docs/ai_integration_plan.md). The Anthropic client is replaced by a fake, so these
tests need no network or API key. AT-09: AI output is labelled, audited, stored, scoped, pseudonymized, and the
system keeps working when AI is disabled or fails."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import SecretStr
from sqlalchemy import func, select

from backend.app.ai import client as ai_client
from backend.app.ai import schemas
from backend.app.ai.privacy import scrub
from backend.app.config import get_settings
from backend.app.models import (
    AIOutput,
    AuditLog,
    Course,
    Enrollment,
    Recommendation,
    RiskAssessment,
    Student,
    User,
)

from .conftest import student_not_taught_by


def _sample(schema, prompt: str):
    if schema is schemas.CaseSummary:
        return schemas.CaseSummary(summary="Attendance fell in recent weeks.", key_concerns=["Attendance 70%"],
                                   positives=[], conversation_starters=["How are classes going?"], data_caveats=[])
    if schema is schemas.PersonalizedActions:
        import json
        import re
        data = json.loads(re.search(r"<data>\n(.*)\n</data>", prompt, re.S).group(1))
        ids = [a["id"] for a in data["proposed_actions"]]
        return schemas.PersonalizedActions(actions=[schemas.PersonalizedAction(id=i, text=f"Personalized text {i}")
                                                    for i in ids] + [schemas.PersonalizedAction(id=999999, text="x")])
    if schema is schemas.OutcomeNote:
        return schemas.OutcomeNote(note="Two meetings were held.", indicator_changes=["Attendance 70% -> 80%"],
                                   suggested_next_step="Review in two weeks.")
    if schema is schemas.SupportMessage:
        return schemas.SupportMessage(subject="Support for {student}",
                                      body="Dear guardian of {student}, we agreed extra classes. Regards, {sender}")
    if schema is schemas.GoalPlan:
        return schemas.GoalPlan(overview="You can do this.", study_tips=["Short daily sessions"],
                                weekly_steps=[schemas.WeeklyStep(week=1, focus="Basics", actions=["Revise ch. 1"])],
                                who_can_help=["Your class advisor"])
    raise AssertionError(schema)


class FakeClient:
    def __init__(self, stop_reason: str = "end_turn"):
        self.calls: list[dict] = []
        self.stop_reason = stop_reason
        self.beta = SimpleNamespace(messages=SimpleNamespace(parse=self._parse))

    def _parse(self, **kw):
        self.calls.append(kw)
        prompt = kw["messages"][0]["content"]
        parsed = None if self.stop_reason == "refusal" else _sample(kw["output_format"], prompt)
        return SimpleNamespace(stop_reason=self.stop_reason, parsed_output=parsed, model=kw["model"],
                               usage=SimpleNamespace(input_tokens=1200, output_tokens=300))

    @property
    def prompts(self) -> list[str]:
        return [c["messages"][0]["content"] for c in self.calls]


@pytest.fixture()
def fake_ai(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "ai_enabled", True)
    monkeypatch.setattr(s, "anthropic_api_key", SecretStr("test-key"))
    fake = FakeClient()
    monkeypatch.setattr(ai_client, "get_client", lambda: fake)
    return fake


def _teacher_student_with_assessment(db, email="teacher1@saews.demo", proposed=False):
    teacher = db.scalar(select(User).where(User.email == email))
    taught = select(Enrollment.student_id).join(Course).where(Course.teacher_id == teacher.id)
    q = (select(Student).join(RiskAssessment, RiskAssessment.student_id == Student.id)
         .where(Student.id.in_(taught), RiskAssessment.is_current.is_(True),
                RiskAssessment.risk_level.in_(["moderate", "high", "critical"])))
    if proposed:
        q = q.where(Student.id.in_(select(Recommendation.student_id).where(
            Recommendation.status == "proposed", Recommendation.ai_drafted.is_(False))))
    return db.scalar(q.limit(1))


def _assert_no_identifiers(text: str, st: Student, db):
    assert st.full_name not in text
    assert st.student_code not in text
    assert "@" not in text
    assert "equity" not in text.lower()
    if st.user_id:
        assert db.get(User, st.user_id).email not in text


# ------------------------------------------------------------------------------------------ disabled
def test_ai_disabled_by_default_and_system_still_works(as_role, db):
    assert not ai_client.is_enabled()
    c = as_role("teacher1@saews.demo")
    assert c.get("/api/ai/status").json() == {"enabled": False, "model": None, "features": [],
                                              "label": c.get("/api/ai/status").json()["label"]}
    st = _teacher_student_with_assessment(db)
    assert c.post(f"/api/ai/students/{st.id}/case-summary").status_code == 503
    assert c.get(f"/api/students/{st.id}").status_code == 200  # the normal profile is unaffected


def test_status_lists_features_by_role(as_role, fake_ai):
    assert as_role("teacher1@saews.demo").get("/api/ai/status").json()["features"] == [
        "case_summary", "rec_personalize", "outcome_note", "support_message"]
    assert as_role("student@saews.demo").get("/api/ai/status").json()["features"] == ["goal_plan"]
    assert as_role("analyst@saews.demo").get("/api/ai/status").json()["features"] == []


# ------------------------------------------------------------------------------------------ F1 / AT-09
def test_at09_case_summary_is_labelled_audited_cached_and_pseudonymized(as_role, db, fake_ai):
    st = _teacher_student_with_assessment(db)
    c = as_role("teacher1@saews.demo")
    r = c.post(f"/api/ai/students/{st.id}/case-summary")
    assert r.status_code == 200, r.text
    item = r.json()["item"]
    assert item["ai_generated"] is True and "AI-generated" in item["label"]
    assert item["output"]["summary"] and item["prompt_version"]
    assert r.json()["cached"] is False

    # stored + audited with token counts
    row = db.get(AIOutput, item["id"])
    assert row.feature == "case_summary" and row.student_id == st.id and row.input_tokens == 1200
    log = db.scalar(select(AuditLog).where(AuditLog.action == "ai.generate", AuditLog.outcome == "success")
                    .order_by(AuditLog.id.desc()))
    assert log.detail["feature"] == "case_summary" and log.detail["student_id"] == st.id

    # second request reuses the stored summary (no new model call); GET never calls the model
    again = c.post(f"/api/ai/students/{st.id}/case-summary")
    assert again.json()["cached"] is True and len(fake_ai.calls) == 1
    assert c.get(f"/api/ai/students/{st.id}/case-summary").json()["item"]["id"] == item["id"]
    assert c.post(f"/api/ai/students/{st.id}/case-summary?refresh=true").json()["cached"] is False
    assert len(fake_ai.calls) == 2

    # request settings and data minimization
    call = fake_ai.calls[0]
    assert call["model"] == get_settings().ai_model and call["fallbacks"] == "default"
    _assert_no_identifiers(fake_ai.prompts[0], st, db)


def test_ai_respects_record_scope_and_roles(as_role, db, fake_ai):
    other = student_not_taught_by(db, "teacher1@saews.demo")
    c = as_role("teacher1@saews.demo")
    assert c.post(f"/api/ai/students/{other.id}/case-summary").status_code == 403
    assert c.post(f"/api/ai/students/{other.id}/recommendations/personalize").status_code == 403
    denied = db.scalar(select(AuditLog).where(AuditLog.action == "ai.case_summary", AuditLog.outcome == "denied",
                                              AuditLog.target_id == str(other.id)))
    assert denied is not None
    st = _teacher_student_with_assessment(db)
    assert as_role("student@saews.demo").post(f"/api/ai/students/{st.id}/case-summary").status_code == 403
    assert as_role("analyst@saews.demo").post(f"/api/ai/students/{st.id}/case-summary").status_code == 403
    assert fake_ai.calls == []


def test_refusal_falls_back_cleanly(as_role, db, monkeypatch, fake_ai):
    refusing = FakeClient(stop_reason="refusal")
    monkeypatch.setattr(ai_client, "get_client", lambda: refusing)
    st = _teacher_student_with_assessment(db)
    before = db.scalar(select(func.count()).select_from(AIOutput))
    r = as_role("teacher1@saews.demo").post(f"/api/ai/students/{st.id}/case-summary?refresh=true")
    assert r.status_code == 503 and "declined" in r.json()["detail"]
    assert db.scalar(select(func.count()).select_from(AIOutput)) == before
    err = db.scalar(select(AuditLog).where(AuditLog.action == "ai.generate", AuditLog.outcome == "error")
                    .order_by(AuditLog.id.desc()))
    assert err.detail["feature"] == "case_summary"


# ------------------------------------------------------------------------------------------ F2
def test_personalize_only_rewrites_proposed_suggestions(as_role, db, fake_ai):
    st = _teacher_student_with_assessment(db, proposed=True)
    assert st is not None, "seed data should produce proposed recommendations"
    proposed = db.scalars(select(Recommendation).where(Recommendation.student_id == st.id,
                                                       Recommendation.status == "proposed")).all()
    c = as_role("teacher1@saews.demo")
    r = c.post(f"/api/ai/students/{st.id}/recommendations/personalize")
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert {i["id"] for i in items} == {p.id for p in proposed}  # the unknown id 999999 was ignored
    assert all(i["ai_drafted"] and i["status"] == "proposed" and i["text"].startswith("Personalized") for i in items)
    _assert_no_identifiers(fake_ai.prompts[0], st, db)
    # nothing left to personalize -> 409, and the student still sees none of the proposed items
    assert c.post(f"/api/ai/students/{st.id}/recommendations/personalize").status_code == 409


# ------------------------------------------------------------------------------------------ F3 / F4
def _plan_with_intervention(c, st):
    plan = c.post("/api/plans", json={"student_id": st.id, "title": f"Check-in for {st.full_name}"}).json()
    c.post(f"/api/plans/{plan['id']}/interventions",
           json={"action_type": "advisor_meeting", "notes": f"Met {st.full_name} ({st.student_code}), call 01712345678"})
    return plan


def test_outcome_note_scrubs_free_text(as_role, db, fake_ai):
    st = _teacher_student_with_assessment(db)
    c = as_role("teacher1@saews.demo")
    empty = c.post("/api/plans", json={"student_id": st.id, "title": "Empty plan"}).json()
    assert c.post(f"/api/ai/plans/{empty['id']}/outcome-note").status_code == 409
    plan = _plan_with_intervention(c, st)
    r = c.post(f"/api/ai/plans/{plan['id']}/outcome-note")
    assert r.status_code == 200, r.text
    assert r.json()["item"]["output"]["note"]
    prompt = fake_ai.prompts[-1]
    _assert_no_identifiers(prompt, st, db)
    assert "01712345678" not in prompt and "[phone]" in prompt


def test_bangla_message_fills_names_only_after_generation(as_role, db, fake_ai):
    st = _teacher_student_with_assessment(db)
    c = as_role("teacher1@saews.demo")
    plan = _plan_with_intervention(c, st)
    r = c.post(f"/api/ai/plans/{plan['id']}/message", json={"audience": "guardian", "language": "bn"})
    assert r.status_code == 200, r.text
    out = r.json()["item"]["output"]
    assert st.full_name in out["body"] and "Hasan Teacher" in out["body"] and "{student}" not in out["body"]
    assert "Bangla" in fake_ai.prompts[-1]
    _assert_no_identifiers(fake_ai.prompts[-1], st, db)
    row = db.get(AIOutput, r.json()["item"]["id"])
    assert "{student}" in row.output["body"] and st.full_name not in row.output["body"]  # stored without names
    assert row.variant == "guardian:bn"
    assert c.post(f"/api/ai/plans/{plan['id']}/message", json={"language": "fr"}).status_code == 422


# ------------------------------------------------------------------------------------------ F5
def test_student_goal_plan_has_no_risk_data(as_role, db, fake_ai):
    c = as_role("student@saews.demo")
    me = db.scalar(select(Student).join(User, User.id == Student.user_id).where(User.email == "student@saews.demo"))
    goal = c.post("/api/me/goals", json={"title": f"I am {me.full_name}, improve Physics marks"}).json()
    r = c.post(f"/api/ai/me/goals/{goal['id']}/plan", json={"language": "en"})
    assert r.status_code == 200, r.text
    assert r.json()["item"]["output"]["weekly_steps"]
    prompt = fake_ai.prompts[-1]
    _assert_no_identifiers(prompt, me, db)
    for word in ("risk", "probability", "factor", "warning"):
        assert word not in prompt.lower()
    assert c.post(f"/api/ai/me/goals/{goal['id']}/plan", json={"language": "en"}).json()["cached"] is True
    # staff cannot use the student endpoint; another student's goal id is not found
    assert as_role("teacher1@saews.demo").post(f"/api/ai/me/goals/{goal['id']}/plan", json={}).status_code == 403
    assert c.post("/api/ai/me/goals/999999/plan", json={}).status_code == 404


# ------------------------------------------------------------------------------------------ units
def test_scrub_removes_identifiers():
    st = Student(full_name="Rafiq Hossain", student_code="S20260099")
    out = scrub("Rafiq (S20260099) said hossain will email rafiq@example.com or call +8801712345678", st)
    assert "Rafiq" not in out and "hossain" not in out.lower() and "S20260099" not in out
    assert "[email]" in out and "[phone]" in out
    assert scrub(None, st) is None
