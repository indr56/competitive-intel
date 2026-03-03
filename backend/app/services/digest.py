from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.models import ChangeEvent, Competitor, Digest, Workspace
from app.services.email import build_digest_html, send_email

logger = logging.getLogger(__name__)


def build_weekly_digest(db: Session, workspace_id: str) -> Digest | None:
    """
    Build a weekly digest for a workspace:
    1. Gather all change_events from the past 7 days.
    2. Create a Digest record.
    3. Send email to workspace members.
    4. Return the Digest.
    """
    now = datetime.now(timezone.utc)
    period_start = now - timedelta(days=7)
    period_end = now

    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        logger.error("Workspace %s not found", workspace_id)
        return None

    change_events = (
        db.query(ChangeEvent)
        .filter(
            ChangeEvent.workspace_id == workspace_id,
            ChangeEvent.created_at >= period_start,
            ChangeEvent.created_at <= period_end,
        )
        .order_by(ChangeEvent.created_at.desc())
        .all()
    )

    if not change_events:
        logger.info("No change events for workspace %s in the past week", workspace_id)
        return None

    # Build change data for email
    changes_data = []
    for ce in change_events:
        competitor = db.query(Competitor).filter(Competitor.id == ce.competitor_id).first()
        changes_data.append({
            "competitor_name": competitor.name if competitor else "Unknown",
            "categories": ce.categories,
            "severity": ce.severity.value if ce.severity else "medium",
            "ai_summary": ce.ai_summary or "",
        })

    web_view_token = secrets.token_urlsafe(48)

    digest = Digest(
        workspace_id=workspace_id,
        period_start=period_start,
        period_end=period_end,
        change_event_ids=[ce.id for ce in change_events],
        web_view_token=web_view_token,
    )
    db.add(digest)
    db.commit()
    db.refresh(digest)

    # Send email
    period_label = f"{period_start.strftime('%b %d')} – {period_end.strftime('%b %d, %Y')}"
    html = build_digest_html(workspace.name, period_label, changes_data)

    # For MVP, get admin emails from the account
    from app.models.models import User

    admins = (
        db.query(User)
        .filter(User.account_id == workspace.account_id, User.role.in_(["admin", "member"]))
        .all()
    )
    recipient_emails = [u.email for u in admins]

    if recipient_emails:
        result = send_email(
            to=recipient_emails,
            subject=f"Competitive Intel Digest — {period_label}",
            html_body=html,
        )
        if result.get("id"):
            digest.email_sent_at = datetime.now(timezone.utc)
            db.commit()

    logger.info(
        "Digest built for workspace %s: %d changes, sent to %d recipients",
        workspace_id,
        len(change_events),
        len(recipient_emails),
    )
    return digest
