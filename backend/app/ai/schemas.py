"""Structured outputs the AI must return (validated by the SDK against these Pydantic models)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# F1 ------------------------------------------------------------------------------------------
class CaseSummary(BaseModel):
    summary: str = Field(description="3-4 plain-language sentences for a teacher or class advisor.")
    key_concerns: list[str] = Field(description="2-4 short bullet points, each tied to a specific number in the data.")
    positives: list[str] = Field(description="0-3 strengths or improving trends visible in the data.")
    conversation_starters: list[str] = Field(
        description="3 open, supportive questions staff could ask the student. No assumptions about causes.")
    data_caveats: list[str] = Field(description="Limits of the data (stale, missing, provisional). Empty if none.")


# F2 ------------------------------------------------------------------------------------------
class PersonalizedAction(BaseModel):
    id: int = Field(description="The id of the proposed action being rewritten.")
    text: str = Field(description="2-4 sentences: what to do, tailored to this student's numbers, and why.")


class PersonalizedActions(BaseModel):
    actions: list[PersonalizedAction]


# F3 ------------------------------------------------------------------------------------------
class OutcomeNote(BaseModel):
    note: str = Field(description="A factual 3-6 sentence outcome note for the support-plan record.")
    indicator_changes: list[str] = Field(description="Each before/after change, e.g. 'Attendance 72% -> 85%'.")
    suggested_next_step: str = Field(description="One supportive next step for staff to consider.")


# F4 ------------------------------------------------------------------------------------------
class SupportMessage(BaseModel):
    subject: str = Field(description="Short subject line in the requested language.")
    body: str = Field(description="The message in the requested language, using {student} and {sender} placeholders.")


# F5 ------------------------------------------------------------------------------------------
class WeeklyStep(BaseModel):
    week: int = Field(description="Week number starting at 1.")
    focus: str
    actions: list[str] = Field(description="2-4 small, concrete tasks for that week.")


class GoalPlan(BaseModel):
    overview: str = Field(description="1-2 encouraging sentences addressed to the student.")
    weekly_steps: list[WeeklyStep] = Field(description="2-6 weeks of steps.")
    study_tips: list[str] = Field(description="2-4 practical study tips relevant to the goal.")
    who_can_help: list[str] = Field(description="Who at school/college the student could ask for help.")


Language = Literal["en", "bn"]
Audience = Literal["guardian", "student"]
