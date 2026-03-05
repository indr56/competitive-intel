from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from app.tasks.celery_app import celery_app
from app.core.database import SessionLocal
from app.core.plan_enforcement import can_capture
from app.models.models import Competitor, TrackedPage

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.capture_tasks.check_due_pages")
def check_due_pages() -> dict:
    """
    Hourly beat task: find all active tracked pages that are due for a check
    (last_checked_at + check_interval_hours < now) and fan out capture jobs.
    """
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        pages = (
            db.query(TrackedPage)
            .filter(TrackedPage.is_active == True)  # noqa: E712
            .all()
        )

        dispatched = 0
        skipped_billing = 0
        # Cache workspace billing checks
        ws_billing_cache: dict[str, bool] = {}
        for page in pages:
            if page.last_checked_at is not None:
                last_checked = page.last_checked_at
                if last_checked.tzinfo is None:
                    last_checked = last_checked.replace(tzinfo=timezone.utc)
                next_check = last_checked + timedelta(hours=page.check_interval_hours)
                if now < next_check:
                    continue

            # Check workspace billing status
            comp = db.query(Competitor).filter(Competitor.id == page.competitor_id).first()
            if comp:
                ws_id = str(comp.workspace_id)
                if ws_id not in ws_billing_cache:
                    ws_billing_cache[ws_id] = can_capture(comp.workspace_id, db)
                if not ws_billing_cache[ws_id]:
                    skipped_billing += 1
                    continue

            from app.tasks.pipeline_tasks import run_page_pipeline
            run_page_pipeline.delay(str(page.id))
            dispatched += 1

        logger.info("check_due_pages: dispatched %d / %d pages", dispatched, len(pages))
        return {"dispatched": dispatched, "total_active": len(pages)}
    finally:
        db.close()


@celery_app.task(
    name="app.tasks.capture_tasks.capture_page_task",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
)
def capture_page_task(self, tracked_page_id: str) -> dict:
    """
    Capture a single tracked page (Celery wrapper).
    Delegates to snapshot_service.take_snapshot.
    """
    from app.services.snapshot_service import take_snapshot

    db = SessionLocal()
    try:
        page = db.query(TrackedPage).filter(TrackedPage.id == tracked_page_id).first()
        if not page:
            return {"error": f"TrackedPage {tracked_page_id} not found"}

        snapshot = take_snapshot(page, db)
        return {"snapshot_id": str(snapshot.id), "text_hash": snapshot.text_hash}
    except Exception as exc:
        logger.error("Capture failed for page %s: %s", tracked_page_id, exc)
        raise self.retry(exc=exc)
    finally:
        db.close()
