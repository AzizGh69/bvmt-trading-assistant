"""The paper-trading account: valuation, orders and rebalancing.

Orders fill at the last close of the last session in the price history. There
is no order book, no fees and no partial fill: this is a simulator for
learning how an allocation behaves, not a broker.
"""
from __future__ import annotations

import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .analytics.market import MarketData
from .analytics.portfolio import allocation_returns, risk_metrics, stress_tests
from .models import Portfolio, Position, Transaction, User

DEFAULT_CAPITAL = 10_000.0


class OrderError(ValueError):
    pass


def get_portfolio(db: Session, user: User) -> Portfolio:
    portfolio = db.get(Portfolio, user.id)
    if portfolio is None:
        portfolio = Portfolio(user_id=user.id, initial_capital=DEFAULT_CAPITAL, cash=DEFAULT_CAPITAL)
        db.add(portfolio)
        db.commit()
    return portfolio


def positions_of(db: Session, user: User) -> list[Position]:
    rows = db.scalars(select(Position).where(Position.user_id == user.id, Position.quantity > 0)).all()
    return sorted(rows, key=lambda p: p.ticker)


def snapshot(db: Session, user: User, market: MarketData, risk_free_rate: float) -> dict:
    """Cash, positions at the last close, profit and loss, and the risk of the current weights."""
    portfolio = get_portfolio(db, user)
    stocks = market.stocks.set_index("ticker")
    rows, invested = [], 0.0
    for position in positions_of(db, user):
        known = position.ticker in stocks.index
        last_close = float(stocks.loc[position.ticker, "last_close"]) if known else position.avg_cost
        value = position.quantity * last_close
        cost = position.quantity * position.avg_cost
        invested += value
        rows.append(
            {
                "ticker": position.ticker,
                "name": str(stocks.loc[position.ticker, "name"]) if known else position.ticker,
                "sector": str(stocks.loc[position.ticker, "sector"]) if known else "Other",
                "quantity": position.quantity,
                "avg_cost": round(position.avg_cost, 3),
                "last_close": round(last_close, 3),
                "market_value": round(value, 2),
                "pnl": round(value - cost, 2),
                "pnl_pct": round((value / cost - 1.0) * 100.0, 2) if cost > 0 else 0.0,
            }
        )
    total = portfolio.cash + invested
    for row in rows:
        row["weight_pct"] = round(row["market_value"] / total * 100.0, 2) if total > 0 else 0.0
    sectors: dict[str, float] = {}
    for row in rows:
        sectors[row["sector"]] = sectors.get(row["sector"], 0.0) + row["weight_pct"]

    weights = pd.Series({r["ticker"]: r["market_value"] / total for r in rows if r["ticker"] in market.returns_matrix.columns}, dtype=float)
    if weights.empty:
        risk, stress = None, []
    else:
        history = allocation_returns(market.returns_matrix.tail(250), weights)
        risk = risk_metrics(history, risk_free_rate, total)
        stress = stress_tests(market, weights)
    return {
        "session": market.last_session.date().isoformat(),
        "initial_capital": round(portfolio.initial_capital, 2),
        "cash": round(portfolio.cash, 2),
        "invested": round(invested, 2),
        "total_value": round(total, 2),
        "pnl": round(total - portfolio.initial_capital, 2),
        "pnl_pct": round((total / portfolio.initial_capital - 1.0) * 100.0, 2) if portfolio.initial_capital > 0 else 0.0,
        "positions": sorted(rows, key=lambda r: r["market_value"], reverse=True),
        "sectors": [{"sector": s, "weight_pct": round(w, 2)} for s, w in sorted(sectors.items(), key=lambda kv: -kv[1])],
        "risk": risk,  # of today's weights over the last 250 sessions, not of the account's own past
        "stress_tests": stress,
    }


def _fill(db: Session, user: User, portfolio: Portfolio, market: MarketData, ticker: str, side: str, quantity: int) -> Transaction:
    stocks = market.stocks.set_index("ticker")
    symbol = market.resolve(ticker)
    if side == "BUY" and not bool(stocks.loc[symbol, "listed"]):
        raise OrderError(f"{symbol} is no longer listed")
    price = float(stocks.loc[symbol, "last_close"])
    position = db.get(Position, (user.id, symbol))
    amount = quantity * price
    if side == "BUY":
        if amount > portfolio.cash + 1e-9:
            raise OrderError(f"not enough cash: the order costs {amount:.2f} TND, {portfolio.cash:.2f} TND available")
        if position is None:
            position = Position(user_id=user.id, ticker=symbol, quantity=0, avg_cost=0.0)
            db.add(position)
        position.avg_cost = (position.quantity * position.avg_cost + amount) / (position.quantity + quantity)
        position.quantity += quantity
        portfolio.cash -= amount
    else:
        held = position.quantity if position else 0
        if quantity > held:
            raise OrderError(f"cannot sell {quantity} {symbol}: {held} held")
        position.quantity -= quantity
        if position.quantity == 0:
            position.avg_cost = 0.0
        portfolio.cash += amount
    transaction = Transaction(
        user_id=user.id, ticker=symbol, side=side, quantity=quantity, price=price, session_date=market.last_session.date()
    )
    db.add(transaction)
    return transaction


def place_order(db: Session, user: User, market: MarketData, ticker: str, side: str, quantity: int) -> Transaction:
    side = side.upper()
    if side not in {"BUY", "SELL"}:
        raise OrderError("side must be BUY or SELL")
    if quantity <= 0:
        raise OrderError("quantity must be positive")
    portfolio = get_portfolio(db, user)
    try:
        transaction = _fill(db, user, portfolio, market, ticker, side, quantity)
    except OrderError:
        db.rollback()
        raise
    db.commit()
    return transaction


def reset(db: Session, user: User, initial_capital: float) -> None:
    """Start over: no positions, no history, a fresh amount of cash."""
    portfolio = get_portfolio(db, user)
    db.execute(delete(Position).where(Position.user_id == user.id))
    db.execute(delete(Transaction).where(Transaction.user_id == user.id))
    portfolio.initial_capital = initial_capital
    portfolio.cash = initial_capital
    db.commit()


def rebalance(db: Session, user: User, market: MarketData, target_weights: dict[str, float]) -> list[Transaction]:
    """Trade the account to the target weights (fractions of its total value)."""
    portfolio = get_portfolio(db, user)
    stocks = market.stocks.set_index("ticker")
    held = {p.ticker: p.quantity for p in positions_of(db, user)}
    total = portfolio.cash + sum(q * float(stocks.loc[t, "last_close"]) for t, q in held.items() if t in stocks.index)
    targets = {t: int(total * w // float(stocks.loc[t, "last_close"])) for t, w in target_weights.items() if w > 0}
    done = []
    try:
        # Sells first, so the cash they free can pay for the buys.
        for ticker, quantity in held.items():
            excess = quantity - targets.get(ticker, 0)
            if excess > 0:
                done.append(_fill(db, user, portfolio, market, ticker, "SELL", excess))
        for ticker, target in targets.items():
            missing = target - held.get(ticker, 0)
            if missing > 0:
                done.append(_fill(db, user, portfolio, market, ticker, "BUY", missing))
    except OrderError:
        db.rollback()
        raise
    db.commit()
    return done
