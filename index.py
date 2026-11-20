"""Vercel entrypoint: exposes the FastAPI app (static UI + /api) as a single Python function."""

from backend.app.main import app  # noqa: F401
