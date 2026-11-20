from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..core.audit import audit
from ..core.deps import get_current_user
from ..core.ratelimit import limiter
from ..core.security import create_access_token, verify_password
from ..database import get_db
from ..models import User
from .serializers import user_out

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=256)


@router.post("/login")
@limiter.limit(get_settings().login_rate_limit)
def login(request: Request, response: Response, body: LoginIn, db: Session = Depends(get_db)):
    s = get_settings()
    user = db.scalar(select(User).where(func.lower(User.email) == body.email.strip().lower()))
    if not user or not user.is_active or not verify_password(body.password, user.password_hash):
        audit(db, "auth.login", user=user, request=request, outcome="denied",
              detail={"email": body.email.strip().lower()[:255]})
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    user.last_login_at = datetime.now(UTC)
    audit(db, "auth.login", user=user, request=request)
    token = create_access_token(user.id, user.role)
    response.set_cookie(s.cookie_name, token, max_age=s.access_token_minutes * 60, httponly=True,
                        secure=s.cookie_secure, samesite="strict", path="/")
    return {"user": user_out(user)}


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    response.delete_cookie(get_settings().cookie_name, path="/")
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return {"user": user_out(user)}
