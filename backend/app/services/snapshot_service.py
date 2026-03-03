from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.models import Snapshot, TrackedPage
from app.services.capture import capture_page
from app.core.storage import upload_bytes

logger = logging.getLogger(__name__)


def take_snapshot(page: TrackedPage, db: Session) -> Snapshot:
    """
    Capture a page via Playwright, store the screenshot, and persist a
    Snapshot row.  Returns the committed Snapshot ORM object.
    """
    result = capture_page(page.url, save_html=False)

    # Upload screenshot (S3 or local fallback)
    screenshot_key = f"screenshots/{page.id}/{result.text_hash}.png"
    try:
        screenshot_url = upload_bytes(screenshot_key, result.screenshot_bytes, "image/png")
    except Exception as exc:
        logger.warning("Screenshot upload failed, continuing without: %s", exc)
        screenshot_url = None

    snapshot = Snapshot(
        tracked_page_id=page.id,
        screenshot_url=screenshot_url,
        html_archive_url=None,
        extracted_text=result.extracted_text,
        text_hash=result.text_hash,
        metadata_=result.metadata,
    )
    db.add(snapshot)

    page.last_checked_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(snapshot)

    logger.info(
        "Snapshot %s for %s (hash=%s, screenshot=%s)",
        snapshot.id, page.url, result.text_hash,
        "saved" if screenshot_url else "skipped",
    )
    return snapshot
