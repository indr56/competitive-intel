from __future__ import annotations

import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.models import Competitor, TrackedPage
from app.schemas.schemas import TrackedPageCreate, TrackedPageRead, TrackedPageUpdate

router = APIRouter(tags=["tracked_pages"])


@router.post(
    "/api/competitors/{competitor_id}/pages",
    response_model=TrackedPageRead,
    status_code=201,
)
def create_tracked_page(
    competitor_id: uuid.UUID,
    payload: TrackedPageCreate,
    db: Session = Depends(get_db),
):
    competitor = db.query(Competitor).filter(Competitor.id == competitor_id).first()
    if not competitor:
        raise HTTPException(status_code=404, detail="Competitor not found")

    existing = (
        db.query(TrackedPage)
        .filter(TrackedPage.competitor_id == competitor_id, TrackedPage.url == payload.url)
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="This URL is already tracked for this competitor")

    page = TrackedPage(
        competitor_id=competitor_id,
        url=payload.url,
        page_type=payload.page_type,
        check_interval_hours=payload.check_interval_hours,
    )
    db.add(page)
    db.commit()
    db.refresh(page)
    return page


@router.get(
    "/api/competitors/{competitor_id}/pages",
    response_model=List[TrackedPageRead],
)
def list_tracked_pages(competitor_id: uuid.UUID, db: Session = Depends(get_db)):
    return (
        db.query(TrackedPage)
        .filter(TrackedPage.competitor_id == competitor_id)
        .order_by(TrackedPage.created_at.desc())
        .all()
    )


@router.get("/api/pages/{page_id}", response_model=TrackedPageRead)
def get_tracked_page(page_id: uuid.UUID, db: Session = Depends(get_db)):
    page = db.query(TrackedPage).filter(TrackedPage.id == page_id).first()
    if not page:
        raise HTTPException(status_code=404, detail="Tracked page not found")
    return page


@router.patch("/api/pages/{page_id}", response_model=TrackedPageRead)
def update_tracked_page(
    page_id: uuid.UUID,
    payload: TrackedPageUpdate,
    db: Session = Depends(get_db),
):
    page = db.query(TrackedPage).filter(TrackedPage.id == page_id).first()
    if not page:
        raise HTTPException(status_code=404, detail="Tracked page not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(page, field, value)

    db.commit()
    db.refresh(page)
    return page


@router.delete("/api/pages/{page_id}", status_code=204)
def delete_tracked_page(page_id: uuid.UUID, db: Session = Depends(get_db)):
    page = db.query(TrackedPage).filter(TrackedPage.id == page_id).first()
    if not page:
        raise HTTPException(status_code=404, detail="Tracked page not found")
    db.delete(page)
    db.commit()


@router.post("/api/pages/{page_id}/capture-now")
def capture_now(
    page_id: uuid.UUID,
    sync: bool = Query(default=False, description="Run pipeline synchronously (no Celery)"),
    db: Session = Depends(get_db),
):
    page = db.query(TrackedPage).filter(TrackedPage.id == page_id).first()
    if not page:
        raise HTTPException(status_code=404, detail="Tracked page not found")

    if sync:
        from app.services.pipeline import run_pipeline_sync

        return run_pipeline_sync(str(page_id), db)

    from app.tasks.pipeline_tasks import run_page_pipeline

    task = run_page_pipeline.delay(str(page_id))
    return {"task_id": task.id, "status": "queued"}
