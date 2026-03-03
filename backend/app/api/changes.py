from __future__ import annotations

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.models import ChangeEvent, TrackedPage
from app.schemas.schemas import ChangeEventRead

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
