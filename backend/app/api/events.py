"""API endpoints for competitor events (multi-signal intelligence)."""

from __future__ import annotations

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.models import Competitor, CompetitorEvent, SignalType
from app.schemas.schemas import CompetitorEventCreate, CompetitorEventRead

router = APIRouter(tags=["events"])


@router.get(
    "/api/workspaces/{workspace_id}/events",
    response_model=List[CompetitorEventRead],
)
def list_workspace_events(
    workspace_id: uuid.UUID,
    signal_type: Optional[str] = Query(default=None),
    competitor_id: Optional[uuid.UUID] = Query(default=None),
    severity: Optional[str] = Query(default=None),
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """List competitor events for a workspace, with optional filters."""
    query = db.query(CompetitorEvent).filter(
        CompetitorEvent.workspace_id == workspace_id
    )

    if signal_type:
        query = query.filter(CompetitorEvent.signal_type == signal_type)
    if competitor_id:
        query = query.filter(CompetitorEvent.competitor_id == competitor_id)
    if severity:
        query = query.filter(CompetitorEvent.severity == severity)

    return (
        query.order_by(CompetitorEvent.event_time.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


@router.get(
    "/api/competitors/{competitor_id}/events",
    response_model=List[CompetitorEventRead],
)
def list_competitor_events(
    competitor_id: uuid.UUID,
    signal_type: Optional[str] = Query(default=None),
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """List events for a specific competitor."""
    comp = db.query(Competitor).filter(Competitor.id == competitor_id).first()
    if not comp:
        raise HTTPException(status_code=404, detail="Competitor not found")

    query = db.query(CompetitorEvent).filter(
        CompetitorEvent.competitor_id == competitor_id
    )
    if signal_type:
        query = query.filter(CompetitorEvent.signal_type == signal_type)

    return (
        query.order_by(CompetitorEvent.event_time.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


@router.get("/api/events/signal-types", response_model=List[str])
def list_signal_types():
    """List all valid signal types."""
    return [t.value for t in SignalType]


@router.get("/api/events/{event_id}", response_model=CompetitorEventRead)
def get_event(event_id: uuid.UUID, db: Session = Depends(get_db)):
    """Get a single competitor event by ID."""
    event = db.query(CompetitorEvent).filter(CompetitorEvent.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Competitor event not found")
    return event


@router.post(
    "/api/workspaces/{workspace_id}/competitors/{competitor_id}/events",
    response_model=CompetitorEventRead,
    status_code=201,
)
def create_event(
    workspace_id: uuid.UUID,
    competitor_id: uuid.UUID,
    payload: CompetitorEventCreate,
    db: Session = Depends(get_db),
):
    """Manually create a competitor event (useful for testing and manual entry)."""
    comp = db.query(Competitor).filter(
        Competitor.id == competitor_id,
        Competitor.workspace_id == workspace_id,
    ).first()
    if not comp:
        raise HTTPException(status_code=404, detail="Competitor not found in workspace")

    valid_types = {t.value for t in SignalType}
    if payload.signal_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid signal_type: {payload.signal_type}. Valid: {', '.join(sorted(valid_types))}",
        )

    event = CompetitorEvent(
        workspace_id=workspace_id,
        competitor_id=competitor_id,
        signal_type=payload.signal_type,
        title=payload.title,
        description=payload.description,
        source_url=payload.source_url,
        event_time=payload.event_time,
        metadata_json=payload.metadata_json or {},
        severity=payload.severity,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event
