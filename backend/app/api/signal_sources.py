"""API routes for Signal Sources: CRUD, test, scan."""

from __future__ import annotations

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.models import Competitor, SignalSource, SignalType
from app.schemas.schemas import (
    SignalSourceCreate,
    SignalSourceRead,
    SignalSourceUpdate,
    TestSourceResult,
    ScanResult,
)

router = APIRouter()

VALID_SIGNAL_TYPES = {t.value for t in SignalType} - {"website_change", "pricing_change", "product_change"}


# ── Signal Sources CRUD ──


@router.post(
    "/api/competitors/{competitor_id}/sources",
    response_model=SignalSourceRead,
    status_code=201,
)
def create_signal_source(
    competitor_id: uuid.UUID,
    payload: SignalSourceCreate,
    db: Session = Depends(get_db),
):
    """Create a new signal source for a competitor."""
    comp = db.query(Competitor).filter(Competitor.id == competitor_id).first()
    if not comp:
        raise HTTPException(status_code=404, detail="Competitor not found")

    if payload.signal_type not in VALID_SIGNAL_TYPES:
        valid = sorted(VALID_SIGNAL_TYPES)
        raise HTTPException(
            status_code=400,
            detail=f"Invalid signal_type: {payload.signal_type}. Valid: {', '.join(valid)}",
        )

    source = SignalSource(
        workspace_id=comp.workspace_id,
        competitor_id=comp.id,
        signal_type=payload.signal_type,
        source_url=payload.source_url,
        source_label=payload.source_label,
        is_active=payload.is_active,
        poll_interval_hours=payload.poll_interval_hours,
        source_kind=payload.source_kind,
        metadata_json=payload.metadata_json or {},
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


@router.get(
    "/api/competitors/{competitor_id}/sources",
    response_model=List[SignalSourceRead],
)
def list_signal_sources(
    competitor_id: uuid.UUID,
    signal_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """List signal sources for a competitor."""
    query = db.query(SignalSource).filter(SignalSource.competitor_id == competitor_id)
    if signal_type:
        query = query.filter(SignalSource.signal_type == signal_type)
    return query.order_by(SignalSource.created_at.desc()).all()


@router.get(
    "/api/sources/{source_id}",
    response_model=SignalSourceRead,
)
def get_signal_source(
    source_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """Get a single signal source."""
    source = db.query(SignalSource).filter(SignalSource.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Signal source not found")
    return source


@router.patch(
    "/api/sources/{source_id}",
    response_model=SignalSourceRead,
)
def update_signal_source(
    source_id: uuid.UUID,
    payload: SignalSourceUpdate,
    db: Session = Depends(get_db),
):
    """Update a signal source."""
    source = db.query(SignalSource).filter(SignalSource.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Signal source not found")

    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(source, key, value)
    db.commit()
    db.refresh(source)
    return source


@router.delete(
    "/api/sources/{source_id}",
    status_code=204,
)
def delete_signal_source(
    source_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """Delete a signal source."""
    source = db.query(SignalSource).filter(SignalSource.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Signal source not found")
    db.delete(source)
    db.commit()


# ── Test Source ──


@router.post(
    "/api/sources/{source_id}/test",
    response_model=TestSourceResult,
)
def test_signal_source(
    source_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """Test an existing signal source for reachability and content validity."""
    source = db.query(SignalSource).filter(SignalSource.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Signal source not found")

    from app.services.scan_service import test_source
    return test_source(source.signal_type, source.source_url)


@router.post(
    "/api/sources/test-url",
    response_model=TestSourceResult,
)
def test_source_url(
    signal_type: str = Query(...),
    source_url: str = Query(...),
):
    """Test a URL without creating a source first."""
    if signal_type not in VALID_SIGNAL_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid signal_type: {signal_type}")

    from app.services.scan_service import test_source
    return test_source(signal_type, source_url)


# ── Scan Signals ──


@router.post(
    "/api/competitors/{competitor_id}/scan",
    response_model=ScanResult,
)
def scan_competitor_signals(
    competitor_id: uuid.UUID,
    signal_types: Optional[List[str]] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Scan all active signal sources for a competitor.
    Optionally filter by signal_types query param.
    """
    comp = db.query(Competitor).filter(Competitor.id == competitor_id).first()
    if not comp:
        raise HTTPException(status_code=404, detail="Competitor not found")

    from app.services.scan_service import scan_competitor
    return scan_competitor(db, comp, signal_types=signal_types)
