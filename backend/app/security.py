"""Passwords, login tokens and the FastAPI dependencies that read them."""
from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import User

ALGORITHM = "HS256"
_generated_secret = secrets.token_urlsafe(48)  # used when JWT_SECRET is empty; lasts until restart
_bearer = HTTPBearer(auto_error=False)


def _secret() -> str:
    return get_settings().jwt_secret or _generated_secret


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except ValueError:
        return False


def create_token(user_id: int) -> str:
    expires = datetime.now(UTC) + timedelta(minutes=get_settings().access_token_minutes)
    return jwt.encode({"sub": str(user_id), "exp": expires}, _secret(), algorithm=ALGORITHM)


def _user_from(credentials: HTTPAuthorizationCredentials | None, db: Session) -> User | None:
    if credentials is None:
        return None
    try:
        payload = jwt.decode(credentials.credentials, _secret(), algorithms=[ALGORITHM])
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
    return db.get(User, user_id)


def optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer), db: Session = Depends(get_db)
) -> User | None:
    """The signed-in user, or None for an anonymous or expired request."""
    return _user_from(credentials, db)


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer), db: Session = Depends(get_db)
) -> User:
    user = _user_from(credentials, db)
    if user is None:
        raise HTTPException(status_code=401, detail="sign in to use this feature", headers={"WWW-Authenticate": "Bearer"})
    return user
