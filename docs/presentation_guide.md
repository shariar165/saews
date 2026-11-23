# SAEWS — Complete Usage & Presentation Guide

A to Z guide to understanding, running, demonstrating and presenting the
**AI-Driven Socio-Academic Early Warning & Personalized Decision Support System (SAEWS)**,
SE331 capstone prototype (Fall 2026, Section A1).

---

## Contents
1. [What the project is](#part-1--what-the-project-is)
2. [How it works internally](#part-2--how-it-works-internally)
3. [How to use it](#part-3--how-to-use-it)
4. [How to present it](#part-4--how-to-present-it)
5. [Questions to prepare for](#part-5--questions-to-prepare-for)
6. [Pre-presentation checklist](#part-6--pre-presentation-checklist)

---

## Part 1 — What the project is

**One-line pitch:**
> SAEWS helps teachers and advisors notice students who are starting to struggle *early enough to help*,
> explains *why* each student was flagged, and suggests supportive actions — with a human always making the final decision.

### The problem
Schools and colleges usually notice a struggling student only after a failed exam. The warning signs —
attendance dropping, missing homework, falling class-test scores, reduced online learning portal activity — were
visible weeks earlier, but nobody combines them in one place.

### The solution: a 6-step loop
1. **Collect** — staff upload CSV files (attendance, class test/exam scores, homework, online-portal activity); every file is validated before anything is saved.
2. **Predict** — a machine-learning model estimates each student's risk: **Low / Moderate / High / Critical**.
3. **Explain** — the system shows *why* in plain language (e.g. "Attendance dropped by 15+ points recently").
4. **Recommend** — supportive, never punitive, actions (tutoring, study plan, advisor meeting, …).
5. **Human decides** — a teacher approves, edits or dismisses each suggestion. Nothing happens automatically.
6. **Track** — the approved suggestion becomes a support plan; interventions are recorded and before/after indicators compared.

### Core principles (repeat these when presenting)
- **Model outputs are estimates, not facts.** The system never grades, disciplines or decides eligibility.
- **Human-in-the-loop** — every recommendation needs staff approval.
- **Privacy by design** — role-based access, audit log, de-identified reports, data retention.
- **Fairness checked** — no demographic features are used; error rates are still compared across groups.
- **Honest about data quality** — missing or old data is reported instead of guessed around.
- **All data is synthetic** — fictional students only.

---

## Part 2 — How it works internally

### Architecture
```
Browser (HTML/CSS/JS + Chart.js)
      │  JSON + secure HttpOnly cookie
      ▼
FastAPI server (/api/*)
  ├─ Auth: Argon2id passwords, JWT cookie, rate-limited login, role + per-record checks
  ├─ Import validator: dry-run → line-level errors → commit only if clean
  ├─ Risk engine ──► Feature pipeline (pandas) ──► Logistic Regression (scikit-learn)
  │                                         └─(if model fails)─► Rule-based fallback
  ├─ Recommendation engine (catalogue of 7 supportive actions)
  ├─ Workflow: support plans, interventions, student requests
  ├─ Reports: aggregate + de-identified exports
  └─ Audit logger (views, denials, exports, logins, role changes)
      ▼
Database: SQLite (local) / Neon Postgres (Vercel)
```
Detailed Mermaid diagrams (architecture, risk pipeline, activity flow, ER diagram) are in
[`architecture.md`](architecture.md) — paste them into <https://mermaid.live> to export PNGs for slides.

### The risk pipeline
1. **9 features per student** (`backend/app/ml/features.py`):
   - attendance rate, attendance trend (last 4 weeks vs earlier)
   - average score, score trend (last 2 assessments vs earlier)
   - missing-homework rate, late-homework rate
   - engagement change (last 3 weeks vs earlier), average logins
   - previous exam GPA (out of 5.00; SSC GPA for college students)
2. **Data-quality gates**
   - Less than 60% of data groups present → **"Insufficient data"**, no prediction shown.
   - Newest data older than 21 days → **"provisional"** with a warning.
3. **Model** — logistic regression, chosen for *explainability*. Each feature's contribution
   (coefficient × standardized value) becomes a plain-language reason (`ml/explain.py`).
4. **Risk levels** (configurable): Low < 0.20 ≤ Moderate < 0.40 ≤ High < 0.65 ≤ Critical.
5. **Fallback** — if the model is missing or broken, transparent rules (`ml/rules.py`) take over, labelled
   *Rule-based (fallback)*. If rules also fail → *Unavailable*.
6. **Recommendations** (`services/recommendations.py`):

   | Trigger | Suggested action |
   |---|---|
   | Low attendance | Supportive attendance follow-up |
   | Low scores | Remedial classes or peer tutoring |
   | Missing work / low scores | Structured weekly study plan |
   | Missing work | Homework catch-up and deadline planning |
   | Low engagement | Online learning portal check-in (check access, device, connectivity) |
   | Risk High or above | Advisor check-in meeting |
   | Risk Critical | Share support-services information ("do not assume a cause") |

### User roles
| Role | Can see | Can do |
|---|---|---|
| **Teacher** | Students in own subjects only | Review alerts, approve recommendations, plans, import data for own subjects |
| **Advisor** (class advisor) | Own class's students only | Same as teacher (no imports), resolve student requests |
| **Student** | Self only — **no risk label**, only approved support | Study goals, help / correction requests |
| **Analyst** | No individual students | Aggregate, de-identified reports (groups under 5 suppressed) |
| **Admin** | Everything (audited) | Users/roles, imports, model monitor, audit log, retention |

All checks are enforced on the server, and denied attempts are written to the audit log.

### SRS traceability
| SRS | Feature |
|---|---|
| FR1 | Secure login, role-based access, per-record scope checks |
| FR2 | CSV import with dry-run validation, commit only if error-free, SHA-256 fingerprinted batches |
| FR3 | Role dashboards, student profile trends, student portal |
| FR4 | Risk model storing level, probability, model version, timestamp, data freshness |
| FR5 | Plain-language factors, missing/stale-data warnings, review & flag actions |
| FR6 | Ranked recommendation catalogue; staff approve/edit/dismiss; students see approved items only |
| FR7 | Support plans and interventions with before/after snapshots |
| FR8 | Audit log, correction requests routed to reviewer, retention job |
| FR9 | Aggregate reports, de-identified exports, identifiable export only when authorized |
| FR10 | Labelled rule-based fallback; "unavailable" state; model monitor |

### Tech stack
Python 3.11+ · FastAPI · SQLAlchemy 2 + Alembic · SQLite / PostgreSQL · pandas · scikit-learn ·
plain HTML/CSS/JavaScript (ES modules) · Chart.js · hosted on Vercel with Neon Postgres. No Node.js build step.

---

## Part 3 — How to use it

### Option A — Live demo (easiest)
**<https://saews.vercel.app>** — password for every account: **`Demo@2026!`**

| Login | Role |
|---|---|
| `teacher1@saews.demo` | Teacher (Mathematics, Physics, Chemistry, Accounting) |
| `teacher2@saews.demo` | Teacher (Bangla, English, ICT, Business, Humanities) |
| `advisor1@saews.demo` | Class advisor (School, Class 9–10) |
| `advisor2@saews.demo` | Class advisor (College, Class 11–12) |
| `student@saews.demo` | Student |
| `analyst@saews.demo` | Analyst |
| `admin@saews.demo` | Admin |

> ⚠️ The live database is **shared** — anything any visitor does is visible to everyone.

### Option B — Run locally (Windows PowerShell)
```powershell
cd "D:\shemul project"
.\scripts\setup.ps1     # one time: venv, packages, DB, 300 synthetic students, train model, assess
.\scripts\run.ps1       # start the server
```
Open **http://localhost:8000** — interactive API docs at **http://localhost:8000/api/docs**.

Useful commands:
```powershell
.\.venv\Scripts\python.exe -m pytest                              # 29 automated tests
.\.venv\Scripts\python.exe scripts\smoke_test.py                  # 92 end-to-end checks (server must be running)
.\.venv\Scripts\python.exe -m backend.app.seed.generate --reset   # reset demo data
.\.venv\Scripts\python.exe -m backend.app.ml.train                # retrain the model
```

### Pages
| Page | Purpose |
|---|---|
| Dashboard | Risk summary and charts for your students |
| Alerts | Moderate / High / Critical students to review |
| Students | Search students in your scope; profile with trends, factors, warnings, recommendations |
| Interventions | Support plans, interventions, Support & Requests inbox |
| Data Import | Upload CSV → validate → commit |
| Reports | Aggregate, de-identified figures and exports |
| Administration | Users, audit log, model monitor (metrics, fairness), retention |
| My Progress (student) | Own trends, approved support, goals, requests |

### Sample data (`sample_data/`)
- `template_*.csv` — empty templates for each import type.
- `example_attendance_week11_SSC-MATH.csv`, `example_engagement_week11_SSC-MATH.csv` — valid files.
- `example_with_errors_attendance.csv` — deliberately broken file (shows line-level validation).

### Special demo students
| Student | Situation | What it shows |
|---|---|---|
| **S20260001** | Declining after the mid-term exam | **High risk** with clear factors |
| **S20260002** | Enrolled, no data | **Insufficient data** — the system refuses to guess |
| **S20260003** | Data stops at week 4 | **Stale / provisional** warning |

---

## Part 4 — How to present it

### Structure (about 15–20 minutes)
| # | Section | Time | Speaker |
|---|---|---|---|
| 1 | Title + team | 0:30 | Any |
| 2 | Problem: late detection of struggling students | 1:30 | Speaker 1 |
| 3 | Solution: the 6-step loop | 1:30 | Speaker 1 |
| 4 | Principles: human-in-the-loop, privacy, fairness, data honesty | 1:30 | Speaker 1 |
| 5 | Architecture + tech stack | 2:00 | Speaker 2 |
| 6 | ML model: features, explainability, fallback, metrics | 2:30 | Speaker 2 |
| 7 | **Live demo** (5 roles) | 6:00 | Speaker 3 |
| 8 | Testing: AT-01…AT-08, 29 tests, 92 smoke checks | 1:00 | Speaker 2 |
| 9 | Limitations + future work | 1:00 | Speaker 3 |
| 10 | Q&A | — | All |

### Live demo script

**1. Teacher (`teacher1`)** — *"This is what a teacher sees on Monday morning."*
- Dashboard → point at the risk distribution.
- Open a **High/Critical** alert (S20260001) → trend charts → read the **plain-language factors** aloud.
- *"Model version, timestamp and data freshness are stored with every prediction."*
- **Approve** a suggestion → it becomes a support plan with owner and due date.
- Record an intervention → record its outcome → show the before/after comparison.
- Bonus: open **S20260002** ("we refuse to predict without data") and **S20260003** ("we warn when data is old").

**2. Student (`student`)** — *"What the student sees — no risk label."*
- My Progress → approved plan visible; unapproved suggestions hidden.
- **Request a correction** (e.g. "my week 7 attendance is wrong").

**3. Advisor (`advisor1`)** — *"The request is routed to the right person."*
- Support & Requests → resolve the correction request.

**4. Admin (`admin`)** — *"Data quality is protected at the door."*
- Data Import → upload `example_with_errors_attendance.csv` → **rejected with line-level errors, nothing saved**.
- Upload `example_attendance_week11_SSC-MATH.csv` → validate → commit → background re-assessment.
- Administration → **Audit log** (earlier actions are logged) → **Model monitor** (metrics + fairness "Needs review").

**5. Analyst (`analyst`)** — *"Privacy for reporting."*
- Reports → aggregate figures only; small groups suppressed.
- Try the identifiable export → **refused and audited**.

### Key numbers
- 300 synthetic students in the demo; model trained on 1,500 synthetic historical students.
- ROC-AUC ≈ **0.83**, well calibrated (predicted vs observed within ~0.05 per band).
- High precision at the high threshold — when it says "high risk", it is usually right.
- All 10 functional requirements (FR1–FR10) implemented; SRS acceptance tests AT-01…AT-08 automated;
  **29/29 tests pass**.

---

## Part 5 — Questions to prepare for

| Question | Answer |
|---|---|
| Isn't labelling students harmful? | Students never see a risk label. Only staff do, and every action is supportive and human-approved. |
| Why logistic regression, not deep learning? | Explainability — each factor's contribution can be shown in plain language. It performs well on this data (AUC 0.83). |
| What if the model breaks? | Automatic, clearly labelled rule-based fallback; if both fail it says "Unavailable" instead of guessing. Tested in AT-05. |
| Is it fair? | No demographic features. We measure recall and false-positive gaps by class group, class and equity group; gaps above 0.10 are flagged "Needs review" — some are flagged in the demo, showing the check works. |
| Is it accurate on real students? | Unknown — it uses synthetic data. Real use needs institutional data, re-validation, consent, and thresholds agreed with stakeholders. |
| Low engagement means a lazy student? | No — it may reflect device, connectivity or disability barriers. Recommendations say "check access", not "assume a cause". |
| How is data protected? | Argon2id hashing, HttpOnly JWT cookie, rate-limited login, server-side role/record checks, security headers, audit log, retention purge, de-identified exports. |
| Can it handle more users / real deployment? | It already runs on PostgreSQL (Neon) on Vercel; Alembic migrations manage the schema; settings are environment variables (`EWS_*`). |

### Limitations & future work (SRS Appendix B)
- Trained and shown on **synthetic data only**; must be validated on approved real data.
- Thresholds, data fields, model choice, lawful basis/consent, retention periods and integrations
  must be confirmed with the institution.
- Linear model does not capture feature interactions.
- Future: school management system / education board result integrations, notifications, institution-tuned thresholds, real elicitation evidence.

---

## Part 6 — Pre-presentation checklist

- [ ] **Align model metrics with thresholds.** The committed metrics file
      (`backend/app/ml/artifacts/metrics_lr-20261120-191657.json`) was computed with thresholds 0.30/0.50/0.75,
      while the app uses 0.20/0.40/0.65 and `model_card.md` quotes figures at 0.20. Retrain with default
      settings (`python -m backend.app.ml.train`), commit the new artifacts (`git add -f`) and push, so the
      Model monitor matches the documentation.
- [ ] Do a full dry run the day before; the live database is shared and may have been changed by visitors.
- [ ] Keep the **local version running as a backup** in case the internet fails.
- [ ] Have the two sample CSV files easy to reach for the import step.
- [ ] Open tabs in advance: live site, `/api/docs`, the GitHub repository.
- [ ] State the disclaimer early: *"All data is synthetic. Model outputs are estimates, not decisions."*

---

## Team
Tanvir Hasan Siam (241-35-553) · Shah Ismat Mahmud Tanim (241-35-078) · Mahfuzur Rahman Shimul (241-35-175)
