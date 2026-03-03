from __future__ import annotations

import logging

from app.tasks.celery_app import celery_app
from app.core.database import SessionLocal
from app.models.models import Workspace
from app.services.digest import build_weekly_digest

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.digest_tasks.send_all_weekly_digests")
def send_all_weekly_digests() -> dict:
    """
    Weekly beat task: iterate all workspaces and build + send digests.
    """
    db = SessionLocal()
    try:
        workspaces = db.query(Workspace).all()
        sent = 0
        skipped = 0

        for ws in workspaces:
            digest = build_weekly_digest(db, str(ws.id))
            if digest:
                sent += 1
            else:
                skipped += 1

        logger.info("Weekly digests: %d sent, %d skipped (no changes)", sent, skipped)
        return {"sent": sent, "skipped": skipped}
    finally:
        db.close()


@celery_app.task(name="app.tasks.digest_tasks.send_workspace_digest")
def send_workspace_digest(workspace_id: str) -> dict:
    """Send a digest for a single workspace (manual trigger / resend)."""
    db = SessionLocal()
    try:
        digest = build_weekly_digest(db, workspace_id)
        if digest:
            return {"digest_id": str(digest.id), "status": "sent"}
        return {"status": "no_changes"}
    finally:
        db.close()
