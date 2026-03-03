from __future__ import annotations

import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.models import Digest
from app.schemas.schemas import DigestRead

router = APIRouter(tags=["digests"])


@router.get("/api/workspaces/{workspace_id}/digests", response_model=List[DigestRead])
def list_digests(
    workspace_id: uuid.UUID,
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    return (
        db.query(Digest)
        .filter(Digest.workspace_id == workspace_id)
        .order_by(Digest.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


@router.get("/api/digests/{digest_id}", response_model=DigestRead)
def get_digest(digest_id: uuid.UUID, db: Session = Depends(get_db)):
    d = db.query(Digest).filter(Digest.id == digest_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Digest not found")
    return d


@router.post("/api/digests/{digest_id}/resend", status_code=202)
def resend_digest(digest_id: uuid.UUID, db: Session = Depends(get_db)):
    d = db.query(Digest).filter(Digest.id == digest_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Digest not found")

    from app.tasks.digest_tasks import send_workspace_digest

    task = send_workspace_digest.delay(str(d.workspace_id))
    return {"task_id": task.id, "status": "queued"}


@router.get("/api/digest-view/{token}")
def get_digest_web_view(token: str, db: Session = Depends(get_db)):
    """Public web view of a digest — no auth required."""
    d = db.query(Digest).filter(Digest.web_view_token == token).first()
    if not d:
        raise HTTPException(status_code=404, detail="Digest not found")

    from app.models.models import ChangeEvent, Competitor

    changes = (
        db.query(ChangeEvent)
        .filter(ChangeEvent.id.in_(d.change_event_ids))
        .order_by(ChangeEvent.created_at.desc())
        .all()
    )

    items = []
    for ce in changes:
        competitor = db.query(Competitor).filter(Competitor.id == ce.competitor_id).first()
        items.append({
            "competitor_name": competitor.name if competitor else "Unknown",
            "categories": ce.categories,
            "severity": ce.severity.value if ce.severity else "medium",
            "summary": ce.ai_summary,
            "why_it_matters": ce.ai_why_it_matters,
            "next_moves": ce.ai_next_moves,
            "battlecard_block": ce.ai_battlecard_block,
            "sales_talk_track": ce.ai_sales_talk_track,
        })

    return {
        "workspace_id": str(d.workspace_id),
        "period_start": d.period_start.isoformat(),
        "period_end": d.period_end.isoformat(),
        "changes": items,
    }
