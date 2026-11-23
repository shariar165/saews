"""FastAPI application: JSON API under /api and the role-based web UI served from /frontend."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from .api import admin, ai, auth, imports, me, meta, reports, risk, students, workflow
from .config import PROJECT_ROOT, get_settings
from .core.ratelimit import limiter

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("saews")

CSP = ("default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; "
       "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title="SAEWS API",
        description="AI-Driven Socio-Academic Early Warning & Personalized Decision Support System. "
                    "Model outputs are estimates to support — never replace — human judgment.",
        version="1.0.0",
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        else:  # static UI: always revalidate (cheap 304 via ETag) so users never run stale JS/CSS after an update
            response.headers.setdefault("Cache-Control", "no-cache")
        if not request.url.path.startswith("/api/docs"):
            response.headers.setdefault("Content-Security-Policy", CSP)
        return response

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):  # secure error handling: no stack traces to clients
        log.exception("Unhandled error on %s", request.url.path)
        return JSONResponse({"detail": "An internal error occurred. It has been logged."}, status_code=500)

    for r in (auth.router, meta.router, students.router, students.staff_router, risk.router, workflow.router,
              me.router, imports.router, reports.router, admin.router, ai.router):
        app.include_router(r, prefix="/api")

    frontend = PROJECT_ROOT / "frontend"
    if frontend.exists():
        app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
    if s.jwt_secret.startswith("dev-only") and s.environment == "production":
        raise RuntimeError("Set EWS_JWT_SECRET before running in production")
    return app


app = create_app()
