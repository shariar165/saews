# Plan: Adding Generative AI (LLM) to SAEWS

Status: **Phase 1 and Phase 2 implemented** (2026-11-23). Phase 3 not started.

Implementation notes / changes from the original plan:
- F2 runs **on demand** (the "Personalize with AI" button) instead of inside `propose_for_assessment()`, so
  batch re-assessments (imports, seeding, recompute) never trigger hundreds of paid AI calls.
- F4 messages are drafted from a **support plan** (plans exist only for staff-agreed support).
- Staff-written free text (plan titles, notes, outcomes) and student goals are scrubbed of the student's name,
  code, emails and phone numbers before sending.
- Tests use a fake client; no live API call has been made yet (needs an API key).

## 1. Is it possible? Yes.

SAEWS already uses "classic" AI: a logistic-regression risk model (`backend/app/ml/`) with
rule-based fallback. What it lacks is **language**. Every explanation, recommendation and
message is a fixed template (`ml/explain.py`, `services/recommendations.py`). A large language
model (LLM) fits well in those places, because the project already has the safeguards an LLM needs:

| Existing safeguard | Why it matters for an LLM |
|---|---|
| Human review of every recommendation (FR6) | AI text can start as a *draft* that staff approve, edit or dismiss, never an automatic action |
| Structured factors + data-quality warnings in `RiskAssessment` | The LLM writes only from these facts and doesn't invent new ones |
| Fallback design (FR10: model → rules → "unavailable") | The same pattern works for AI: LLM → existing template text |
| Audit log (FR8) | Every AI call can be logged (who, which student, which feature, model version) |
| Role + record scope checks (`core/deps.py`) | AI endpoints reuse them, so the AI can't see more than the user can |
| De-identification and small-cell suppression (FR9) | AI over reports reads only data that is already de-identified |

**Main constraint: privacy.** Student data would go to an external API. The demo data is
synthetic, so the demo is fine. A real school would need consent or a data-processing agreement
first. The design below sends **no names, emails, student codes or `equity_group`**, only
pseudonymized indicators.

## 2. Proposed features (ranked by value ÷ risk)

### Phase 1: Staff-facing, lowest risk (core of the capstone demo)

**F1. "Explain this alert": AI case summary** (student profile page, teachers and advisors)
- Input: the current `RiskAssessment` (level, factors, warnings, completeness, data age), the
  recent trend numbers from `/students/{id}/indicators`, and the titles and statuses of open plans.
- Output (structured JSON): a 3–4 sentence plain-language summary, the top concerns, 3 suggested
  *supportive* conversation-starter questions, and data caveats such as "attendance data is 25 days old".
- The page labels it "AI-generated summary: estimate, verify before acting".
- It extends FR5 (explanations).

**F2. Personalized recommendation drafts** (extends FR6)
- After `propose_for_assessment()` picks catalogue items, the LLM rewrites each item's generic
  `description` into a version tailored to this student's factors. Example: "Attendance fell
  18 points in 4 weeks, mostly in SSC-MATH. Suggest a private check-in about the class routine."
- The item stays in `proposed` status with an `ai_drafted=true` flag. Staff still approve, edit
  or dismiss it. If AI is off or fails, the current template text is used unchanged.

**F3. Intervention / support-plan note drafting**
- When a plan or intervention is closed, the LLM drafts an outcome note from the before/after
  indicator snapshots that FR7 already stores. Staff edit the draft before saving.

### Phase 2: Bangladesh-specific value

**F4. Bangla (বাংলা) guardian / student messages**
- From an *approved* recommendation or plan, generate a polite message for the guardian or
  student in Bangla or English. It is copied manually and never sent automatically.
- The tone rules from the catalogue apply here too: supportive, non-punitive, no risk labels,
  no assumed causes.

**F5. Student study-goal helper** (student portal `me.html`)
- Helps a student turn a goal ("improve Physics") into specific weekly steps.
- Input is limited to the student's own goals and **approved** support items only. It never sees
  risk level, probability or factors, which keeps the rule that students see no risk labels.
- Strict system prompt: study planning only. For wellbeing topics it points to the school
  counsellor instead of advising.

### Phase 3: Optional / stretch

**F6. Natural-language questions over reports** (analyst/admin): "Which HSC subjects had the
biggest attendance drop this term?" Claude uses tool calls to run the *existing* functions in
`services/reports.py`, so de-identification and small-cell suppression still apply. It never runs raw SQL.

**F7. CSV import column mapping**: when an upload has unfamiliar headers ("Roll No",
"উপস্থিতি"), suggest the mapping to the template columns. The existing validator still decides
whether the file is valid.

**Not recommended:** letting an LLM *predict* risk or replace the logistic-regression model. The
current model is calibrated, versioned, fairness-checked and explainable, and an LLM would be
none of those.

## 3. Architecture

