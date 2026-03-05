from __future__ import annotations

import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.plan_enforcement import enforce_billing_active, enforce_competitor_limit
from app.models.models import Competitor, Workspace
from app.schemas.schemas import CompetitorCreate, CompetitorRead, CompetitorUpdate

router = APIRouter(tags=["competitors"])


@router.post(
    "/api/workspaces/{workspace_id}/competitors",
    response_model=CompetitorRead,
    status_code=201,
)
def create_competitor(
    workspace_id: uuid.UUID,
    payload: CompetitorCreate,
    db: Session = Depends(get_db),
):
    ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")

    # Plan enforcement
    enforce_competitor_limit(workspace_id, db)

    existing = (
        db.query(Competitor)
        .filter(Competitor.workspace_id == workspace_id, Competitor.domain == payload.domain)
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Competitor with this domain already exists in workspace")

    competitor = Competitor(
        workspace_id=workspace_id,
        name=payload.name,
        domain=payload.domain,
        logo_url=payload.logo_url,
    )
    db.add(competitor)
    db.commit()
    db.refresh(competitor)
    return competitor


@router.get(
    "/api/workspaces/{workspace_id}/competitors",
    response_model=List[CompetitorRead],
)
def list_competitors(workspace_id: uuid.UUID, db: Session = Depends(get_db)):
    return (
        db.query(Competitor)
        .filter(Competitor.workspace_id == workspace_id)
        .order_by(Competitor.created_at.desc())
        .all()
    )


@router.get("/api/competitors/{competitor_id}", response_model=CompetitorRead)
def get_competitor(competitor_id: uuid.UUID, db: Session = Depends(get_db)):
    c = db.query(Competitor).filter(Competitor.id == competitor_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Competitor not found")
    return c


@router.patch("/api/competitors/{competitor_id}", response_model=CompetitorRead)
def update_competitor(
    competitor_id: uuid.UUID,
    payload: CompetitorUpdate,
    db: Session = Depends(get_db),
):
    c = db.query(Competitor).filter(Competitor.id == competitor_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Competitor not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(c, field, value)

    db.commit()
    db.refresh(c)
    return c


@router.delete("/api/competitors/{competitor_id}", status_code=204)
def delete_competitor(competitor_id: uuid.UUID, db: Session = Depends(get_db)):
    c = db.query(Competitor).filter(Competitor.id == competitor_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Competitor not found")
    db.delete(c)
    db.commit()
