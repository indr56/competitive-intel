from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.models import (
    ChangeEvent,
    Competitor,
    CompetitorEvent,
    Diff,
    Digest,
    User,
    WhiteLabelConfig,
    Workspace,
)
from app.services.email import build_digest_html, build_digest_markdown, send_email

logger = logging.getLogger(__name__)

SEVERITY_WEIGHTS: Dict[str, int] = {
    "critical": 100,
    "high": 75,
    "medium": 50,
    "low": 25,
}

MAX_CHANGES_PER_DIGEST = 25
MAX_SIGNAL_EVENTS_PER_DIGEST = 15

SIGNAL_SEVERITY_WEIGHTS: Dict[str, int] = {
    "critical": 100,
    "high": 75,
    "medium": 50,
    "low": 25,
}


@dataclass
class RankedSignalEvent:
    event_id: str
    competitor_name: str
    signal_type: str
    title: str
    description: str
    severity: str
    source_url: str
    rank_score: float


@dataclass
class RankedChange:
    change_event_id: str
    competitor_name: str
    categories: List[str]
    severity: str
    impact_score: float
    noise_score: float
    rank_score: float
    ai_summary: str
    ai_why_it_matters: str
    ai_next_moves: str
    ai_battlecard_block: str
    ai_sales_talk_track: str


@dataclass
class WhiteLabelTheme:
    logo_url: Optional[str] = None
    brand_color: str = "#111827"
    sender_name: str = "Competitive Intel"
    sender_email: Optional[str] = None
    company_name: str = "Competitive Moves Intelligence"
    footer_text: str = "Powered by Competitive Moves Intelligence"


def _get_theme(db: Session, workspace_id: str) -> WhiteLabelTheme:
    """Load white-label theme for workspace, falling back to defaults."""
    wl = (
        db.query(WhiteLabelConfig)
        .filter(WhiteLabelConfig.workspace_id == workspace_id)
        .first()
    )
    if not wl:
        return WhiteLabelTheme()
    return WhiteLabelTheme(
        logo_url=wl.logo_url,
        brand_color=wl.brand_color or "#111827",
        sender_name=wl.sender_name or "Competitive Intel",
        sender_email=wl.sender_email,
        company_name=wl.company_name or "Competitive Moves Intelligence",
        footer_text=wl.footer_text or "Powered by Competitive Moves Intelligence",
    )


def _compute_rank_score(severity: str, impact_score: float) -> float:
    """Composite ranking: severity_weight * 0.4 + impact_score * 0.6"""
    sw = SEVERITY_WEIGHTS.get(severity, 50)
    return round(sw * 0.4 + impact_score * 0.6, 2)


def _aggregate_and_rank(
    db: Session,
    workspace_id: str,
    period_start: datetime,
    period_end: datetime,
) -> List[RankedChange]:
    """
    Gather change_events in the window, rank by composite score,
    cap at MAX_CHANGES_PER_DIGEST.
    """
    events = (
        db.query(ChangeEvent)
        .filter(
            ChangeEvent.workspace_id == workspace_id,
            ChangeEvent.created_at >= period_start,
            ChangeEvent.created_at <= period_end,
        )
        .all()
    )

    ranked: List[RankedChange] = []
    for ce in events:
        severity = ce.severity.value if ce.severity else "medium"

        # Get impact/noise from diff
        diff = db.query(Diff).filter(Diff.id == ce.diff_id).first()
        impact = 0.0
        noise = 0.0
        if diff and diff.raw_diff:
            impact = diff.raw_diff.get("impact_score", 0.0)
            noise = diff.raw_diff.get("noise_score", 0.0)

        # Skip noise-dominated events
        if noise > 0.8:
            continue

        competitor = db.query(Competitor).filter(Competitor.id == ce.competitor_id).first()

        ranked.append(RankedChange(
            change_event_id=str(ce.id),
            competitor_name=competitor.name if competitor else "Unknown",
            categories=ce.categories or [],
            severity=severity,
            impact_score=impact,
            noise_score=noise,
            rank_score=_compute_rank_score(severity, impact),
            ai_summary=ce.ai_summary or "",
            ai_why_it_matters=ce.ai_why_it_matters or "",
            ai_next_moves=ce.ai_next_moves or "",
            ai_battlecard_block=ce.ai_battlecard_block or "",
            ai_sales_talk_track=ce.ai_sales_talk_track or "",
        ))

    ranked.sort(key=lambda r: r.rank_score, reverse=True)
    return ranked[:MAX_CHANGES_PER_DIGEST]


def _aggregate_signal_events(
    db: Session,
    workspace_id: str,
    period_start: datetime,
    period_end: datetime,
) -> List[RankedSignalEvent]:
    """
    Gather competitor_events in the window, rank by severity weight,
    cap at MAX_SIGNAL_EVENTS_PER_DIGEST.
    """
    events = (
        db.query(CompetitorEvent)
        .filter(
            CompetitorEvent.workspace_id == workspace_id,
            CompetitorEvent.created_at >= period_start,
            CompetitorEvent.created_at <= period_end,
        )
        .all()
    )

    ranked: List[RankedSignalEvent] = []
    for ev in events:
        severity = ev.severity or "medium"
        rank_score = float(SIGNAL_SEVERITY_WEIGHTS.get(severity, 50))
        competitor = db.query(Competitor).filter(Competitor.id == ev.competitor_id).first()

        ranked.append(RankedSignalEvent(
            event_id=str(ev.id),
            competitor_name=competitor.name if competitor else "Unknown",
            signal_type=ev.signal_type,
            title=ev.title,
            description=ev.description or "",
            severity=severity,
            source_url=ev.source_url or "",
            rank_score=rank_score,
        ))

    ranked.sort(key=lambda r: r.rank_score, reverse=True)
    return ranked[:MAX_SIGNAL_EVENTS_PER_DIGEST]


