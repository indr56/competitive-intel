from __future__ import annotations

import uuid
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.signing import sign_digest_url, verify_signature
from app.models.models import (
    ChangeEvent,
    Competitor,
    Digest,
    User,
    WhiteLabelConfig,
)
from app.schemas.schemas import DigestRead, WhiteLabelConfigRead, WhiteLabelConfigUpsert

router = APIRouter(tags=["digests"])


# ── Digest CRUD ──


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


@router.get("/api/digests/{digest_id}/signed-url")
def get_signed_url(digest_id: uuid.UUID, db: Session = Depends(get_db)):
    """Generate a signed URL for sharing a digest report."""
    d = db.query(Digest).filter(Digest.id == digest_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Digest not found")

    url = sign_digest_url(str(digest_id))
    return {"signed_url": url, "digest_id": str(digest_id)}


# ── Public report view (signed URL) ──


@router.get("/api/report/{digest_id}")
def get_report_signed(
    digest_id: uuid.UUID,
    sig: str = Query(...),
    exp: int = Query(...),
    db: Session = Depends(get_db),
):
    """Public report view accessed via signed URL with expiry."""
    if not verify_signature(str(digest_id), sig, exp):
        raise HTTPException(status_code=403, detail="Invalid or expired signature")

    d = db.query(Digest).filter(Digest.id == digest_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Digest not found")

    if d.html_body:
        return HTMLResponse(content=d.html_body)

    return _build_digest_view_json(d, db)


# ── Public web view (bearer token) ──


@router.get("/api/digest-view/{token}")
def get_digest_web_view(token: str, db: Session = Depends(get_db)):
    """Public web view of a digest — no auth required, accessed via token."""
    d = db.query(Digest).filter(Digest.web_view_token == token).first()
    if not d:
        raise HTTPException(status_code=404, detail="Digest not found")

    if d.html_body:
        return HTMLResponse(content=d.html_body)

    return _build_digest_view_json(d, db)


# ── Manual digest trigger (sync) ──


@router.post("/api/workspaces/{workspace_id}/digests/generate", status_code=201)
def generate_digest_sync(
    workspace_id: uuid.UUID,
    period_days: int = Query(default=7, ge=1, le=90),
    db: Session = Depends(get_db),
):
    """Manually trigger digest generation for a workspace (sync)."""
    from app.services.digest import build_weekly_digest

    digest = build_weekly_digest(db, str(workspace_id), period_days=period_days, send=False)
    if not digest:
        return {"status": "no_changes", "workspace_id": str(workspace_id)}

    return {
        "status": "generated",
        "digest_id": str(digest.id),
        "change_count": len(digest.change_event_ids),
        "web_view_token": digest.web_view_token,
        "signed_url": sign_digest_url(str(digest.id)),
    }


# ── Unsubscribe ──


@router.get("/api/unsubscribe")
def unsubscribe(
    user_id: str = Query(...),
    token: str = Query(...),
    db: Session = Depends(get_db),
):
    """Process unsubscribe request via signed token."""
    from app.core.signing import verify_unsubscribe_token

    if not verify_unsubscribe_token(user_id, token):
        raise HTTPException(status_code=403, detail="Invalid unsubscribe token")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.digest_unsubscribed = True
    db.commit()
    return {"status": "unsubscribed", "email": user.email}


# ── White-label config ──


@router.get(
    "/api/workspaces/{workspace_id}/white-label",
    response_model=WhiteLabelConfigRead,
)
def get_white_label(workspace_id: uuid.UUID, db: Session = Depends(get_db)):
    wl = db.query(WhiteLabelConfig).filter(
        WhiteLabelConfig.workspace_id == workspace_id
    ).first()
    if not wl:
        raise HTTPException(status_code=404, detail="White-label config not found")
    return wl


@router.put(
    "/api/workspaces/{workspace_id}/white-label",
    response_model=WhiteLabelConfigRead,
)
def upsert_white_label(
    workspace_id: uuid.UUID,
    payload: WhiteLabelConfigUpsert,
    db: Session = Depends(get_db),
):
    wl = db.query(WhiteLabelConfig).filter(
        WhiteLabelConfig.workspace_id == workspace_id
    ).first()

    if wl:
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(wl, field, value)
    else:
        wl = WhiteLabelConfig(workspace_id=workspace_id, **payload.model_dump())
        db.add(wl)

    db.commit()
    db.refresh(wl)
    return wl


# ── Helper ──


def _build_digest_view_json(d: Digest, db: Session) -> Dict[str, Any]:
    """Fallback: build JSON view from change events."""
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
        "ranking_data": d.ranking_data,
    }
