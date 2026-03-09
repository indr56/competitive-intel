"""
Workspace Filtering Service — filters global prompt results for each workspace.

After global prompt execution, this service:
1. Looks at each workspace's competitors
2. Checks if any competitor brand is mentioned in engine results
3. Creates AIVisibilityEvent records for matches
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.models import (
    AIEngineResult,
    AIPromptRun,
    AITrackedPrompt,
    AIVisibilityEvent,
    Competitor,
    RunStatusEnum,
)
from app.services.ai_visibility.prompt_execution import normalize_prompt

logger = logging.getLogger(__name__)


def _brand_matches(competitor_name: str, mentioned_brands: list[str]) -> tuple[bool, int | None]:
    """
    Check if a competitor name matches any mentioned brand.
    Returns (matched, rank_position).
    """
    comp_lower = competitor_name.lower().strip()
    for i, brand in enumerate(mentioned_brands):
        brand_lower = brand.lower().strip()
        # Exact match or substring match
        if comp_lower == brand_lower or comp_lower in brand_lower or brand_lower in comp_lower:
            return True, i + 1
    return False, None


def _brand_in_raw_response(competitor_name: str, raw_response: str | None) -> tuple[bool, int | None]:
    """
    Fallback: search raw_response text for competitor name mentions.
    Returns (matched, rank_position or None).
    """
    if not raw_response or not competitor_name:
        return False, None

    comp_lower = competitor_name.lower().strip()
    if len(comp_lower) < 2:  # Skip very short names to avoid false positives
        return False, None

    resp_lower = raw_response.lower()
    if comp_lower not in resp_lower:
        return False, None

    # Try to determine rank position from numbered list
    for line in raw_response.split('\n'):
        line_stripped = line.strip()
        m = re.match(r'^(\d+)[.)\s]', line_stripped)
        if m and comp_lower in line_stripped.lower():
            return True, int(m.group(1))

    # Found in text but no rank position
    return True, None


def _normalize_domain(domain: str) -> str:
    """Strip protocol and trailing slashes from a domain for comparison."""
    d = domain.lower().strip()
    for prefix in ("https://", "http://"):
        if d.startswith(prefix):
            d = d[len(prefix):]
    d = d.rstrip("/")
    # Also strip www.
    if d.startswith("www."):
        d = d[4:]
    return d


def filter_results_for_workspace(
    db: Session,
    workspace_id: str,
    run_date: datetime | None = None,
) -> dict:
    """
    Filter global prompt results for a specific workspace.
    Creates AIVisibilityEvent records for each competitor mention found.
    """
    if run_date is None:
        run_date = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    # Get workspace's competitors
    competitors = (
        db.query(Competitor)
        .filter(Competitor.workspace_id == workspace_id, Competitor.is_active == True)
        .all()
    )
    if not competitors:
        return {"events_created": 0, "message": "No active competitors"}

    # Get workspace's tracked prompts
    tracked_prompts = (
        db.query(AITrackedPrompt)
        .filter(
            AITrackedPrompt.workspace_id == workspace_id,
            AITrackedPrompt.is_active == True,
        )
        .all()
    )
    if not tracked_prompts:
        return {"events_created": 0, "message": "No tracked prompts"}

    events_created = 0

    for tp in tracked_prompts:
        normalized = normalize_prompt(tp.prompt_text)

        # Find global prompt run for today
        prompt_run = (
            db.query(AIPromptRun)
            .filter(
                AIPromptRun.normalized_text == normalized,
                AIPromptRun.run_date == run_date,
                AIPromptRun.status == RunStatusEnum.COMPLETED.value,
            )
            .first()
        )
        if not prompt_run:
            continue

        # Check each engine result
        engine_results = (
            db.query(AIEngineResult)
            .filter(
                AIEngineResult.prompt_run_id == prompt_run.id,
                AIEngineResult.status == RunStatusEnum.COMPLETED.value,
            )
            .all()
        )

        for er in engine_results:
            for comp in competitors:
                # Primary: check parsed mentioned_brands list
                matched, rank_pos = _brand_matches(comp.name, er.mentioned_brands or [])
                # Fallback: search raw_response text
                if not matched:
                    matched, rank_pos = _brand_in_raw_response(comp.name, er.raw_response)
                if not matched:
                    continue

                # Check for existing visibility event to avoid duplicates
                existing = (
                    db.query(AIVisibilityEvent)
                    .filter(
                        AIVisibilityEvent.workspace_id == workspace_id,
                        AIVisibilityEvent.competitor_id == comp.id,
                        AIVisibilityEvent.tracked_prompt_id == tp.id,
                        AIVisibilityEvent.engine_result_id == er.id,
                    )
                    .first()
                )
                if existing:
                    continue

                # Find citation URL if available (normalize domains)
                citation_url = None
                if er.citations and comp.domain:
                    comp_domain_norm = _normalize_domain(comp.domain)
                    for c in er.citations:
                        c_norm = _normalize_domain(c)
                        if comp_domain_norm and (
                            comp_domain_norm in c_norm or c_norm in comp_domain_norm
                        ):
                            citation_url = c
                            break

                db.add(AIVisibilityEvent(
                    workspace_id=workspace_id,
                    competitor_id=comp.id,
                    tracked_prompt_id=tp.id,
                    engine_result_id=er.id,
                    engine=er.engine,
                    mentioned=True,
                    rank_position=rank_pos,
                    citation_url=citation_url,
                    event_date=run_date,
                ))
                events_created += 1

    if events_created:
        db.commit()

    return {
        "events_created": events_created,
        "competitors_checked": len(competitors),
        "prompts_checked": len(tracked_prompts),
    }
