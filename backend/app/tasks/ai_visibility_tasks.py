"""
Celery tasks for AI Visibility Intelligence.

- Daily global prompt execution
- Workspace filtering after execution
- Correlation engine runs
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.tasks.celery_app import celery_app
from app.core.database import SessionLocal
from app.models.models import AITrackedPrompt, Workspace
from app.services.ai_visibility.prompt_execution import run_prompt_globally, normalize_prompt
from app.services.ai_visibility.workspace_filtering import filter_results_for_workspace
from app.services.ai_visibility.correlation_engine import correlate_signals_with_visibility

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.ai_visibility_tasks.run_daily_global_prompts")
def run_daily_global_prompts():
    """
    Daily task: collect all unique tracked prompts across all workspaces,
    execute them ONCE globally, then filter results per workspace.
    """
    db = SessionLocal()
    try:
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        # Collect unique normalized prompts across ALL workspaces
        all_tracked = (
            db.query(AITrackedPrompt)
            .filter(AITrackedPrompt.is_active == True)
            .all()
        )

        # Deduplicate by normalized text
        unique_prompts: dict[str, str] = {}
        for tp in all_tracked:
            normalized = normalize_prompt(tp.prompt_text)
            if normalized not in unique_prompts:
                unique_prompts[normalized] = tp.prompt_text

        logger.info(f"AI Visibility: running {len(unique_prompts)} unique prompts globally")

        # Execute each unique prompt globally
        for normalized, prompt_text in unique_prompts.items():
            try:
                run_prompt_globally(db, prompt_text, today)
            except Exception as e:
                logger.error(f"Failed to run prompt '{prompt_text[:50]}': {e}")
                continue

        # Update last_run_at for all tracked prompts
        for tp in all_tracked:
            tp.last_run_at = datetime.now(timezone.utc)
        db.commit()

        # Filter results for each workspace
        workspace_ids = set(str(tp.workspace_id) for tp in all_tracked)
        for ws_id in workspace_ids:
            try:
                filter_results_for_workspace(db, ws_id, today)
            except Exception as e:
                logger.error(f"Failed to filter results for workspace {ws_id}: {e}")

        logger.info(f"AI Visibility: completed daily run for {len(workspace_ids)} workspaces")

        return {
            "unique_prompts_run": len(unique_prompts),
            "workspaces_filtered": len(workspace_ids),
        }

    except Exception as e:
        logger.error(f"Daily global prompt run failed: {e}")
        raise
    finally:
        db.close()


@celery_app.task(name="app.tasks.ai_visibility_tasks.run_correlation_for_all_workspaces")
def run_correlation_for_all_workspaces():
    """Run correlation engine for all workspaces with tracked prompts."""
    db = SessionLocal()
    try:
        workspace_ids = (
            db.query(AITrackedPrompt.workspace_id)
            .filter(AITrackedPrompt.is_active == True)
            .distinct()
            .all()
        )

        total_insights = 0
        for (ws_id,) in workspace_ids:
            try:
                result = correlate_signals_with_visibility(db, str(ws_id))
                total_insights += result.get("insights_created", 0)
            except Exception as e:
                logger.error(f"Correlation failed for workspace {ws_id}: {e}")

        logger.info(f"AI Visibility correlation: {total_insights} insights across {len(workspace_ids)} workspaces")
        return {"workspaces_processed": len(workspace_ids), "insights_created": total_insights}

    except Exception as e:
        logger.error(f"Correlation task failed: {e}")
        raise
    finally:
        db.close()
