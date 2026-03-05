"""Celery tasks for multi-signal collectors."""

from __future__ import annotations

import logging

from app.tasks.celery_app import celery_app
from app.core.database import SessionLocal
from app.core.plan_enforcement import can_capture
from app.models.models import Workspace

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.signal_tasks.run_blog_collector")
def run_blog_collector() -> dict:
    """Beat task: run blog collector for all workspaces."""
    return _run_collector_for_all("blog")


@celery_app.task(name="app.tasks.signal_tasks.run_hiring_collector")
def run_hiring_collector() -> dict:
    """Beat task: run hiring collector for all workspaces."""
    return _run_collector_for_all("hiring")


@celery_app.task(name="app.tasks.signal_tasks.run_funding_collector")
def run_funding_collector() -> dict:
    """Beat task: run funding collector for all workspaces."""
    return _run_collector_for_all("funding")


@celery_app.task(name="app.tasks.signal_tasks.run_review_collector")
def run_review_collector() -> dict:
    """Beat task: run review collector for all workspaces."""
    return _run_collector_for_all("review")


@celery_app.task(name="app.tasks.signal_tasks.run_all_collectors")
def run_all_collectors() -> dict:
    """Run all collectors for all workspaces."""
    results = {}
    for collector_name in ("blog", "hiring", "funding", "review"):
        results[collector_name] = _run_collector_for_all(collector_name)
    return results


@celery_app.task(name="app.tasks.signal_tasks.run_collector_for_workspace")
def run_collector_for_workspace(workspace_id: str, collector_name: str) -> dict:
    """Run a specific collector for a single workspace."""
    db = SessionLocal()
    try:
        collector = _get_collector(collector_name, db)
        if not collector:
            return {"error": f"Unknown collector: {collector_name}"}
        return collector.run_for_workspace(workspace_id)
    finally:
        db.close()


def _run_collector_for_all(collector_name: str) -> dict:
    """Run a collector across all active workspaces with billing checks."""
    db = SessionLocal()
    try:
        workspaces = db.query(Workspace).all()
        total = {
            "collector": collector_name,
            "workspaces_processed": 0,
            "workspaces_skipped_billing": 0,
            "events_found": 0,
            "events_created": 0,
            "errors": [],
        }

        for ws in workspaces:
            if not can_capture(ws.id, db):
                total["workspaces_skipped_billing"] += 1
                continue

            collector = _get_collector(collector_name, db)
            if not collector:
                total["errors"].append(f"Unknown collector: {collector_name}")
                break

            result = collector.run_for_workspace(str(ws.id))
            total["workspaces_processed"] += 1
            total["events_found"] += result.get("events_found", 0)
            total["events_created"] += result.get("events_created", 0)
            total["errors"].extend(result.get("errors", []))

        logger.info(
            "%s collector: %d workspaces, %d events found, %d created",
            collector_name, total["workspaces_processed"],
            total["events_found"], total["events_created"],
        )
        return total
    finally:
        db.close()


def _get_collector(name: str, db):
    """Factory: get collector instance by name."""
    from app.services.collectors.blog_collector import BlogCollector
    from app.services.collectors.hiring_collector import HiringCollector
    from app.services.collectors.funding_collector import FundingCollector
    from app.services.collectors.review_collector import ReviewCollector

    collectors = {
        "blog": BlogCollector,
        "hiring": HiringCollector,
        "funding": FundingCollector,
        "review": ReviewCollector,
    }
    cls = collectors.get(name)
    if cls:
        return cls(db)
    return None