```
backend/app/ai/
  __init__.py
  client.py      # lazy Anthropic client; is_enabled(); one place for model, timeout, retries
  privacy.py     # build_context(): pseudonymize ("Student"), drop name/email/code/equity_group
  schemas.py     # Pydantic output models (CaseSummary, RecDraft, MessageDraft, ...)
  prompts.py     # versioned system prompts (tone rules: supportive, non-punitive, no diagnosis)
  service.py     # summarize_case(), draft_recommendation(), draft_message(), ...
backend/app/api/ai.py   # /api/ai/* routes, reusing get_current_user + scope checks
```

- **SDK:** official `anthropic` Python package. Use `client.messages.parse()` with the Pydantic
  schemas, so the API returns validated JSON and no hand-written parsing is needed.
- **Model:** `claude-opus-5-5` by default, configurable through `EWS_AI_MODEL`. These are short,
  bounded writing tasks, so use `output_config.effort="low"` to keep cost and latency down.
- **Refusals:** check `stop_reason`. On `"refusal"` or any API error, fall back to the existing
  template text, the same way FR10 falls back from the model to rules.
- **Caching results:** a new table `ai_outputs` (feature, assessment_id or plan_id, model,
  prompt_version, output JSON, created_at, created_by). A summary is generated once per
  assessment and reused, then regenerated only when a new assessment arrives. This saves cost
  and makes the output auditable. Needs one Alembic migration.
- **Audit:** every call writes an `AuditLog` row (`action="ai_generate"`, feature, student id,
  model, token counts). The text sent to the API is never logged.
- **Rate limit:** slowapi (already installed) on `/api/ai/*`, e.g. `20/minute` per user.
- **Frontend:** a "Generate AI summary" button on `student.html`, an "AI draft" badge on
  recommendations, and a "Draft message (বাংলা / English)" button on approved items. No CSP
  change is needed because all calls happen on the server.

### Configuration (`config.py` / `.env.example`)
```
EWS_AI_ENABLED=false          # off by default; the app behaves exactly as today
ANTHROPIC_API_KEY=            # set on Vercel with: vercel env add ANTHROPIC_API_KEY
EWS_AI_MODEL=claude-opus-5-5
EWS_AI_RATE_LIMIT=20/minute
```
Add `anthropic` to **both** `requirements.txt` and `pyproject.toml`, because Vercel installs from
`pyproject.toml`. The 300 s function timeout on Vercel is far more than these calls need.

## 4. Safety and privacy rules (put these in the system prompts and enforce them in code)

1. **Facts only from the input.** The model must not guess causes (poverty, family, health). It
   may only *suggest asking*.
2. **No labels for students.** Student-facing output never mentions risk level or probability.
3. **Supportive language only.** No punitive, disciplinary or grading suggestions, matching the
   SRS non-goals.
4. **Pseudonymize.** `privacy.build_context()` is the only way data reaches the LLM. A unit test
   checks that no name, email, student code or equity group appears in any prompt.
5. **Human in the loop.** Everything the AI writes is a draft, and nothing is sent or applied
   without a staff click.
6. **Clear labelling.** All AI text is marked "AI-generated draft" in the UI and API responses.
7. **Kill switch.** With `EWS_AI_ENABLED=false`, or no API key, every feature hides itself and
   AT-01…AT-08 behave exactly as they do today.

## 5. Testing

- Unit tests with a **mocked** Anthropic client (no network, no cost in CI): schema parsing,
  fallback on error or refusal, the pseudonymization test, and role checks (a student cannot call
  `/api/ai/case-summary`, and a teacher cannot summarize a student outside their scope).
- New acceptance test **AT-09**: an AI summary is generated, labelled, audited and cached, and it
  falls back to template text when AI is disabled.
- A small manual evaluation set: 10–15 synthetic students covering every risk level. Check each
  output against a rubric (accurate to the facts, supportive tone, no labels leaked to students,
  no invented causes). Record the results in `docs/model_card.md`.

## 6. Work breakdown

| Step | Work | Size |
|---|---|---|
| 1 | `ai/` module: client, privacy, schemas, prompts; config + deps; kill switch | S |
| 2 | `ai_outputs` table + Alembic migration; audit hook | S |
| 3 | F1 case summary: API route + student-profile UI | M |
| 4 | F2 recommendation drafts wired into `propose_for_assessment()` + "AI draft" badge | M |
| 5 | Tests (mocked), AT-09, pseudonymization test | M |
| 6 | Docs: README feature table row, `architecture.md` diagram node, `model_card.md` LLM section | S |
| 7 | Phase 2: F3 notes, F4 Bangla messages, F5 student goal helper | M–L |
| 8 | Phase 3 (optional): F6 report Q&A with tool use, F7 CSV mapping | L |

Phase 1 (steps 1–6) is enough for a strong capstone demo. Phases 2–3 are optional.

## 7. Open decisions for the team

- **API key / budget:** who owns the Anthropic account and key for the live demo
  (`saews.vercel.app`)? The live demo is a shared public site, so keep rate limits on and AI
  features limited to staff roles at first.
- **Model tier:** start on `claude-opus-5-5` at low effort. Switch through `EWS_AI_MODEL` if the
  team wants lower cost.
- **Real-data use:** before any non-synthetic data is used, get institutional approval for sending
  pseudonymized indicators to an external AI provider.
