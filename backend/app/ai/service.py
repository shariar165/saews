"""AI features: generate, store (``ai_outputs``) and audit. API routes stay thin and only do access control."""

from __future__ import annotations

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..api.serializers import iso
from ..core.audit import audit
from ..models import AIOutput, Recommendation, RiskAssessment, Student, StudyGoal, SupportPlan, User
from . import privacy, prompts, schemas
from .client import AIResult, AIUnavailable, generate

AI_LABEL = "AI-generated draft. Check it against the record before using it."
MAX_REC_TEXT = 1500


def output_out(o: AIOutput | None, *, data: dict | None = None) -> dict | None:
    if o is None:
        return None
    return {"id": o.id, "feature": o.feature, "variant": o.variant, "model": o.model,
            "prompt_version": o.prompt_version, "created_at": iso(o.created_at), "ai_generated": True,
            "label": AI_LABEL, "output": data if data is not None else o.output}


def latest(db: Session, feature: str, target_type: str, target_id: int, variant: str | None = None) -> AIOutput | None:
    q = select(AIOutput).where(AIOutput.feature == feature, AIOutput.target_type == target_type,
                               AIOutput.target_id == target_id)
    if variant is not None:
        q = q.where(AIOutput.variant == variant)
    return db.scalar(q.order_by(AIOutput.created_at.desc(), AIOutput.id.desc()).limit(1))


def _run(db: Session, user: User, request: Request | None, *, feature: str, student_id: int, target_type: str,
         target_id: int, schema, system: str, prompt: str, variant: str | None = None,
         extra_output: dict | None = None, max_tokens: int = 4000) -> tuple[AIOutput, AIResult]:
    try:
        result = generate(schema, system=system, prompt=prompt, max_tokens=max_tokens)
    except AIUnavailable as e:
        audit(db, "ai.generate", user=user, request=request, target_type=target_type, target_id=target_id,
              outcome="error", detail={"feature": feature, "student_id": student_id, "reason": str(e)})
        raise
    output = result.data.model_dump()
    if extra_output:
        output.update(extra_output)
    row = AIOutput(feature=feature, target_type=target_type, target_id=target_id, student_id=student_id,
                   variant=variant, model=result.model, prompt_version=prompts.PROMPT_VERSION, output=output,
                   input_tokens=result.input_tokens, output_tokens=result.output_tokens, created_by=user.id)
    db.add(row)
    db.flush()
    audit(db, "ai.generate", user=user, request=request, target_type=target_type, target_id=target_id,
          detail={"feature": feature, "student_id": student_id, "ai_output_id": row.id, "model": result.model,
                  "prompt_version": prompts.PROMPT_VERSION, "input_tokens": result.input_tokens,
                  "output_tokens": result.output_tokens, "variant": variant})
    return row, result


# F1 -------------------------------------------------------------------------------------------
def case_summary(db: Session, user: User, request: Request, student: Student, ra: RiskAssessment) -> AIOutput:
    ctx = privacy.case_context(db, student, ra)
    row, _ = _run(db, user, request, feature="case_summary", student_id=student.id, target_type="assessment",
                  target_id=ra.id, schema=schemas.CaseSummary, system=prompts.CASE_SUMMARY_SYSTEM,
                  prompt=prompts.case_summary_prompt(ctx))
    return row


# F2 -------------------------------------------------------------------------------------------
def personalize_recommendations(db: Session, user: User, request: Request, student: Student,
                                ra: RiskAssessment | None, recs: list[Recommendation]) -> list[Recommendation]:
    ctx = privacy.recommendations_context(db, student, ra, recs)
    originals = {str(r.id): r.rationale for r in recs}
    row, result = _run(db, user, request, feature="rec_personalize", student_id=student.id, target_type="student",
                       target_id=student.id, schema=schemas.PersonalizedActions, system=prompts.PERSONALIZE_SYSTEM,
                       prompt=prompts.personalize_prompt(ctx), extra_output={"original_text": originals})
    by_id = {r.id: r for r in recs}
    updated = []
    for action in result.data.actions:
        rec = by_id.get(action.id)
        text = (action.text or "").strip()
        if rec is None or rec.status != "proposed" or not text:
            continue
        rec.rationale = text[:MAX_REC_TEXT]
        rec.ai_drafted = True
        updated.append(rec)
    db.commit()
    return updated


# F3 -------------------------------------------------------------------------------------------
def outcome_note(db: Session, user: User, request: Request, plan: SupportPlan) -> AIOutput:
    ctx = privacy.plan_context(db, plan)
    row, _ = _run(db, user, request, feature="outcome_note", student_id=plan.student_id, target_type="plan",
                  target_id=plan.id, schema=schemas.OutcomeNote, system=prompts.OUTCOME_NOTE_SYSTEM,
                  prompt=prompts.outcome_note_prompt(ctx))
    return row


# F4 -------------------------------------------------------------------------------------------
def support_message(db: Session, user: User, request: Request, plan: SupportPlan, *, audience: str,
                    language: str) -> AIOutput:
    ctx = privacy.plan_context(db, plan, include_interventions=False)
    row, _ = _run(db, user, request, feature="support_message", student_id=plan.student_id, target_type="plan",
                  target_id=plan.id, variant=f"{audience}:{language}", schema=schemas.SupportMessage,
                  system=prompts.MESSAGE_SYSTEM, prompt=prompts.message_prompt(ctx, audience=audience, language=language))
    return row


def filled_message(o: AIOutput, *, student: Student, sender: User) -> dict:
    """Insert real names locally, after generation; the stored record keeps only the placeholders."""
    first = (student.full_name or "").split()[0] if student.full_name else "the student"
    name = student.full_name if (o.variant or "").startswith("guardian") else first
    return {k: privacy.fill_placeholders(v, student_name=name, sender_name=sender.full_name)
            for k, v in o.output.items() if isinstance(v, str)}


# F5 -------------------------------------------------------------------------------------------
def goal_plan(db: Session, user: User, request: Request, student: Student, goal: StudyGoal, *, language: str) -> AIOutput:
    ctx = privacy.goal_context(db, student, goal)
    row, _ = _run(db, user, request, feature="goal_plan", student_id=student.id, target_type="goal",
                  target_id=goal.id, variant=language, schema=schemas.GoalPlan, system=prompts.GOAL_PLAN_SYSTEM,
                  prompt=prompts.goal_plan_prompt(ctx, language=language))
    return row
