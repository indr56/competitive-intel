from __future__ import annotations

import logging

from app.tasks.celery_app import celery_app
from app.core.database import SessionLocal

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.pipeline_tasks.run_page_pipeline")
def run_page_pipeline(tracked_page_id: str) -> dict:
    """
    Full pipeline for a single tracked page (Celery wrapper).
    Delegates to the sync pipeline service.
    """
    from app.services.pipeline import run_pipeline_sync

    db = SessionLocal()
    try:
        return run_pipeline_sync(tracked_page_id, db)
    except Exception as exc:
        logger.error("Pipeline failed for page %s: %s", tracked_page_id, exc, exc_info=True)
        return {"error": str(exc)}
    finally:
        db.close()
