# SAEWS — AI-Driven Socio-Academic Early Warning & Personalized Decision Support System

Capstone prototype for **SE331 – Software Engineering Design & Capstone Project** (Fall 2026, Section A1).
It implements the system specified in the team's SRS: it helps authorized teachers and advisors notice
students who may need timely support, explains *why*, suggests supportive (never punitive) actions
for staff to review, and tracks follow-up, with privacy, audit and fairness safeguards built in.
The demo data models a **Bangladeshi school and college**: SSC students (Class 9–10) and HSC students
(Class 11–12) in the Science, Business Studies and Humanities groups, with GPA on the 5.00 scale.

> **Model outputs are estimates, not facts.** The system assists human decision-makers. It never makes grading,
> disciplinary, admission or eligibility decisions, and no action is triggered automatically.
> All bundled data is **synthetic** (fictional students).

## Live demo

**https://saews.vercel.app** — sign in with any of the [demo accounts](#demo-accounts-demo-mode-only-password-demo2026)
below (password `Demo@2026!`), e.g. `teacher1@saews.demo`, `student@saews.demo` or `admin@saews.demo`.
The [suggested walkthrough](#suggested-demo-walkthrough) works there too.

- Hosted on **Vercel** (FastAPI as a single Python function via `index.py`) with a **Neon Postgres** database.
  Every push to `main` redeploys automatically.
- The live database is a **shared demo**: changes made by any visitor (imports, plans, goals) are visible to everyone.
  It is separate from your local SQLite database.
- Vercel installs dependencies from `pyproject.toml` — keep it in sync with `requirements.txt` when adding packages.
- The deployed app loads the model committed in `backend/app/ml/artifacts/`. After retraining, commit the new
  `registry.json`, `model_*.joblib` and `metrics_*.json` (`git add -f`, the folder is git-ignored) and push.

## Features (SRS traceability)

| SRS | Feature | Where |
|---|---|---|
| FR1 | Secure login (Argon2id, HttpOnly JWT cookie, rate-limited), role-based access, per-record scope checks | `core/security.py`, `core/deps.py` |
| FR2 | CSV import → dry-run validation (columns, types, ranges, duplicates, unknown IDs, enrollment, teacher scope) → commit only if error-free; batches fingerprinted (SHA-256) | `services/imports.py`, Data Import page |
| FR3 | Role dashboards, student profile with attendance/score/engagement trends; student portal | `dashboard.html`, `student.html`, `me.html` |
| FR4 | Logistic-regression risk model; stores level, probability, model version, timestamp, data freshness | `ml/`, `services/risk_engine.py` |
| FR5 | Plain-language contributing factors, missing/stale-data warnings, review & flag actions | `ml/explain.py`, profile page |
| FR6 | Rules-based recommendation catalogue ranked by factor strength; staff approve/edit/dismiss; students see only approved items | `services/recommendations.py` |
| FR7 | Support plans (owner, due date, status) and interventions with before/after indicator snapshots | `api/workflow.py` |
| FR8 | Audit log (views, denials, exports, logins, role changes), correction requests routed to a reviewer, retention job | `core/audit.py`, `services/retention.py` |
| FR9 | Aggregate reports, de-identified exports (pseudonyms, small-cell suppression), identifiable export only when authorized | `services/reports.py` |
| FR10 | Rule-based fallback, clearly labelled, when the model is unavailable; "unavailable" state if both fail; model monitor | `services/risk_engine.py`, Administration page |

Acceptance tests **AT-01 … AT-08** from SRS Appendix A are automated in `tests/test_acceptance.py`.

## Tech stack
Python 3.11+ · FastAPI · SQLAlchemy 2 + Alembic · SQLite (PostgreSQL-ready) · pandas · scikit-learn ·
plain HTML/CSS/JavaScript (ES modules) · Chart.js (vendored, no Node build step).

## Quick start (Windows / PowerShell)

Everything installs into the project's virtual environment `.venv`, never into the global Python.

```powershell
# one-time: create/reuse .venv, install deps, create DB + demo data, train model, assess students
.\scripts\setup.ps1

# run
.\scripts\run.ps1            # → http://localhost:8000   (API docs: http://localhost:8000/api/docs)
```

Or step by step:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m backend.app.seed.generate --reset   # schema (Alembic) + synthetic data + assessment
.\.venv\Scripts\python.exe -m backend.app.ml.train                # train, evaluate, register model
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload
```

To activate the venv in your shell instead: `.\.venv\Scripts\Activate.ps1`
(if blocked: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`).

