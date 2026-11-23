# Architecture

## Overview

```mermaid
flowchart LR
  subgraph Browser
    UI[Role-based web UI<br/>HTML/CSS/ES modules + Chart.js]
  end
  subgraph Server[FastAPI service]
    API[REST API /api/*<br/>auth · students · risk · workflow · me · imports · reports · admin]
    AUTH[AuthN/AuthZ<br/>Argon2id · JWT cookie · role + record scope]
    RISK[Risk engine]
    REC[Recommendation engine]
    IMP[Import validator]
    AUD[Audit logger]
    AI[AI assistant<br/>optional · drafts only]
    BG[Background refresh<br/>BackgroundTasks]
  end
  subgraph ML[ML layer]
    FEAT[Feature pipeline<br/>pandas]
    MODEL[Logistic regression<br/>scikit-learn, versioned artifact]
    RULES[Transparent rules<br/>baseline + fallback]
  end
  DB[(SQLite / PostgreSQL)]
  CSV[/Approved CSV files/]

  UI <-->|JSON, HttpOnly cookie| API
  API --> AUTH --> AUD --> DB
  CSV --> IMP --> DB
  IMP --> BG --> RISK
  API --> RISK --> FEAT --> DB
  RISK --> MODEL
  RISK -. model unavailable .-> RULES
  RISK --> REC --> DB
  API --> AI
  AI -->|pseudonymized indicators only| CLAUDE[(Claude API<br/>Anthropic)]
  AI --> AUD
```

## Risk-assessment pipeline (SRS §7.3)

```mermaid
flowchart TD
  A[Validated data: attendance · class tests/exams · homework · online-portal activity · previous exam GPA] --> B[Feature extraction<br/>rates, recent-vs-earlier trends]
  B --> C{Completeness ≥ 60%?}
  C -- No --> X[Insufficient data<br/>no prediction shown]
  C -- Yes --> D{Model available?}
  D -- Yes --> E[Model probability + per-feature contributions]
  D -- No --> F{Rules OK?}
  F -- Yes --> G[Rule-based fallback, labelled]
  F -- No --> U[Prediction unavailable]
  E --> H[Risk level + plain-language factors<br/>+ stale/missing-data warnings]
  G --> H
  H --> I{Moderate or higher?}
  I -- Yes --> J[Proposed recommendations]
  J --> K[Human review: approve / edit / dismiss]
  K --> L[Support plan → interventions → outcome + before/after indicators]
  I -- No --> M[Routine monitoring]
```

## Activity flow (SRS §7.2)

```mermaid
sequenceDiagram
  actor T as Teacher/Advisor
  participant S as SAEWS
  actor St as Student
  T->>S: Upload CSV
  S-->>T: Validation report (line-level errors) / OK
  T->>S: Commit
  S->>S: Background re-assessment of affected students
  T->>S: Open alert → review factors & data quality
  T->>S: Approve (edit) recommendation, set owner + due date
  S-->>St: Approved support visible in portal
  St->>S: Request help / correction
  S-->>T: Routed to advisor inbox (audited)
  T->>S: Record intervention + outcome
  S-->>T: Before/after indicator comparison
```

## Data model (SRS §7.4, extended)

```mermaid
erDiagram
  USERS ||--o| STUDENTS : "student login"
  USERS ||--o{ STUDENTS : advises
  USERS ||--o{ COURSES : teaches
  STUDENTS ||--o{ ENROLLMENTS : has
  COURSES ||--o{ ENROLLMENTS : has
  STUDENTS ||--o{ ATTENDANCE_RECORDS : records
  STUDENTS ||--o{ ASSESSMENT_SCORES : records
  STUDENTS ||--o{ ASSIGNMENT_SUBMISSIONS : records
  STUDENTS ||--o{ ENGAGEMENT_WEEKLY : records
  IMPORT_BATCHES ||--o{ ATTENDANCE_RECORDS : "traceable to"
  STUDENTS ||--o{ RISK_ASSESSMENTS : generates
  RISK_ASSESSMENTS ||--o{ RECOMMENDATIONS : proposes
  RECOMMENDATIONS ||--o| SUPPORT_PLANS : "approved into"
  SUPPORT_PLANS ||--o{ INTERVENTIONS : contains
  STUDENTS ||--o{ STUDENT_REQUESTS : raises
  STUDENTS ||--o{ STUDY_GOALS : sets
  USERS ||--o{ AUDIT_LOGS : performs
```

## Authorization model

| Role | Individual student records | Write actions | Reports |
|---|---|---|---|
| Teacher | Students enrolled in own subjects | Review/flag alerts, approve recs, plans, interventions, import indicators for own subjects | Own subjects |
| Advisor (class advisor) | Students in own class group | Same as teacher (no imports) | Own students |
| Student | Self only (no risk labels, approved support only) | Goals, help/correction requests | — |
| Analyst | None | — | De-identified, small cells suppressed; identifiable export only if `identifiable_access` granted |
| Admin | All (audited) | Users/roles, imports, recompute, retention | All |

Every check is enforced server-side; denied attempts are written to the audit log.

## Security & privacy controls (SRS §6.2)
- Argon2id password hashing; signed JWT in an `HttpOnly`, `SameSite=Strict` cookie (set `EWS_COOKIE_SECURE=true` behind HTTPS).
- Login rate limiting; parameterized queries via SQLAlchemy; Pydantic input validation; upload type/size/encoding checks.
- Security headers (CSP, `X-Frame-Options`, `nosniff`); generic error responses without stack traces.
- Data minimization: only academic/engagement indicators are features; the synthetic `equity_group` is evaluation-only.
- Audit trail for views, denials, exports, imports, logins and role changes; configurable retention purge.
