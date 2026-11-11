"""The daily job: record the session's alerts, write the market report, e-mail subscribers.

It runs once per market session and is idempotent: running it again for a
session that already has its report does nothing. ``ENABLE_SCHEDULER`` runs it
in the API process every ``SCHEDULER_INTERVAL_MINUTES``; ``POST /api/reports/run``
runs it on demand. Without ``SMTP_HOST`` every e-mail is kept in the outbox with
the status ``not_configured`` instead of being sent.
"""
from __future__ import annotations

import asyncio
import logging
import smtplib
from email.message import EmailMessage

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from .account import positions_of
from .analytics.anomalies import cached_scan, filter_alerts
from .analytics.market import MarketData
from .config import Settings, get_settings
from .db import session_factory
from .models import Alert, OutboxEmail, Report, User

log = logging.getLogger("bvmt.jobs")
SEVERITY_FR = {"low": "faible", "medium": "moyenne", "high": "élevée", "critical": "critique"}
DISCLAIMER = "Projet éducatif, calculé sur l'historique des cours : ce n'est pas un conseil en investissement."


def send_email(db: Session, recipient: str, subject: str, body: str, settings: Settings | None = None) -> OutboxEmail:
    """Send through SMTP when configured; keep a copy in the outbox either way."""
    settings = settings or get_settings()
    row = OutboxEmail(recipient=recipient, subject=subject, body=body, status="not_configured")
    if settings.smtp_host:
        message = EmailMessage()
        message["From"], message["To"], message["Subject"] = settings.smtp_from, recipient, subject
        message.set_content(body)
        try:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
                if settings.smtp_starttls:
                    smtp.starttls()
                if settings.smtp_user:
                    smtp.login(settings.smtp_user, settings.smtp_password)
                smtp.send_message(message)
            row.status = "sent"
        except (OSError, smtplib.SMTPException) as exc:
            row.status, row.error = "failed", type(exc).__name__
            log.warning("e-mail to a subscriber failed: %s", type(exc).__name__)
    db.add(row)
    return row


def session_alerts(market: MarketData) -> list[dict]:
    """Alerts of the last session, medium severity and above, corporate actions left out."""
    frame = filter_alerts(cached_scan(market), market, sessions=1, min_severity="medium")
    frame = frame[frame["kinds"].map(lambda kinds: kinds != ["corporate_action"])]
    return [
        {
            "ticker": r.ticker,
            "kinds": list(r.kinds),
            "severity": r.severity,
            "score": float(r.score),
            "change_pct": None if pd.isna(r.change_pct) else round(float(r.change_pct), 2),
            "volume_z": None if pd.isna(r.volume_z) else round(float(r.volume_z), 1),
            "message": r.message,
        }
        for r in frame.itertuples(index=False)
    ]


def _alert_line(alert: dict) -> str:
    parts = []
    if alert["change_pct"] is not None:
        parts.append(f"{alert['change_pct']:+.2f} %")
    if alert["volume_z"] is not None and "volume_spike" in alert["kinds"]:
        parts.append(f"volume à {alert['volume_z']} écarts-types")
    return f"- {alert['ticker']} (gravité {SEVERITY_FR[alert['severity']]}) : {', '.join(parts) or 'séance atypique'}"


def report_body(market: MarketData, alerts: list[dict]) -> tuple[str, str]:
    view = market.overview(top=5, index_sessions=5)
    session = view["session"]
    breadth, index = view["breadth"], view["index"]
    lines = [
        f"Séance du {session}",
        "",
        f"Indice composite (approximation du TUNINDEX) : {index['value']:.2f} ({index['change_pct']:+.2f} %).",
        f"{breadth['traded']} valeurs échangées sur {breadth['listed']} : {breadth['advancing']} en hausse, "
        f"{breadth['declining']} en baisse, {breadth['unchanged']} inchangées.",
        f"Capitaux échangés : {view['totals']['turnover']:,.0f} TND.".replace(",", " "),
        "",
        "Plus fortes hausses :",
        *[f"- {m['ticker']} {m['change_pct']:+.2f} % à {m['close']} TND" for m in view["gainers"]],
        "",
        "Plus fortes baisses :",
        *[f"- {m['ticker']} {m['change_pct']:+.2f} % à {m['close']} TND" for m in view["losers"]],
        "",
        f"Séances inhabituelles (gravité moyenne et plus) : {len(alerts)}",
        *[_alert_line(a) for a in alerts[:10]],
        "",
        DISCLAIMER,
    ]
    return f"Marché BVMT : séance du {session}", "\n".join(lines)


def run_daily(db: Session, market: MarketData, settings: Settings | None = None) -> dict:
    """Alerts, report and e-mails for the last session, once."""
    settings = settings or get_settings()
    session = market.last_session.date()
    existing = db.scalar(select(Report).where(Report.session_date == session, Report.kind == "daily_market"))
    if existing:
        return {"session": session.isoformat(), "report_id": existing.id, "already_done": True, "alerts": 0, "emails": 0}

    alerts = session_alerts(market)
    known = set(db.scalars(select(Alert.ticker).where(Alert.session_date == session)).all())
    for alert in alerts:
        if alert["ticker"] not in known:
            db.add(Alert(ticker=alert["ticker"], session_date=session, kinds=alert["kinds"], severity=alert["severity"], score=alert["score"], message=alert["message"]))
    title, body = report_body(market, alerts)
    report = Report(kind="daily_market", session_date=session, title=title, body=body)
    db.add(report)

    emails = 0
    for user in db.scalars(select(User).where(User.email_alerts.is_(True))).all():
        held = {p.ticker for p in positions_of(db, user)}
        mine = [a for a in alerts if a["ticker"] in held]
        severe = [a for a in alerts if a["severity"] in {"high", "critical"} and a["ticker"] not in held]
        intro = [f"Bonjour {user.username},", ""]
        if mine:
            intro += ["Séances inhabituelles sur des valeurs de votre portefeuille simulé :", *[_alert_line(a) for a in mine], ""]
        elif severe:
            intro += ["Rien d'inhabituel sur vos valeurs. Ailleurs sur le marché :", *[_alert_line(a) for a in severe[:5]], ""]
        else:
            intro += ["Aucune séance inhabituelle sur vos valeurs.", ""]
        subject = f"{'Alerte : ' if mine else ''}{title}"
        send_email(db, user.email, subject, "\n".join(intro + [body]), settings)
        emails += 1
    db.commit()
    log.info("daily job for %s: %d alerts, %d e-mails", session, len(alerts), emails)
    return {"session": session.isoformat(), "report_id": report.id, "already_done": False, "alerts": len(alerts), "emails": emails}


async def scheduler(get_market, settings: Settings) -> None:
    """Run the daily job now and then every interval, inside the API process."""
    while True:
        try:
            with session_factory()() as db:
                await asyncio.to_thread(run_daily, db, get_market(), settings)
        except Exception:  # the next round tries again
            log.exception("daily job failed")
        await asyncio.sleep(settings.scheduler_interval_minutes * 60)
