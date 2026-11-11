"""Run the agent pipeline on a stock, replay a run, and give feedback on its call."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import policy
from ..agents import Pipeline, run_out
from ..analytics.market import UnknownTicker
from ..db import get_db
from ..models import AgentMessage, AgentRun, Feedback, User
from ..security import current_user, optional_user
from .market import market_or_503

router = APIRouter(prefix="/api/agents", tags=["agents"])


class RunIn(BaseModel):
    ticker: str


class FeedbackIn(BaseModel):
    liked: bool


def _visible(run: AgentRun | None, user: User | None) -> AgentRun:
    """Anonymous runs are shared; a signed-in user's runs are theirs alone."""
    if run is None or (run.user_id is not None and (user is None or run.user_id != user.id)):
        raise HTTPException(status_code=404, detail="run not found")
    return run


def _messages(db: Session, run: AgentRun) -> list[AgentMessage]:
    return db.scalars(select(AgentMessage).where(AgentMessage.run_id == run.id).order_by(AgentMessage.seq)).all()


@router.post("/run", status_code=201)
def run_pipeline(body: RunIn, user: User | None = Depends(optional_user), db: Session = Depends(get_db)) -> dict:
    """Analyse one stock with the five agents and return every hand-off."""
    pipeline = Pipeline(db, market_or_503(), user=user)
    try:
        run = pipeline.run_for(body.ticker)
    except UnknownTicker as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=f"unknown stock: {body.ticker}") from exc
    return run_out(run, _messages(db, run))


@router.get("/runs")
def list_runs(
    limit: int = Query(20, ge=1, le=100), user: User | None = Depends(optional_user), db: Session = Depends(get_db)
) -> list[dict]:
    owner = AgentRun.user_id == user.id if user else AgentRun.user_id.is_(None)
    rows = db.scalars(select(AgentRun).where(owner).order_by(AgentRun.id.desc()).limit(limit)).all()
    return [run_out(r) for r in rows]


@router.get("/runs/{run_id}")
def get_run(run_id: int, user: User | None = Depends(optional_user), db: Session = Depends(get_db)) -> dict:
    run = _visible(db.get(AgentRun, run_id), user)
    out = run_out(run, _messages(db, run))
    if user:
        verdict = db.scalar(select(Feedback).where(Feedback.run_id == run.id, Feedback.user_id == user.id))
        out["feedback"] = None if verdict is None else {"liked": verdict.liked}
    return out


@router.post("/runs/{run_id}/feedback")
def give_feedback(run_id: int, body: FeedbackIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """A thumbs up or down on a run's call; BUY and SELL calls update the user's signal trust."""
    run = db.get(AgentRun, run_id)
    if run is None or run.user_id != user.id:
        raise HTTPException(status_code=404, detail="run not found")
    if run.status != "done":
        raise HTTPException(status_code=422, detail="this run produced no recommendation")
    if db.scalar(select(Feedback).where(Feedback.run_id == run.id)):
        raise HTTPException(status_code=409, detail="feedback already given for this run")
    return policy.learn(db, user, run.id, run.ticker, run.result, body.liked)


@router.get("/policy")
def get_policy(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """How much the engine currently trusts each signal for this user (1 = neutral)."""
    return {**policy.get_state(db, user), "range": [policy.LOW, policy.HIGH], "learning_rate": policy.LEARNING_RATE}
