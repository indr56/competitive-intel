from __future__ import annotations

import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.models import Snapshot, TrackedPage
from app.schemas.schemas import SnapshotRead

router = APIRouter(tags=["snapshots"])


@router.get("/api/pages/{page_id}/snapshots", response_model=List[SnapshotRead])
def list_snapshots(
    page_id: uuid.UUID,
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    page = db.query(TrackedPage).filter(TrackedPage.id == page_id).first()
    if not page:
        raise HTTPException(status_code=404, detail="Tracked page not found")

    return (
        db.query(Snapshot)
        .filter(Snapshot.tracked_page_id == page_id)
        .order_by(Snapshot.captured_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


@router.get("/api/pages/{page_id}/snapshots/latest", response_model=SnapshotRead)
def get_latest_snapshot(page_id: uuid.UUID, db: Session = Depends(get_db)):
    snapshot = (
        db.query(Snapshot)
        .filter(Snapshot.tracked_page_id == page_id)
        .order_by(Snapshot.captured_at.desc())
        .first()
    )
    if not snapshot:
        raise HTTPException(status_code=404, detail="No snapshots found for this page")
    return snapshot


@router.get("/api/snapshots/{snapshot_id}", response_model=SnapshotRead)
def get_snapshot(snapshot_id: uuid.UUID, db: Session = Depends(get_db)):
    snapshot = db.query(Snapshot).filter(Snapshot.id == snapshot_id).first()
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return snapshot