def build_weekly_digest(
    db: Session,
    workspace_id: str,
    period_days: int = 7,
    send: bool = True,
) -> Digest | None:
    """
    Build a weekly digest for a workspace:
    1. Aggregate and rank change_events from the period window.
    2. Aggregate and rank competitor_events (signals) from the period window.
    3. Load white-label theme.
    4. Generate HTML + Markdown bodies.
    5. Create Digest record.
    6. Optionally send email to subscribed members.
    """
    now = datetime.now(timezone.utc)
    period_start = now - timedelta(days=period_days)
    period_end = now

    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        logger.error("Workspace %s not found", workspace_id)
        return None

    ranked = _aggregate_and_rank(db, workspace_id, period_start, period_end)
    signal_events = _aggregate_signal_events(db, workspace_id, period_start, period_end)

    if not ranked and not signal_events:
        logger.info("No events for workspace %s in the past %d days", workspace_id, period_days)
        return None

    theme = _get_theme(db, workspace_id)
    period_label = f"{period_start.strftime('%b %d')} – {period_end.strftime('%b %d, %Y')}"

    # Convert ranked changes to dicts for templates
    changes_data = []
    ranking_data = []
    for rc in ranked:
        changes_data.append({
            "competitor_name": rc.competitor_name,
            "categories": rc.categories,
            "severity": rc.severity,
            "ai_summary": rc.ai_summary,
            "ai_why_it_matters": rc.ai_why_it_matters,
            "ai_next_moves": rc.ai_next_moves,
            "rank_score": rc.rank_score,
            "impact_score": rc.impact_score,
        })
        ranking_data.append({
            "change_event_id": rc.change_event_id,
            "rank_score": rc.rank_score,
            "impact_score": rc.impact_score,
            "noise_score": rc.noise_score,
            "severity": rc.severity,
        })

    # Add signal events to changes_data for template rendering
    for se in signal_events:
        changes_data.append({
            "competitor_name": se.competitor_name,
            "categories": [se.signal_type],
            "severity": se.severity,
            "ai_summary": se.title,
            "ai_why_it_matters": se.description,
            "ai_next_moves": "",
            "rank_score": se.rank_score,
            "impact_score": se.rank_score,
            "signal_type": se.signal_type,
            "source_url": se.source_url,
        })
        ranking_data.append({
            "event_id": se.event_id,
            "rank_score": se.rank_score,
            "severity": se.severity,
            "signal_type": se.signal_type,
        })

    # Re-sort combined data by rank_score
    changes_data.sort(key=lambda x: x.get("rank_score", 0), reverse=True)

    # Generate bodies
    html = build_digest_html(workspace.name, period_label, changes_data, theme)
    markdown = build_digest_markdown(workspace.name, period_label, changes_data, theme)

    web_view_token = secrets.token_urlsafe(48)

    # Create signed report URL
    from app.core.signing import sign_digest_url

    digest = Digest(
        workspace_id=workspace_id,
        period_start=period_start,
        period_end=period_end,
        change_event_ids=[rc.change_event_id for rc in ranked],
        ranking_data=ranking_data,
        html_body=html,
        markdown_body=markdown,
        web_view_token=web_view_token,
    )
    db.add(digest)
    db.commit()
    db.refresh(digest)

    signed_url = sign_digest_url(str(digest.id))
    logger.info("Digest %s signed URL: %s", digest.id, signed_url)

    # Send email
    if send:
        _send_digest_email(db, workspace, digest, theme, period_label, html)

    logger.info(
        "Digest built for workspace %s: %d changes (top rank=%.1f)",
        workspace_id, len(ranked),
        ranked[0].rank_score if ranked else 0,
    )
    return digest


def _send_digest_email(
    db: Session,
    workspace: Workspace,
    digest: Digest,
    theme: WhiteLabelTheme,
    period_label: str,
    html: str,
) -> None:
    """Send digest email to subscribed workspace members."""
    admins = (
        db.query(User)
        .filter(
            User.account_id == workspace.account_id,
            User.role.in_(["admin", "member"]),
            User.digest_unsubscribed == False,  # noqa: E712
        )
        .all()
    )
    recipient_emails = [u.email for u in admins]

    if not recipient_emails:
        logger.info("No subscribed recipients for workspace %s", workspace.id)
        return

    sender = theme.sender_email
    subject_prefix = theme.sender_name or "Competitive Intel"

    result = send_email(
        to=recipient_emails,
        subject=f"{subject_prefix} Digest — {period_label}",
        html_body=html,
        from_override=sender,
    )
    if result.get("id") or result.get("status") == "skipped":
        digest.email_sent_at = datetime.now(timezone.utc)
        db.commit()


def cleanup_old_digests(db: Session, retention_days: int = 90) -> int:
    """Delete digests older than retention_days. Returns count deleted."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    count = db.query(Digest).filter(Digest.created_at < cutoff).delete()
    db.commit()
    logger.info("Cleaned up %d digests older than %d days", count, retention_days)
    return count
