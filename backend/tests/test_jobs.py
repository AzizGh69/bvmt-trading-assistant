"""The daily job: alerts, the market report and e-mails (SMTP mocked)."""
from __future__ import annotations

import smtplib

from app import jobs
from app.analytics import anomalies
from app.analytics.market import MarketData
from app.config import Settings
from app.db import session_factory
from app.models import OutboxEmail


def spiked(prices) -> MarketData:
    """The synthetic history with a huge volume and a 9% jump on ALPHA's last session."""
    frame = prices.copy()
    last = frame["date"].max()
    row = (frame["ticker"] == "ALPHA") & (frame["date"] == last)
    previous = frame.loc[(frame["ticker"] == "ALPHA") & (frame["date"] < last), "close"].iloc[-1]
    frame.loc[row, "volume"] = frame.loc[row, "volume"] * 40
    frame.loc[row, "close"] = round(previous * 1.09, 3)
    frame.loc[row, "high"] = frame.loc[row, "close"]
    anomalies._cache.clear()
    return MarketData(frame)


def account(client, email, alerts=True, buy=None):
    token = client.post("/api/auth/register", json={"email": email, "username": email[:4], "password": "long enough"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    client.put("/api/auth/profile", headers=headers, json={"email_alerts": alerts})
    if buy:
        client.post("/api/portfolio/orders", headers=headers, json={"ticker": buy, "side": "BUY", "quantity": 5})
    return headers


def test_daily_job_reports_alerts_and_emails_once(client, prices):
    holder = account(client, "holder@example.com", buy="ALPHA")
    account(client, "watcher@example.com", buy="BETA")
    account(client, "quiet@example.com", alerts=False)
    market = spiked(prices)
    with session_factory()() as db:
        done = jobs.run_daily(db, market)
        assert done["alerts"] >= 1 and done["emails"] == 2 and not done["already_done"]
        assert jobs.run_daily(db, market)["already_done"]  # once per session
        mails = {m.recipient: m for m in db.query(OutboxEmail).all()}
    assert set(mails) == {"holder@example.com", "watcher@example.com"}
    assert mails["holder@example.com"].subject.startswith("Alerte") and "ALPHA" in mails["holder@example.com"].body
    assert all(m.status == "not_configured" for m in mails.values())  # no SMTP: kept in the outbox

    listed = client.get("/api/reports").json()
    assert listed["reports"][0]["id"] == done["report_id"] and listed["smtp_configured"] is False
    body = client.get(f"/api/reports/{done['report_id']}").json()["body"]
    assert "ALPHA" in body and "pas un conseil" in body
    inbox = client.get("/api/outbox", headers=holder).json()
    assert len(inbox) == 1 and inbox[0]["status"] == "not_configured"
    assert client.get("/api/outbox").status_code == 401
    assert client.post("/api/reports/run", headers=holder).json()["already_done"] is True  # same session, already reported
    anomalies._cache.clear()


def test_smtp_is_used_when_configured(client, monkeypatch):
    sent = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            self.host = host

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def starttls(self):
            pass

        def login(self, user, password):
            pass

        def send_message(self, message):
            if message["To"] == "down@example.com":
                raise smtplib.SMTPServerDisconnected("gone")
            sent.append(message["To"])

    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    settings = Settings(smtp_host="smtp.example.test", smtp_user="u", smtp_password="p")
    with session_factory()() as db:
        ok = jobs.send_email(db, "up@example.com", "Sujet", "Corps", settings)
        failed = jobs.send_email(db, "down@example.com", "Sujet", "Corps", settings)
        db.commit()
        assert ok.status == "sent" and sent == ["up@example.com"]
        assert failed.status == "failed" and failed.error == "SMTPServerDisconnected"
