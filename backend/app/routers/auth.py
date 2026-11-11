"""Sign-up, sign-in and the investor profile."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..account import DEFAULT_CAPITAL
from ..analytics.portfolio import PROFILES, QUESTIONS, profile_from_answers
from ..db import get_db
from ..models import Portfolio, User
from ..security import create_token, current_user, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterIn(BaseModel):
    email: str = Field(max_length=255, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    username: str = Field(min_length=2, max_length=60)
    password: str = Field(min_length=8, max_length=72)
    answers: dict[str, str] | None = None
    initial_capital: float = Field(DEFAULT_CAPITAL, ge=1_000, le=10_000_000)

    @field_validator("email")
    @classmethod
    def lower(cls, value: str) -> str:
        return value.strip().lower()


class LoginIn(BaseModel):
    email: str
    password: str


class ProfileIn(BaseModel):
    answers: dict[str, str] | None = None
    risk_profile: str | None = None
    email_alerts: bool | None = None


def user_out(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "risk_profile": user.risk_profile,
        "email_alerts": user.email_alerts,
    }


def _profile(answers: dict[str, str]) -> str:
    try:
        return profile_from_answers(answers)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/questions")
def profile_questions() -> dict:
    """The sign-up questionnaire and the profiles it leads to."""
    return {"questions": QUESTIONS, "profiles": PROFILES}


@router.post("/register", status_code=201)
def register(body: RegisterIn, db: Session = Depends(get_db)) -> dict:
    if db.scalar(select(User).where(User.email == body.email)):
        raise HTTPException(status_code=409, detail="an account already uses this e-mail address")
    user = User(
        email=body.email,
        username=body.username.strip(),
        password_hash=hash_password(body.password),
        risk_profile=_profile(body.answers) if body.answers else "moderate",
        profile_answers=body.answers or {},
    )
    db.add(user)
    db.flush()
    db.add(Portfolio(user_id=user.id, initial_capital=body.initial_capital, cash=body.initial_capital))
    db.commit()
    return {"access_token": create_token(user.id), "token_type": "bearer", "user": user_out(user)}


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)) -> dict:
    user = db.scalar(select(User).where(User.email == body.email.strip().lower()))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="wrong e-mail address or password")
    return {"access_token": create_token(user.id), "token_type": "bearer", "user": user_out(user)}


@router.get("/me")
def me(user: User = Depends(current_user)) -> dict:
    return user_out(user)


@router.put("/profile")
def update_profile(body: ProfileIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    if body.answers is not None:
        user.risk_profile = _profile(body.answers)
        user.profile_answers = body.answers
    elif body.risk_profile is not None:
        if body.risk_profile not in PROFILES:
            raise HTTPException(status_code=422, detail=f"risk_profile must be one of {sorted(PROFILES)}")
        user.risk_profile = body.risk_profile
    if body.email_alerts is not None:
        user.email_alerts = body.email_alerts
    db.add(user)
    db.commit()
    return user_out(user)
