"""The agent pipeline: five agents analyse one stock and hand off to each other.

    orchestrator -> market -> forecast -> sentiment -> anomaly -> recommendation -> orchestrator

Each agent does one job and passes what it found to the next. Every hand-off is
written to ``agent_messages``, so a run can be replayed on screen step by step.
An agent that fails does not stop the run: it reports the failure, its signal
is left out, and the recommendation agent's safety rules decide whether what is
left is enough to act on. The structure (named agents, logged hand-offs,
enforced safety rules) follows Tradeili's design; the code is this project's.
"""
from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from . import news, policy
from .account import get_portfolio, positions_of
from .analytics import decision
from .analytics.anomalies import stock_signal
from .analytics.forecasting import NotEnoughHistory, cached_forecast
from .analytics.indicators import technical_summary
from .analytics.market import MarketData
from .config import Settings, get_settings
from .models import AgentMessage, AgentRun, User

log = logging.getLogger("bvmt.agents")

AGENTS = ["market", "forecast", "sentiment", "anomaly", "recommendation"]


class Pipeline:
    def __init__(self, db: Session, market: MarketData, settings: Settings | None = None, user: User | None = None):
        self.db, self.market, self.user = db, market, user
        self.settings = settings or get_settings()
        self.seq = 0
        self.run: AgentRun | None = None

    # ------------------------------------------------------------- logging
    def say(self, sender: str, receiver: str, kind: str, summary: str, payload: dict | None = None) -> None:
        self.seq += 1
        self.db.add(
            AgentMessage(
                run_id=self.run.id, seq=self.seq, sender=sender, receiver=receiver, kind=kind,
                summary=summary, payload=payload or {},
            )
        )
        self.db.flush()

    def step(self, name: str, receiver: str, work):
        """Run one agent; on failure log it and hand off nothing."""
        started = time.perf_counter()
        try:
            summary, payload = work()
        except Exception as exc:  # an agent's failure must not end the run
            log.warning("agent %s failed: %s", name, exc)
            self.say(name, receiver, "error", f"{name} failed: {type(exc).__name__}: {exc}", {"error": str(exc)})
            return None
        payload["elapsed_ms"] = round((time.perf_counter() - started) * 1000.0, 1)
        self.say(name, receiver, "handoff", summary, payload)
        return payload

    # -------------------------------------------------------------- agents
    def market_agent(self, symbol: str):
        def work():
            info = self.market.info(symbol)
            history = self.market.history(symbol)
            last = history.iloc[-1]
            recent = history.tail(60)
            technical = technical_summary(history)
            refreshed = None
            if self.settings.enable_scraping:
                try:
                    refreshed = news.refresh_news(self.db, self.market, self.settings)
                except Exception as exc:  # live sources are best effort
                    refreshed = {"error": type(exc).__name__}
            payload = {
                "ticker": symbol,
                "name": info["name"],
                "sector": info["sector"],
                "listed": info["listed"],
                "session": last["date"].date().isoformat(),
                "close": round(float(last["close"]), 3),
                "traded_share_60": round(float(recent["traded"].mean()), 2),
                "technical": {k: v for k, v in technical.items() if k != "readings"},
                "news_refresh": refreshed if refreshed is not None else "disabled",
            }
            # The technical signal is read from the market agent's own indicators.
            payload["signal"] = decision.technical_signal(payload["technical"], payload["close"])
            summary = f"{symbol} closed at {payload['close']} on {payload['session']}; traded on {payload['traded_share_60']:.0%} of the last 60 sessions"
            return summary, payload

        return self.step("market", "forecast", work)

    def forecast_agent(self, symbol: str):
        def work():
            try:
                result = cached_forecast(self.market, symbol, 5)
            except NotEnoughHistory as exc:
                return f"no forecast: {exc}", {"available": False, "reason": str(exc)}
            signal = decision.forecast_signal(result)
            payload = {
                "available": True,
                "model": result["model"],
                "expected_return_pct": result["expected_return_pct"],
                "daily_volatility_pct": result["daily_volatility_pct"],
                "horizon": result["horizon"],
                "last_price": result["forecast"][-1]["price"],
                "lower80": result["forecast"][-1]["lower80"],
                "upper80": result["forecast"][-1]["upper80"],
                "backtest": result["backtest"]["models"],
                "signal": signal,
            }
            verdict = "beats" if result["model"]["beats_random_walk"] else "does not beat"
            summary = f"{result['model']['selected']} expects {result['expected_return_pct']:+.2f}% over 5 sessions and {verdict} the random walk"
            return summary, payload

        return self.step("forecast", "sentiment", work)

    def sentiment_agent(self, symbol: str):
        def work():
            found = news.ticker_sentiment(self.db, symbol, days=30)
            signal = decision.sentiment_signal(found)
            payload = {**found, "signal": signal, "scraping_enabled": self.settings.enable_scraping}
            if not found["articles"]:
                return f"no article about {symbol} in the last 30 days", payload
            return f"{found['articles']} recent articles, average sentiment {found['score']:+.2f}", payload

        return self.step("sentiment", "anomaly", work)

    def anomaly_agent(self, symbol: str):
        def work():
            alert = stock_signal(self.market, symbol, sessions=5)
            signal = decision.anomaly_signal(alert)
            if alert["severity"] is None:
                return "no unusual session in the last 5", {"alert": alert, "signal": signal}
            return f"{alert['count']} unusual session(s), worst {alert['severity']}", {"alert": alert, "signal": signal}

        return self.step("anomaly", "recommendation", work)

    def recommendation_agent(self, symbol: str, market: dict | None, found: list[dict | None]):
        def work():
            profile = self.user.risk_profile if self.user else "moderate"
            held_weight, trust = None, None
            if self.user:
                trust = policy.get_state(self.db, self.user)["trust"]
                account = get_portfolio(self.db, self.user)
                stocks = self.market.stocks.set_index("ticker")["last_close"]
                values = {p.ticker: p.quantity * float(stocks.get(p.ticker, p.avg_cost)) for p in positions_of(self.db, self.user)}
                total = account.cash + sum(values.values())
                held_weight = values.get(symbol, 0.0) / total if total > 0 else 0.0
            signals = [part["signal"] for part in found if part and "signal" in part]
            result = decision.decide(
                signals,
                profile,
                listed=bool(market["listed"]) if market else True,
                traded_share=float(market["traded_share_60"]) if market else 1.0,
                held_weight=held_weight,
                trust=trust,
            )
            result["signals"] = signals
            result["held_weight_pct"] = round(held_weight * 100.0, 2) if held_weight is not None else None
            result["trust"] = trust
            for rule in result["safety_rules"]:
                if rule["triggered"]:
                    self.say("recommendation", "orchestrator", "safety", f"safety rule {rule['rule']}: {rule['effect']}", rule)
            summary = f"{result['action']} (score {result['score']:+.2f}, threshold ±{result['threshold']}, profile {profile})"
            return summary, result

        started = time.perf_counter()
        try:
            summary, payload = work()
        except Exception as exc:
            self.say("recommendation", "orchestrator", "error", f"recommendation failed: {exc}", {"error": str(exc)})
            return None
        payload["elapsed_ms"] = round((time.perf_counter() - started) * 1000.0, 1)
        self.say("recommendation", "orchestrator", "result", summary, payload)
        return payload

    # ---------------------------------------------------------------- run
    def run_for(self, ticker: str) -> AgentRun:
        symbol = self.market.resolve(ticker)
        self.run = AgentRun(
            user_id=self.user.id if self.user else None,
            ticker=symbol,
            risk_profile=self.user.risk_profile if self.user else "moderate",
            status="running",
        )
        self.db.add(self.run)
        self.db.flush()
        self.say("orchestrator", "market", "task", f"analyse {symbol} for a {self.run.risk_profile} profile", {"ticker": symbol})
        market = self.market_agent(symbol)
        forecast = self.forecast_agent(symbol)
        sentiment = self.sentiment_agent(symbol)
        anomaly = self.anomaly_agent(symbol)
        result = self.recommendation_agent(symbol, market, [market, forecast, sentiment, anomaly])
        self.run.status = "done" if result else "failed"
        self.run.result = result or {}
        self.run.finished_at = datetime.now(UTC)
        self.db.commit()
        return self.run


def iso_utc(moment: datetime | None) -> str | None:
    """SQLite gives back naive datetimes; they were written in UTC, so say so."""
    if moment is None:
        return None
    return (moment if moment.tzinfo else moment.replace(tzinfo=UTC)).isoformat()


def run_out(run: AgentRun, messages: list[AgentMessage] | None = None) -> dict:
    out = {
        "id": run.id,
        "ticker": run.ticker,
        "risk_profile": run.risk_profile,
        "status": run.status,
        "action": (run.result or {}).get("action"),
        "score": (run.result or {}).get("score"),
        "started_at": iso_utc(run.started_at),
        "finished_at": iso_utc(run.finished_at),
    }
    if messages is not None:
        out["result"] = run.result
        out["messages"] = [
            {
                "seq": m.seq,
                "sender": m.sender,
                "receiver": m.receiver,
                "kind": m.kind,
                "summary": m.summary,
                "payload": m.payload,
                "at": iso_utc(m.created_at),
            }
            for m in messages
        ]
    return out
