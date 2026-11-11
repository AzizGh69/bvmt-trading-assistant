"""Optimiser, risk measures, accounts and the paper-trading simulator."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.analytics.portfolio import (
    PROFILES,
    allocation_returns,
    estimate,
    explain,
    max_drawdown,
    optimise,
    profile_from_answers,
    recommend,
    risk_metrics,
    select_universe,
    stress_tests,
    universe_returns,
)


def test_profile_scoring():
    assert profile_from_answers({"horizon": "short", "loss_reaction": "sell", "experience": "none"}) == "conservative"
    assert profile_from_answers({"horizon": "medium", "loss_reaction": "hold", "experience": "some"}) == "moderate"
    assert profile_from_answers({"horizon": "long", "loss_reaction": "buy_more", "experience": "experienced"}) == "aggressive"
    with pytest.raises(ValueError):
        profile_from_answers({"horizon": "forever", "loss_reaction": "hold", "experience": "some"})


def inputs(market):
    tickers = select_universe(market)
    return estimate(universe_returns(market, tickers))


def test_universe_keeps_only_liquid_listed_stocks(prices):
    from app.analytics.market import MarketData

    frame = prices.copy()
    rarely = (frame["ticker"] == "ZETA") & (np.arange(len(frame)) % 3 != 0)
    frame.loc[rarely, "traded"] = False
    gone = (frame["ticker"] == "EPSILON") & (frame["date"] > frame["date"].max() - pd.Timedelta(days=30))
    universe = select_universe(MarketData(frame[~gone]))
    assert "ZETA" not in universe and "EPSILON" not in universe and len(universe) == 4


def test_weights_are_long_only_capped_and_sum_to_one(market):
    mu, cov = inputs(market)
    for settings in PROFILES.values():
        weights = optimise(mu, cov, settings["risk_aversion"], settings["max_weight"])
        cap = max(settings["max_weight"], 1 / len(mu)) + 1e-6
        assert abs(weights.sum() - 1.0) < 1e-9 and (weights >= 0).all() and (weights <= cap).all()


def test_more_risk_aversion_means_less_volatility(market):
    mu, cov = inputs(market)

    def volatility(aversion: float) -> float:
        w = optimise(mu, cov, aversion, 1.0)
        return float(np.sqrt(w @ cov @ w))

    assert volatility(50.0) <= volatility(5.0) <= volatility(0.5)


def test_the_optimum_beats_equal_weights_on_its_own_objective(market):
    mu, cov = inputs(market)
    aversion = 5.0
    best = optimise(mu, cov, aversion, 1.0)
    equal = pd.Series(1 / len(mu), index=mu.index)

    def utility(w: pd.Series) -> float:
        return float(w @ mu - 0.5 * aversion * (w @ cov @ w))

    assert utility(best) >= utility(equal) - 1e-9


def test_explanation_adds_up(market):
    mu, cov = inputs(market)
    weights = optimise(mu, cov, 5.0, 0.5)
    rows = explain(weights, mu, cov)
    assert abs(sum(r["risk_share_pct"] for r in rows) - 100.0) < 0.1
    assert abs(sum(r["return_contribution_pct"] for r in rows) - float(weights @ mu) * 100.0) < 0.1
    assert abs(sum(r["weight_pct"] for r in rows) - 100.0) < 0.1
    assert {r["reason"] for r in rows} <= {"diversifier", "return_driver", "core"}


def test_max_drawdown_and_risk_metrics():
    assert max_drawdown(np.array([100.0, 120.0, 90.0, 110.0, 99.0])) == pytest.approx(-0.25)
    assert max_drawdown(np.array([1.0, 2.0, 3.0])) == 0.0
    returns = pd.Series(np.tile([0.01, -0.02, 0.015, 0.0], 60))
    metrics = risk_metrics(returns, risk_free_rate=0.07, value=10_000)
    assert metrics["var95_pct"] == 2.0 and metrics["cvar95_pct"] == 2.0 and metrics["var95_tnd"] == 200.0
    assert metrics["volatility_pct"] > 0 and metrics["max_drawdown_pct"] < 0
    assert risk_metrics(pd.Series([0.01] * 5), 0.07)["sharpe"] is None  # too short to say anything


def test_stress_tests_cover_history_and_hypotheses(market):
    weights = pd.Series({"ALPHA": 0.5, "BETA": 0.3, "GAMMA": 0.1})
    scenarios = {s["name"]: s for s in stress_tests(market, weights)}
    assert set(scenarios) == {"worst_20_sessions", "worst_session", "market_minus_10", "largest_sector_minus_15"}
    assert scenarios["market_minus_10"]["portfolio_pct"] == pytest.approx(-9.0)  # 10% of it is cash
    assert scenarios["largest_sector_minus_15"]["sector"] == "Banks"
    assert scenarios["largest_sector_minus_15"]["portfolio_pct"] == pytest.approx(-12.0)
    assert scenarios["worst_20_sessions"]["market_pct"] < 0


def test_recommendation_is_complete(market):
    plan = recommend(market, "moderate", risk_free_rate=0.07, capital=20_000)
    assert abs(sum(h["weight_pct"] for h in plan["holdings"]) - 100.0) < 0.1
    assert all(h["shares"] >= 0 and h["amount_tnd"] <= 20_000 * h["weight_pct"] / 100 + 0.01 for h in plan["holdings"])
    assert len(plan["frontier"]) == 12 and plan["stress_tests"] and plan["history"]
    check = plan["out_of_sample"]
    assert check["chosen_on"][1] < check["scored_on"][0]  # scored only on sessions it never saw
    assert check["portfolio"]["volatility_pct"] > 0 and check["equal_weight"]["volatility_pct"] > 0
    assert plan["in_sample"]["var95_tnd"] > 0
    volatilities = [p["volatility_pct"] for p in plan["frontier"]]
    assert volatilities == sorted(volatilities, reverse=True)  # the frontier runs from risky to safe
    with pytest.raises(ValueError):
        recommend(market, "reckless", 0.07)


def test_allocation_returns_leave_cash_idle(market):
    returns = market.returns_matrix.tail(50)
    half = allocation_returns(returns, pd.Series({"ALPHA": 0.5}))
    full = allocation_returns(returns, pd.Series({"ALPHA": 1.0}))
    assert np.allclose(half, full / 2)


# ------------------------------------------------------------------- API
ANSWERS = {"horizon": "long", "loss_reaction": "buy_more", "experience": "experienced"}


def sign_up(client, email="amina@example.com", **extra) -> dict:
    response = client.post(
        "/api/auth/register",
        json={"email": email, "username": "Amina", "password": "correct horse", "answers": ANSWERS, **extra},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_api_accounts(client):
    headers = sign_up(client, email="Amina@Example.com")
    me = client.get("/api/auth/me", headers=headers).json()
    assert me["email"] == "amina@example.com" and me["risk_profile"] == "aggressive"
    assert client.post("/api/auth/register", json={"email": "amina@example.com", "username": "A2", "password": "another one"}).status_code == 409
    assert client.post("/api/auth/login", json={"email": "amina@example.com", "password": "wrong"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "amina@example.com", "password": "correct horse"}).status_code == 200
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer nonsense"}).status_code == 401
    assert client.post("/api/auth/register", json={"email": "bad", "username": "x", "password": "short"}).status_code == 422
    updated = client.put("/api/auth/profile", headers=headers, json={"risk_profile": "conservative", "email_alerts": True}).json()
    assert updated["risk_profile"] == "conservative" and updated["email_alerts"] is True
    assert client.put("/api/auth/profile", headers=headers, json={"risk_profile": "reckless"}).status_code == 422


def test_api_paper_trading(client):
    headers = sign_up(client, initial_capital=5_000)
    empty = client.get("/api/portfolio", headers=headers).json()
    assert empty["cash"] == 5_000 and empty["positions"] == [] and empty["risk"] is None
    assert client.get("/api/portfolio").status_code == 401

    price = client.get("/api/stocks/ALPHA").json()["quote"]["close"]
    bought = client.post("/api/portfolio/orders", headers=headers, json={"ticker": "alpha", "side": "buy", "quantity": 50})
    assert bought.status_code == 201
    acct = bought.json()["account"]
    assert acct["cash"] == pytest.approx(5_000 - 50 * price, abs=0.01)
    assert acct["positions"][0]["ticker"] == "ALPHA" and acct["positions"][0]["quantity"] == 50
    assert acct["total_value"] == pytest.approx(5_000, abs=0.01) and acct["pnl"] == pytest.approx(0, abs=0.01)
    assert acct["risk"]["volatility_pct"] > 0 and len(acct["stress_tests"]) == 4

    too_much = client.post("/api/portfolio/orders", headers=headers, json={"ticker": "ALPHA", "side": "BUY", "quantity": 100_000})
    assert too_much.status_code == 422 and "not enough cash" in too_much.json()["detail"]
    oversell = client.post("/api/portfolio/orders", headers=headers, json={"ticker": "ALPHA", "side": "SELL", "quantity": 51})
    assert oversell.status_code == 422
    assert client.post("/api/portfolio/orders", headers=headers, json={"ticker": "NOPE", "side": "BUY", "quantity": 1}).status_code == 404
    assert client.post("/api/portfolio/orders", headers=headers, json={"ticker": "ALPHA", "side": "HOLD", "quantity": 1}).status_code == 422

    sold = client.post("/api/portfolio/orders", headers=headers, json={"ticker": "ALPHA", "side": "SELL", "quantity": 50}).json()
    assert sold["account"]["positions"] == [] and sold["account"]["cash"] == pytest.approx(5_000, abs=0.01)
    history = client.get("/api/portfolio/transactions", headers=headers).json()
    assert [t["side"] for t in history] == ["SELL", "BUY"]

    fresh = client.post("/api/portfolio/reset", headers=headers, json={"initial_capital": 20_000}).json()
    assert fresh["cash"] == 20_000 and client.get("/api/portfolio/transactions", headers=headers).json() == []


def test_api_recommendation_and_rebalance(client):
    public = client.get("/api/portfolio/recommendation", params={"profile": "conservative", "capital": 10_000})
    assert public.status_code == 200 and public.json()["profile"] == "conservative"
    assert client.get("/api/portfolio/recommendation", params={"profile": "reckless"}).status_code == 422

    headers = sign_up(client)
    mine = client.get("/api/portfolio/recommendation", headers=headers).json()
    assert mine["profile"] == "aggressive"  # taken from the account when not given

    applied = client.post("/api/portfolio/apply-recommendation", headers=headers).json()
    acct = applied["account"]
    assert applied["orders"] > 0 and acct["cash"] >= 0 and acct["invested"] > 0.9 * acct["total_value"]
    target = {h["ticker"]: h["weight_pct"] for h in mine["holdings"]}
    for position in acct["positions"]:
        assert abs(position["weight_pct"] - target[position["ticker"]]) < 2.0
    again = client.post("/api/portfolio/apply-recommendation", headers=headers).json()
    assert again["orders"] == 0  # already on target
