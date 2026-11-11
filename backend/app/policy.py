"""Learning from feedback: how much each user trusts each signal.

A small gradient bandit, in the spirit of Tradeili's feedback learning. The arms
are the three directional signals; a thumbs up or down on a BUY or SELL call is
the reward. A signal that agreed with a call the user liked gains weight, one
that agreed with a call they disliked loses it, and one that dissented from a
disliked call gains it. HOLD calls carry no direction and teach nothing.

Trust stays in [0.5, 1.5], so feedback can tilt the engine but never silence a
signal or override a safety rule.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from .analytics.decision import BASE_WEIGHTS
from .models import Feedback, PolicyState, User

LEARNING_RATE = 0.15
LOW, HIGH = 0.5, 1.5
DIRECTION = {"BUY": 1.0, "SELL": -1.0, "AVOID": -1.0, "HOLD": 0.0}


def get_state(db: Session, user: User) -> dict:
    row = db.get(PolicyState, user.id)
    state = dict(row.state) if row else {}
    trust = {name: float(state.get("trust", {}).get(name, 1.0)) for name in BASE_WEIGHTS}
    return {"trust": trust, "updates": int(state.get("updates", 0)), "feedback": int(state.get("feedback", 0))}


def update_trust(trust: dict[str, float], decision: dict, liked: bool) -> tuple[dict[str, float], bool]:
    """The new trust after one verdict, and whether the verdict taught anything."""
    direction = DIRECTION.get(decision.get("action", "HOLD"), 0.0)
    if direction == 0.0:
        return dict(trust), False
    reward = 1.0 if liked else -1.0
    new = dict(trust)
    for part in decision.get("contributions", []):
        agreement = direction * float(part["score"])
        value = new.get(part["name"], 1.0) + LEARNING_RATE * reward * agreement
        new[part["name"]] = round(min(HIGH, max(LOW, value)), 4)
    return new, True


def learn(db: Session, user: User, run_id: int, ticker: str, decision: dict, liked: bool) -> dict:
    """Record a verdict on a run's decision and update the user's trust."""
    state = get_state(db, user)
    trust, taught = update_trust(state["trust"], decision, liked)
    db.add(
        Feedback(
            user_id=user.id,
            run_id=run_id,
            ticker=ticker,
            action=decision.get("action", "HOLD"),
            liked=liked,
            reward=1.0 if liked else -1.0,
        )
    )
    row = db.get(PolicyState, user.id)
    new_state = {"trust": trust, "updates": state["updates"] + int(taught), "feedback": state["feedback"] + 1}
    if row is None:
        db.add(PolicyState(user_id=user.id, state=new_state))
    else:
        row.state = new_state
    db.commit()
    return {**new_state, "taught": taught}
