"""The decision engine, the feedback policy and the five-agent pipeline (no LLM, no network)."""
from __future__ import annotations

import pytest

from app import agents, policy
from app.analytics import decision

FORECAST = {
    "expected_return_pct": 2.0,
    "daily_volatility_pct": 1.0,
    "horizon": 4,
    "model": {"selected": "ema", "beats_random_walk": True},
}


def signals(forecast=0.0, technical=0.0, sentiment=None, severity=None):
    out = [
        {"name": "forecast", "available": True, "score": forecast},
        {"name": "technical", "available": True, "score": technical},
        decision.anomaly_signal({"severity": severity, "count": 1 if severity else 0}),
    ]
    if sentiment is not None:
        out.append({"name": "sentiment", "available": True, "score": sentiment, "strength": 1.0})
    return out


def rule(result, name):
    return next(r for r in result["safety_rules"] if r["rule"] == name)


def test_forecast_signal_counts_only_a_model_that_beats_the_random_walk():
    useful = decision.forecast_signal(FORECAST)
    assert useful["available"] and useful["score"] == 1.0  # +2% against a 2% spread over 4 sessions
    useless = decision.forecast_signal({**FORECAST, "model": {"selected": "naive", "beats_random_walk": False}})
    assert not useless["available"] and useless["reason"] == "model_no_better_than_random_walk"
    assert not decision.forecast_signal(None)["available"]


def test_technical_signal():
    oversold = decision.technical_signal({"rsi": 20.0, "macd_histogram": 0.0, "sma_50": 10.0}, 10.0)
    overbought = decision.technical_signal({"rsi": 85.0, "macd_histogram": 0.0, "sma_50": 10.0}, 10.0)
    assert oversold["score"] > 0 > overbought["score"]
    assert decision.technical_signal({"rsi": 50.0, "macd_histogram": 0.0, "sma_50": 10.0}, 10.0)["score"] == 0.0
    assert not decision.technical_signal({}, 10.0)["available"]


def test_thresholds_depend_on_the_profile():
    mild = signals(forecast=0.2, technical=0.2)
    assert decision.decide(mild, "aggressive")["action"] == "BUY"
    assert decision.decide(mild, "conservative")["action"] == "HOLD"
    assert decision.decide(signals(forecast=-0.8, technical=-0.6), "moderate", held_weight=0.1)["action"] == "SELL"
    with pytest.raises(ValueError):
        decision.decide(mild, "reckless")


def test_safety_rules():
    strong = signals(forecast=0.9, technical=0.8)
    assert decision.decide(strong, "moderate")["action"] == "BUY"

    blocked = decision.decide(signals(forecast=0.9, technical=0.8, severity="critical"), "moderate")
    assert blocked["action"] == "HOLD" and blocked["proposed_action"] == "BUY" and rule(blocked, "recent_anomaly")["triggered"]
    assert decision.decide(signals(forecast=0.9, technical=0.8, severity="medium"), "moderate")["action"] == "BUY"

    assert decision.decide(strong, "moderate", listed=False)["action"] == "HOLD"
    assert decision.decide(strong, "conservative", traded_share=0.3)["action"] == "HOLD"
    assert decision.decide(strong, "aggressive", traded_share=0.3)["action"] == "BUY"  # warned, not blocked

    capped = decision.decide(strong, "moderate", held_weight=0.30)
    assert capped["action"] == "HOLD" and rule(capped, "position_cap")["triggered"]

    avoid = decision.decide(signals(forecast=-0.9, technical=-0.8), "moderate", held_weight=0.0)
    assert avoid["action"] == "AVOID" and rule(avoid, "no_short_selling")["triggered"]

    only_news = [{"name": "sentiment", "available": True, "score": 1.0, "strength": 1.0}]
    thin = decision.decide(only_news, "aggressive")
    assert thin["proposed_action"] == "BUY" and thin["action"] == "HOLD" and thin["coverage"] < decision.MIN_COVERAGE
    assert all("disclaimer" in decision.decide(s, "moderate") for s in (strong, only_news))


def test_trust_tilts_but_does_not_override():
    mixed = signals(forecast=0.6, technical=-0.3)
    neutral = decision.decide(mixed, "moderate")
    leaning = decision.decide(mixed, "moderate", trust={"forecast": 1.5, "technical": 0.5})
    assert leaning["score"] > neutral["score"]
    blocked = decision.decide(signals(0.9, 0.8, severity="high"), "moderate", trust={"forecast": 1.5, "technical": 1.5})
    assert blocked["action"] == "HOLD"