### Demo accounts (demo mode only, password `Demo@2026!`)

| Role | Email | Sees |
|---|---|---|
| Teacher | `teacher1@saews.demo` | Students in Mathematics, Physics, Chemistry and Accounting (SSC-MATH, SSC-PHY, SSC-CHEM, SSC-ACC, HSC-PHY, HSC-CHEM, HSC-ACC) |
| Teacher | `teacher2@saews.demo` | Students in Bangla, English, ICT, Business and Humanities subjects (SSC-BAN, SSC-ENG, SSC-FIN, SSC-HIST, SSC-GEO, HSC-BAN, HSC-ENG, HSC-ICT, HSC-BOM, HSC-CIV, HSC-ECO) |
| Advisor | `advisor1@saews.demo` | Class advisor for school students (Class 9–10) |
| Advisor | `advisor2@saews.demo` | Class advisor for college students (Class 11–12) |
| Student | `student@saews.demo` | Own progress, approved support, goals, requests |
| Analyst | `analyst@saews.demo` | Aggregate, de-identified reports only |
| Admin | `admin@saews.demo` | Users/roles, imports, model monitor, audit log, retention |

Interesting seeded cases: **S20260001** (the demo student, declining after the mid-term exam → high risk),
**S20260002** (enrolled, no data → *Insufficient data*), **S20260003** (data stops at week 4 → *stale, provisional*).

### Suggested demo walkthrough
1. `teacher1` → Dashboard → open a High/Critical alert → read the factors → **Approve** a suggestion (creates a plan) → record an intervention → record its outcome.
2. `student` → My Progress → see the approved plan → submit **Request a correction**.
3. `advisor1` → Support & Requests → resolve the correction request.
4. `admin` → Data Import → upload `sample_data/example_with_errors_attendance.csv` (rejected with line-level errors), then `example_attendance_week11_SSC-MATH.csv` (validate → commit → background re-assessment) → Administration → audit log / model monitor.
5. `analyst` → Reports → only suppressed, de-identified figures; identifiable export is refused and audited.

## Tests & quality

```powershell
.\.venv\Scripts\python.exe -m pytest        # 29 tests: AT-01..AT-08 + unit tests
.\.venv\Scripts\python.exe -m ruff check .
```

Tests run against an isolated temporary database and model directory.

End-to-end check against the **running** server (92 checks across all roles; writes demo records):

```powershell
.\.venv\Scripts\python.exe scripts\smoke_test.py
```

## Configuration
All settings use environment variables with the `EWS_` prefix (or a `.env` file). See `.env.example`.
Key ones: `EWS_DATABASE_URL`, `EWS_JWT_SECRET` (**required** in production), `EWS_COOKIE_SECURE`,
risk thresholds, `EWS_STALE_AFTER_DAYS`, `EWS_MIN_GROUP_SIZE`, retention periods.

**PostgreSQL:** `pip install "psycopg[binary]"` into the venv, set
`EWS_DATABASE_URL=postgresql+psycopg://user:pass@host:5432/saews`, then run
`.\.venv\Scripts\python.exe -m alembic upgrade head`.

## Project layout
```
backend/app/
  api/         REST endpoints (auth, students, risk, workflow, me, imports, reports, admin)
  core/        security (Argon2id, JWT), authorization dependencies, audit, rate limiting
  ml/          features, rules engine, explanations, model loading, training, evaluation
  services/    risk engine, recommendations, imports, indicators, reports, retention
  seed/        synthetic cohort generator + demo seeding
alembic/       database migrations
frontend/      role-based web UI (HTML/CSS/ES modules, Chart.js)
sample_data/   CSV templates and example import files
tests/         acceptance (AT-01..08) and unit tests
docs/          architecture, model card, API notes
```

## Documentation
- [Architecture & diagrams](docs/architecture.md)
- [Model card](docs/model_card.md)
- [API overview](docs/api.md) (interactive docs at `/api/docs`)

## Limitations (SRS Appendix B)
This is a prototype trained and demonstrated on **synthetic data**. Before any real use, the
following must be confirmed with the institution: risk thresholds, data fields, model choice and
validation on real data, lawful basis and consent, retention periods, and integrations. Elicitation
evidence (interviews, surveys) must be collected, and nothing should be reported as validated until it has been.

## Team
Tanvir Hasan Siam (241-35-553) · Shah Ismat Mahmud Tanim (241-35-078) · Mahfuzur Rahman Shimul (241-35-175)
