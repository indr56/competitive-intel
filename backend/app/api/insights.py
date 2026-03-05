from __future__ import annotations

import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.models import ChangeEvent, Insight
from app.schemas.schemas import InsightGenerateRequest, InsightRead, InsightRegenerateRequest

router = APIRouter(tags=["insights"])


@router.get(
    "/api/change-events/{change_event_id}/insights",
    response_model=List[InsightRead],
)
def list_insights_for_event(
    change_event_id: uuid.UUID,
    insight_type: str = Query(default=None, description="Filter by insight type"),
    db: Session = Depends(get_db),
):
    event = db.query(ChangeEvent).filter(ChangeEvent.id == change_event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="ChangeEvent not found")

    q = db.query(Insight).filter(Insight.change_event_id == change_event_id)
    if insight_type:
        q = q.filter(Insight.insight_type == insight_type)
    return q.order_by(Insight.insight_type, Insight.version.desc()).all()


@router.get("/api/insights/{insight_id}", response_model=InsightRead)
def get_insight(insight_id: uuid.UUID, db: Session = Depends(get_db)):
    insight = db.query(Insight).filter(Insight.id == insight_id).first()
    if not insight:
        raise HTTPException(status_code=404, detail="Insight not found")
    return insight


@router.post(
    "/api/change-events/{change_event_id}/insights/generate",
    response_model=List[InsightRead],
    status_code=201,
)
def generate_insights_for_event(
    change_event_id: uuid.UUID,
    payload: InsightGenerateRequest = InsightGenerateRequest(),
    db: Session = Depends(get_db),
):
    event = db.query(ChangeEvent).filter(ChangeEvent.id == change_event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="ChangeEvent not found")

    from app.services.insight_generator import generate_all_insights

    insights = generate_all_insights(
        change_event_id=str(change_event_id),
        db=db,
        insight_types=payload.insight_types,
    )
    return insights


@router.post(
    "/api/insights/{insight_id}/regenerate",
    response_model=InsightRead,
    status_code=201,
)
def regenerate_insight_endpoint(
    insight_id: uuid.UUID,
    payload: InsightRegenerateRequest = InsightRegenerateRequest(),
    db: Session = Depends(get_db),
):
    existing = db.query(Insight).filter(Insight.id == insight_id).first()
    if not existing:
        raise HTTPException(status_code=404, detail="Insight not found")

    from app.services.insight_generator import regenerate_insight

    new_insight = regenerate_insight(
        insight_id=str(insight_id),
        db=db,
        reason=payload.reason,
        custom_instructions=payload.custom_instructions,
    )
    return new_insight
