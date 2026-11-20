# API overview

Interactive OpenAPI docs: **`/api/docs`** (Swagger UI) · schema: `/api/openapi.json`.
Authentication: `POST /api/auth/login` sets an HttpOnly session cookie. API clients may also send `Authorization: Bearer <token>`.

| Area | Endpoints |
|---|---|
| Auth | `POST /auth/login` · `POST /auth/logout` · `GET /auth/me` |
| Meta | `GET /health` · `GET /meta` |
| Students (staff) | `GET /students` · `GET /students/{id}` · `/indicators` · `/assessments` · `POST /students/{id}/assess` · `/recommendations` · `/plans` · `/requests` · `GET /staff` |
| Risk | `GET /risk/alerts` · `GET /risk/summary` · `POST /risk/{id}/review` · `POST /risk/{id}/flag` |
| Workflow | `POST /recommendations/{id}/approve` · `/dismiss` · `GET/POST /plans` · `PATCH /plans/{id}` · `POST /plans/{id}/interventions` · `PATCH /interventions/{id}` · `GET /requests` · `PATCH /requests/{id}` |
| Student portal | `GET /me/profile` · `/indicators` · `/support` · `GET/POST /me/goals` · `PATCH/DELETE /me/goals/{id}` · `GET/POST /me/requests` |
| Imports | `GET /imports/kinds` · `GET /imports/template/{kind}` · `GET /imports` · `POST /imports/validate` · `POST /imports/{id}/commit` |
| Reports | `GET /reports/summary` · `GET /reports/trends` · `GET /reports/export?identifiable=` |
| Admin | `GET/POST /admin/users` · `PATCH /admin/users/{id}` · `GET /admin/audit` · `GET /admin/model` · `POST /admin/recompute` · `POST /admin/retention` |

All endpoints are prefixed with `/api`. Errors return `{"detail": "..."}` with an appropriate HTTP status.