def test_policy_update():
    call = decision.decide(signals(forecast=0.9, technical=-0.2), "aggressive")
    assert call["action"] == "BUY"
    trust = {"forecast": 1.0, "technical": 1.0, "sentiment": 1.0}
    liked, taught = policy.update_trust(trust, call, liked=True)
    assert taught and liked["forecast"] > 1.0 and liked["technical"] < 1.0  # the dissenting signal was wrong
    disliked, _ = policy.update_trust(trust, call, liked=False)
    assert disliked["forecast"] < 1.0 and disliked["technical"] > 1.0
    hold = decision.decide(signals(0.0, 0.0), "moderate")
    assert policy.update_trust(trust, hold, liked=False) == (trust, False)
    for _ in range(50):
        trust, _ = policy.update_trust(trust, call, liked=True)
    assert trust["forecast"] == policy.HIGH and trust["technical"] == policy.LOW


# ------------------------------------------------------------- pipeline
def sign_up(client, email):
    response = client.post("/api/auth/register", json={"email": email, "username": "Agent", "password": "long enough"})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_pipeline_logs_every_handoff(client):
    response = client.post("/api/agents/run", json={"ticker": "alpha"})
    assert response.status_code == 201, response.text
    run = response.json()
    assert run["status"] == "done" and run["ticker"] == "ALPHA"
    chain = [(m["sender"], m["receiver"]) for m in run["messages"] if m["kind"] in {"task", "handoff", "result"}]
    assert chain == [
        ("orchestrator", "market"),
        ("market", "forecast"),
        ("forecast", "sentiment"),
        ("sentiment", "anomaly"),
        ("anomaly", "recommendation"),
        ("recommendation", "orchestrator"),
    ]
    assert [m["seq"] for m in run["messages"]] == list(range(1, len(run["messages"]) + 1))
    result = run["result"]
    assert result["action"] in {"BUY", "HOLD", "SELL", "AVOID"} and result["disclaimer"]
    assert {s["name"] for s in result["signals"]} == {"technical", "forecast", "sentiment", "anomaly"}
    sentiment = next(m for m in run["messages"] if m["sender"] == "sentiment")
    assert sentiment["payload"]["articles"] == 0 and not sentiment["payload"]["signal"]["available"]
    assert client.post("/api/agents/run", json={"ticker": "NOPE"}).status_code == 404


def test_a_failing_agent_does_not_stop_the_run(client, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("model crashed")

    monkeypatch.setattr(agents, "cached_forecast", broken)
    run = client.post("/api/agents/run", json={"ticker": "BETA"}).json()
    assert run["status"] == "done"
    failed = next(m for m in run["messages"] if m["sender"] == "forecast")
    assert failed["kind"] == "error" and "model crashed" in failed["summary"]
    assert "forecast" not in {s["name"] for s in run["result"]["signals"]}


def test_runs_are_private_to_their_owner(client):
    anonymous = client.post("/api/agents/run", json={"ticker": "GAMMA"}).json()
    amina = sign_up(client, "amina@example.com")
    sami = sign_up(client, "sami@example.com")
    mine = client.post("/api/agents/run", json={"ticker": "GAMMA"}, headers=amina).json()
    assert client.get(f"/api/agents/runs/{anonymous['id']}").status_code == 200
    assert client.get(f"/api/agents/runs/{mine['id']}", headers=amina).status_code == 200
    assert client.get(f"/api/agents/runs/{mine['id']}").status_code == 404
    assert client.get(f"/api/agents/runs/{mine['id']}", headers=sami).status_code == 404
    assert [r["id"] for r in client.get("/api/agents/runs", headers=amina).json()] == [mine["id"]]
    assert mine["id"] not in [r["id"] for r in client.get("/api/agents/runs").json()]


def test_feedback_updates_the_policy_once(client, monkeypatch):
    # Force a BUY so the verdict has a direction to learn from.
    monkeypatch.setattr(
        agents.decision, "decide", lambda *a, **k: {**ORIGINAL_DECIDE(*a, **k), "action": "BUY"}
    )
    headers = sign_up(client, "learner@example.com")
    run = client.post("/api/agents/run", json={"ticker": "DELTA"}, headers=headers).json()
    assert client.post(f"/api/agents/runs/{run['id']}/feedback", json={"liked": True}).status_code == 401
    first = client.post(f"/api/agents/runs/{run['id']}/feedback", json={"liked": True}, headers=headers)
    assert first.status_code == 200 and first.json()["feedback"] == 1
    assert client.post(f"/api/agents/runs/{run['id']}/feedback", json={"liked": False}, headers=headers).status_code == 409
    state = client.get("/api/agents/policy", headers=headers).json()
    assert state["feedback"] == 1 and set(state["trust"]) == {"forecast", "technical", "sentiment"}
    assert client.get(f"/api/agents/runs/{run['id']}", headers=headers).json()["feedback"] == {"liked": True}
    other = sign_up(client, "other@example.com")
    assert client.post(f"/api/agents/runs/{run['id']}/feedback", json={"liked": True}, headers=other).status_code == 404


ORIGINAL_DECIDE = decision.decide
