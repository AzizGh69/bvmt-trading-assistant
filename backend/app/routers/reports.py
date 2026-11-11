"""Market reports, running the daily job, and the user's e-mail outbox."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import jobs
from ..config import get_settings
from ..db import get_db
from ..models import OutboxEmail, Report, User
from ..security import current_user
from .market import market_or_503

router = APIRouter(prefix="/api", tags=["reports"])


def report_out(report: Report, body: bool = False) -> dict:
    out = {"id": report.id, "kind": report.kind, "session": report.session_date.isoformat(), "title": report.title}
    if body:
        out["body"] = report.body
    return out


@router.get("/reports")
def list_reports(limit: int = Query(30, ge=1, le=200), db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(select(Report).order_by(Report.session_date.desc(), Report.id.desc()).limit(limit)).all()
    settings = get_settings()
    return {
        "scheduler_enabled": settings.enable_scheduler,
        "smtp_configured": bool(settings.smtp_host),
        "reports": [report_out(r) for r in rows],
    }


@router.get("/reports/{report_id}")
def get_report(report_id: int, db: Session = Depends(get_db)) -> dict:
    report = db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="report not found")
    return report_out(report, body=True)


@router.post("/reports/run")
def run_now(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """Run the daily job for the last session now (does nothing if it already ran)."""
    return jobs.run_daily(db, market_or_503())


@router.get("/outbox")
def outbox(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    """The e-mails addressed to this user, sent or kept because SMTP is not configured."""
    rows = db.scalars(
        select(OutboxEmail).where(OutboxEmail.recipient == user.email).order_by(OutboxEmail.id.desc()).limit(50)
    ).all()
    return [
        {"id": r.id, "subject": r.subject, "body": r.body, "status": r.status, "created_at": r.created_at.isoformat()}
        for r in rows
    ]
