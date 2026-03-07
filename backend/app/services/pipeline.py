from __future__ import annotations

import logging
from typing import Any, Dict

from sqlalchemy.orm import Session

from app.models.models import ChangeEvent, Diff, Snapshot, TrackedPage
from app.services.snapshot_service import take_snapshot
from app.services.differ import compute_diff, compute_impact_score
from app.services.classifier import classify_change, derive_signal_type

logger = logging.getLogger(__name__)


def run_pipeline_sync(tracked_page_id: str, db: Session) -> Dict[str, Any]:
    """
    Full monitoring pipeline executed synchronously (no Celery needed).

      1. Capture → snapshot
      2. If text_hash unchanged → STOP
      3. Diff previous vs new snapshot
      4. Noise filter + meaningful check → if not meaningful → STOP
      5. Classify (rules + LLM) → change_event
    """
    page = db.query(TrackedPage).filter(TrackedPage.id == tracked_page_id).first()
    if not page:
        return {"error": f"TrackedPage {tracked_page_id} not found"}

    # ── Step 1: Capture ──
    try:
        new_snapshot = take_snapshot(page, db)
    except Exception as exc:
        logger.error("Capture failed for page %s: %s", tracked_page_id, exc, exc_info=True)
        return {"error": f"Capture failed: {exc}"}

    # ── Step 2: Check text_hash against previous snapshot ──
    previous_snapshot = (
        db.query(Snapshot)
        .filter(
            Snapshot.tracked_page_id == tracked_page_id,
            Snapshot.id != new_snapshot.id,
        )
        .order_by(Snapshot.captured_at.desc())
        .first()
    )

    if previous_snapshot is None:
        logger.info("First snapshot for page %s — no diff to compute", tracked_page_id)
        return {
            "status": "first_snapshot",
            "snapshot_id": str(new_snapshot.id),
        }

    if previous_snapshot.text_hash == new_snapshot.text_hash:
        logger.info("No text change for page %s (hash=%s)", tracked_page_id, new_snapshot.text_hash)
        return {
            "status": "no_change",
            "snapshot_id": str(new_snapshot.id),
        }

    # ── Step 3: Compute diff ──
    diff_result = compute_diff(previous_snapshot.extracted_text, new_snapshot.extracted_text)

    diff_record = Diff(
        tracked_page_id=page.id,
        snapshot_before_id=previous_snapshot.id,
        snapshot_after_id=new_snapshot.id,
        raw_diff={
            "lines": diff_result.raw_diff_lines[:500],
            "additions_count": len(diff_result.additions),
            "removals_count": len(diff_result.removals),
            "changed_chars": diff_result.changed_char_count,
            "noise_score": diff_result.noise_score,
        },
        is_meaningful=diff_result.is_meaningful,
        noise_filtered=diff_result.noise_report,
    )
    db.add(diff_record)
    db.commit()
    db.refresh(diff_record)

    # ── Step 4: Meaningful check ──
    if not diff_result.is_meaningful:
        logger.info(
            "Diff not meaningful for page %s (%d chars changed)",
            tracked_page_id, diff_result.changed_char_count,
        )
        return {
            "status": "not_meaningful",
            "snapshot_id": str(new_snapshot.id),
            "diff_id": str(diff_record.id),
        }

    # ── Step 5: Classify (rules + LLM) ──
    classification = classify_change(
        diff_result=diff_result,
        page_type=page.page_type,
        before_text=previous_snapshot.extracted_text,
        after_text=new_snapshot.extracted_text,
    )

    # Compute impact_score now that we have categories + severity
    impact = compute_impact_score(
        changed_chars=diff_result.changed_char_count,
        severity=classification.severity,
        categories=classification.categories,
    )
    diff_result.impact_score = impact

    # Update diff record with impact_score
    raw = dict(diff_record.raw_diff)
    raw["impact_score"] = impact
    diff_record.raw_diff = raw
    db.commit()

    # Resolve workspace_id and competitor_id via relationship
    competitor = page.competitor
    workspace_id = competitor.workspace_id
    competitor_id = competitor.id

    change_event = ChangeEvent(
        diff_id=diff_record.id,
        workspace_id=workspace_id,
        competitor_id=competitor_id,
        categories=classification.categories,
        severity=classification.severity,
        signal_type=derive_signal_type(classification.categories),
        ai_summary=classification.ai_summary,
        ai_why_it_matters=classification.ai_why_it_matters,
        ai_next_moves=classification.ai_next_moves,
        ai_battlecard_block=classification.ai_battlecard_block,
        ai_sales_talk_track=classification.ai_sales_talk_track,
        raw_llm_response=classification.raw_llm_response,
    )
    db.add(change_event)
    db.commit()
    db.refresh(change_event)

    logger.info(
        "Pipeline complete for page %s: change_event %s "
        "(categories=%s, severity=%s, impact=%.1f, llm=%s)",
        tracked_page_id, change_event.id,
        classification.categories, classification.severity,
        impact, classification.used_llm,
    )

    # ── Step 6: Generate structured insights ──
    insight_ids = []
    try:
        from app.services.insight_generator import generate_all_insights

        insights = generate_all_insights(str(change_event.id), db)
        insight_ids = [str(i.id) for i in insights]
    except Exception as exc:
        logger.warning("Insight generation failed (non-fatal): %s", exc)

    return {
        "status": "change_detected",
        "snapshot_id": str(new_snapshot.id),
        "diff_id": str(diff_record.id),
        "change_event_id": str(change_event.id),
        "impact_score": impact,
        "noise_score": diff_result.noise_score,
        "insight_ids": insight_ids,
    }
