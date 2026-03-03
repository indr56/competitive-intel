from __future__ import annotations

import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.models import Account, Workspace
from app.schemas.schemas import WorkspaceCreate, WorkspaceRead

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


@router.post("", response_model=WorkspaceRead, status_code=201)
def create_workspace(payload: WorkspaceCreate, db: Session = Depends(get_db)):
    # MVP: auto-create a default account if none exists
    account = db.query(Account).first()
    if not account:
        account = Account(name="Default Account", slug="default")
        db.add(account)
        db.commit()
        db.refresh(account)

    workspace = Workspace(
        account_id=account.id,
        name=payload.name,
        slug=payload.slug,
    )
    db.add(workspace)
    db.commit()
    db.refresh(workspace)
    return workspace


@router.get("", response_model=List[WorkspaceRead])
def list_workspaces(db: Session = Depends(get_db)):
    return db.query(Workspace).order_by(Workspace.created_at.desc()).all()


@router.get("/{workspace_id}", response_model=WorkspaceRead)
def get_workspace(workspace_id: uuid.UUID, db: Session = Depends(get_db)):
    ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return ws


@router.patch("/{workspace_id}", response_model=WorkspaceRead)
def update_workspace(
    workspace_id: uuid.UUID,
    payload: WorkspaceCreate,
    db: Session = Depends(get_db),
):
    ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    ws.name = payload.name
    ws.slug = payload.slug
    db.commit()
    db.refresh(ws)
    return ws
