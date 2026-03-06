from __future__ import annotations

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.models import ChangeEvent, Competitor, CompetitorEvent, TrackedPage
from app.schemas.schemas import ActivityFeedItem, ChangeEventRead

router = APIRouter(tags=["changes"])


@router.get("/api/pages/{page_id}/changes", response_model=List[ChangeEventRead])
def list_page_changes(
    page_id: uuid.UUID,
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    page = db.query(TrackedPage).filter(TrackedPage.id == page_id).first()
    if not page:
        raise HTTPException(status_code=404, detail="Tracked page not found")

    return (
        db.query(ChangeEvent)
        .join(ChangeEvent.diff)
        .filter(ChangeEvent.diff.has(tracked_page_id=page_id))
        .order_by(ChangeEvent.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


@router.get("/api/changes", response_model=List[ChangeEventRead])
def list_changes(
    workspace_id: Optional[uuid.UUID] = Query(default=None),
    category: Optional[str] = Query(default=None),
    severity: Optional[str] = Query(default=None),
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    query = db.query(ChangeEvent)

    if workspace_id:
        query = query.filter(ChangeEvent.workspace_id == workspace_id)
    if severity:
        query = query.filter(ChangeEvent.severity == severity)
    if category:
        query = query.filter(ChangeEvent.categories.contains([category]))

    return query.order_by(ChangeEvent.created_at.desc()).offset(offset).limit(limit).all()


@router.get("/api/changes/{change_id}", response_model=ChangeEventRead)
def get_change(change_id: uuid.UUID, db: Session = Depends(get_db)):
    ce = db.query(ChangeEvent).filter(ChangeEvent.id == change_id).first()
    if not ce:
        raise HTTPException(status_code=404, detail="Change event not found")
    return ce


@router.get("/api/workspaces/{workspace_id}/activity", response_model=List[ActivityFeedItem])
def get_activity_feed(
    workspace_id: uuid.UUID,
    signal_type: Optional[str] = Query(default=None),
    limit: int = Query(default=30, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """
    Unified activity feed merging ChangeEvents and CompetitorEvents,
    sorted by event_time descending.
    """
    # Build competitor name cache
    competitors = db.query(Competitor).filter(Competitor.workspace_id == workspace_id).all()
    comp_names = {str(c.id): c.name for c in competitors}

    items: List[ActivityFeedItem] = []

    # Fetch ChangeEvents (website changes)
    if signal_type is None or signal_type in ("website_change", "pricing_change", "product_change", "marketing"):
        ce_query = db.query(ChangeEvent).filter(ChangeEvent.workspace_id == workspace_id)
        change_events = ce_query.order_by(ChangeEvent.created_at.desc()).limit(limit).all()

        for ce in change_events:
            # Map categories to signal_type
            cats = ce.categories or []
            if "pricing_change" in cats:
                st = "pricing_change"
            elif "positioning_hero" in cats or "cta_change" in cats:
                st = "marketing"
            elif "feature_claim" in cats:
                st = "product_change"
            else:
                st = "website_change"

            if signal_type and st != signal_type:
                continue

            items.append(ActivityFeedItem(
                id=str(ce.id),
                source="change_event",
                workspace_id=str(ce.workspace_id),
                competitor_id=str(ce.competitor_id),
                competitor_name=comp_names.get(str(ce.competitor_id)),
                signal_type=st,
                title=ce.ai_summary or f"Website change: {', '.join(cats)}",
                description=ce.ai_why_it_matters,
                severity=ce.severity.value if ce.severity else "medium",
                source_url=None,
                event_time=ce.created_at,
                created_at=ce.created_at,
            ))

    # Fetch CompetitorEvents
    ce2_query = db.query(CompetitorEvent).filter(CompetitorEvent.workspace_id == workspace_id)
    if signal_type:
        ce2_query = ce2_query.filter(CompetitorEvent.signal_type == signal_type)
    comp_events = ce2_query.order_by(CompetitorEvent.event_time.desc()).limit(limit).all()

    for ev in comp_events:
        items.append(ActivityFeedItem(
            id=str(ev.id),
            source="competitor_event",
            workspace_id=str(ev.workspace_id),
            competitor_id=str(ev.competitor_id),
            competitor_name=comp_names.get(str(ev.competitor_id)),
            signal_type=ev.signal_type,
            title=ev.title,
            description=ev.description,
            severity=ev.severity,
            source_url=ev.source_url,
            event_time=ev.event_time,
            created_at=ev.created_at,
        ))

    # Sort merged feed by event_time descending
    items.sort(key=lambda x: x.event_time, reverse=True)
    return items[offset:offset + limit]
