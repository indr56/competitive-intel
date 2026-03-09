"""
Visibility Trends Service — computes analytics from visibility events.

Provides:
- Mention frequency over time
- Ranking distribution per engine
- Engine-specific mention counts
- Citation URLs
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone, timedelta

from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from app.models.models import (
    AIVisibilityEvent,
    Competitor,
)

logger = logging.getLogger(__name__)


def get_visibility_trends(
    db: Session,
    workspace_id: str,
    competitor_id: str | None = None,
    days: int = 30,
    engine: str | None = None,
) -> list[dict]:
    """
    Get visibility trend data points for a workspace.
    Returns list of {date, engine, mentions, avg_rank} points.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)

    query = (
        db.query(
            sa_func.date_trunc("day", AIVisibilityEvent.event_date).label("day"),
            AIVisibilityEvent.engine,
            sa_func.count(AIVisibilityEvent.id).label("mentions"),
            sa_func.avg(AIVisibilityEvent.rank_position).label("avg_rank"),
        )
        .filter(
            AIVisibilityEvent.workspace_id == workspace_id,
            AIVisibilityEvent.mentioned == True,
            AIVisibilityEvent.event_date >= since,
        )
    )

    if competitor_id:
        query = query.filter(AIVisibilityEvent.competitor_id == competitor_id)
    if engine:
        query = query.filter(AIVisibilityEvent.engine == engine)

    query = query.group_by("day", AIVisibilityEvent.engine).order_by("day")

    rows = query.all()

    return [
        {
            "date": row.day.strftime("%Y-%m-%d") if row.day else "",
            "engine": row.engine,
            "mentions": row.mentions,
            "avg_rank": round(float(row.avg_rank), 1) if row.avg_rank else None,
        }
        for row in rows
    ]


def get_engines_breakdown(
    db: Session,
    workspace_id: str,
    competitor_id: str | None = None,
    days: int = 30,
) -> dict[str, int]:
    """Get total mention count per engine."""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    query = (
        db.query(
            AIVisibilityEvent.engine,
            sa_func.count(AIVisibilityEvent.id).label("count"),
        )
        .filter(
            AIVisibilityEvent.workspace_id == workspace_id,
            AIVisibilityEvent.mentioned == True,
            AIVisibilityEvent.event_date >= since,
        )
    )
    if competitor_id:
        query = query.filter(AIVisibilityEvent.competitor_id == competitor_id)

    query = query.group_by(AIVisibilityEvent.engine)

    return {row.engine: row.count for row in query.all()}


def get_competitor_visibility_summary(
    db: Session,
    workspace_id: str,
    days: int = 30,
) -> list[dict]:
    """Get visibility summary per competitor."""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    rows = (
        db.query(
            AIVisibilityEvent.competitor_id,
            sa_func.count(AIVisibilityEvent.id).label("total_mentions"),
            sa_func.avg(AIVisibilityEvent.rank_position).label("avg_rank"),
        )
        .filter(
            AIVisibilityEvent.workspace_id == workspace_id,
            AIVisibilityEvent.mentioned == True,
            AIVisibilityEvent.event_date >= since,
        )
        .group_by(AIVisibilityEvent.competitor_id)
        .all()
    )

    result = []
    for row in rows:
        comp = db.query(Competitor).filter(Competitor.id == row.competitor_id).first()
        result.append({
            "competitor_id": str(row.competitor_id),
            "competitor_name": comp.name if comp else "Unknown",
            "total_mentions": row.total_mentions,
            "avg_rank": round(float(row.avg_rank), 1) if row.avg_rank else None,
        })

    result.sort(key=lambda x: -x["total_mentions"])
    return result


def get_citation_urls(
    db: Session,
    workspace_id: str,
    competitor_id: str | None = None,
    days: int = 30,
    limit: int = 50,
) -> list[dict]:
    """Get citation URLs from visibility events."""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    query = (
        db.query(AIVisibilityEvent)
        .filter(
            AIVisibilityEvent.workspace_id == workspace_id,
            AIVisibilityEvent.mentioned == True,
            AIVisibilityEvent.citation_url != None,
            AIVisibilityEvent.event_date >= since,
        )
    )
    if competitor_id:
        query = query.filter(AIVisibilityEvent.competitor_id == competitor_id)

    events = query.order_by(AIVisibilityEvent.event_date.desc()).limit(limit).all()

    return [
        {
            "citation_url": ev.citation_url,
            "engine": ev.engine,
            "rank_position": ev.rank_position,
            "event_date": ev.event_date.strftime("%Y-%m-%d") if ev.event_date else "",
        }
        for ev in events
    ]
