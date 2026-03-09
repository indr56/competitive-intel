"""
AI Impact Correlation Engine — correlates visibility events with competitor signals.

Detects when:
1. A competitor signal occurs (e.g., "Zapier launched AI workflow builder")
2. Visibility changes happen around the same time
3. Generates AI Impact Insights with priority levels
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import List

from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from app.models.models import (
    AIImpactInsight,
    AITrackedPrompt,
    AIVisibilityEvent,
    ChangeEvent,
    Competitor,
    CompetitorEvent,
    PriorityLevel,
)

logger = logging.getLogger(__name__)

# Window to look for visibility changes around a signal event
CORRELATION_WINDOW_DAYS = 7


def _compute_priority(impact_score: float) -> str:
    """Determine priority level from impact score."""
    if impact_score >= 70:
        return PriorityLevel.P0.value
    elif impact_score >= 40:
        return PriorityLevel.P1.value
    return PriorityLevel.P2.value


def _compute_impact_score(
    visibility_before: int,
    visibility_after: int,
    engines_affected_count: int,
) -> float:
    """
    Compute impact score (0-100) based on visibility change magnitude.
    """
    if visibility_before == 0 and visibility_after == 0:
        return 0.0

    # Magnitude of change
    delta = visibility_after - visibility_before
    base = max(visibility_before, 1)
    change_pct = abs(delta) / base * 100

    # Scale by engines affected (more engines = higher impact)
    engine_factor = min(engines_affected_count / 4, 1.0)  # max 4 engines

    score = min(change_pct * 0.5 + engine_factor * 30, 100.0)
    return round(score, 1)


def _generate_explanation(
    competitor_name: str,
    signal_title: str,
    signal_type: str,
    visibility_before: int,
    visibility_after: int,
    engines_affected: list[str],
    prompt_text: str,
) -> str:
    """Generate a human-readable explanation for the insight."""
    delta = visibility_after - visibility_before
    direction = "increased" if delta > 0 else "decreased" if delta < 0 else "unchanged"

    engines_str = ", ".join(engines_affected) if engines_affected else "no engines"

    return (
        f"{competitor_name} visibility {direction} from {visibility_before} to "
        f"{visibility_after} mentions across {engines_str}. "
        f"This correlates with the signal: \"{signal_title}\" ({signal_type}). "
        f"Detected via prompt: \"{prompt_text}\"."
    )


def correlate_signals_with_visibility(
    db: Session,
    workspace_id: str,
    days: int = CORRELATION_WINDOW_DAYS,
) -> dict:
    """
    Run correlation engine for a workspace.
    Looks at recent competitor signals and checks for visibility changes.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days * 2)
    mid_point = datetime.now(timezone.utc) - timedelta(days=days)

    competitors = (
        db.query(Competitor)
        .filter(Competitor.workspace_id == workspace_id, Competitor.is_active == True)
        .all()
    )

    insights_created = 0

    for comp in competitors:
        # Get recent competitor events (signals)
        signals: List[tuple[str, str, str, datetime]] = []

        # From CompetitorEvent
        comp_events = (
            db.query(CompetitorEvent)
            .filter(
                CompetitorEvent.competitor_id == comp.id,
                CompetitorEvent.created_at >= since,
            )
            .all()
        )
        for ce in comp_events:
            signals.append((str(ce.id), ce.signal_type, ce.title, ce.created_at))

        # From ChangeEvent
        change_events = (
            db.query(ChangeEvent)
            .filter(
                ChangeEvent.competitor_id == comp.id,
                ChangeEvent.created_at >= since,
            )
            .all()
        )
        for ce in change_events:
            sig_type = ce.signal_type or (ce.categories[0] if ce.categories else "website_change")
            title = ce.ai_summary or f"Change detected: {', '.join(ce.categories or [])}"
            signals.append((str(ce.id), sig_type, title[:200], ce.created_at))

        if not signals:
            continue

        # Get tracked prompts for this workspace
        tracked_prompts = (
            db.query(AITrackedPrompt)
            .filter(
                AITrackedPrompt.workspace_id == workspace_id,
                AITrackedPrompt.is_active == True,
            )
            .all()
        )

        for signal_id, signal_type, signal_title, signal_time in signals:
            # Define before/after windows around the signal
            before_start = signal_time - timedelta(days=days)
            after_end = signal_time + timedelta(days=days)

            for tp in tracked_prompts:
                # Count visibility events BEFORE signal
                before_count = (
                    db.query(sa_func.count(AIVisibilityEvent.id))
                    .filter(
                        AIVisibilityEvent.competitor_id == comp.id,
                        AIVisibilityEvent.tracked_prompt_id == tp.id,
                        AIVisibilityEvent.mentioned == True,
                        AIVisibilityEvent.event_date >= before_start,
                        AIVisibilityEvent.event_date < signal_time,
                    )
                    .scalar() or 0
                )

                # Count visibility events AFTER signal
                after_count = (
                    db.query(sa_func.count(AIVisibilityEvent.id))
                    .filter(
                        AIVisibilityEvent.competitor_id == comp.id,
                        AIVisibilityEvent.tracked_prompt_id == tp.id,
                        AIVisibilityEvent.mentioned == True,
                        AIVisibilityEvent.event_date >= signal_time,
                        AIVisibilityEvent.event_date <= after_end,
                    )
                    .scalar() or 0
                )

                # Only create insight if there's actual visibility data
                if before_count == 0 and after_count == 0:
                    continue

                # Get engines affected
                engines = (
                    db.query(AIVisibilityEvent.engine)
                    .filter(
                        AIVisibilityEvent.competitor_id == comp.id,
                        AIVisibilityEvent.tracked_prompt_id == tp.id,
                        AIVisibilityEvent.mentioned == True,
                        AIVisibilityEvent.event_date >= before_start,
                        AIVisibilityEvent.event_date <= after_end,
                    )
                    .distinct()
                    .all()
                )
                engines_affected = [e[0] for e in engines]

                # Get citations
                citation_rows = (
                    db.query(AIVisibilityEvent.citation_url)
                    .filter(
                        AIVisibilityEvent.competitor_id == comp.id,
                        AIVisibilityEvent.tracked_prompt_id == tp.id,
                        AIVisibilityEvent.citation_url != None,
                        AIVisibilityEvent.event_date >= before_start,
                        AIVisibilityEvent.event_date <= after_end,
                    )
                    .distinct()
                    .limit(10)
                    .all()
                )
                citations = [c[0] for c in citation_rows if c[0]]

                impact_score = _compute_impact_score(before_count, after_count, len(engines_affected))
                priority = _compute_priority(impact_score)

                explanation = _generate_explanation(
                    comp.name, signal_title, signal_type,
                    before_count, after_count, engines_affected, tp.prompt_text,
                )

                # Check for existing insight to avoid duplicates
                existing = (
                    db.query(AIImpactInsight)
                    .filter(
                        AIImpactInsight.workspace_id == workspace_id,
                        AIImpactInsight.competitor_id == comp.id,
                        AIImpactInsight.signal_event_id == signal_id,
                        AIImpactInsight.tracked_prompt_id == tp.id,
                    )
                    .first()
                )
                if existing:
                    # Update existing insight
                    existing.visibility_before = before_count
                    existing.visibility_after = after_count
                    existing.engines_affected = engines_affected
                    existing.citations = citations
                    existing.impact_score = impact_score
                    existing.priority_level = priority
                    existing.explanation = explanation
                    continue

                db.add(AIImpactInsight(
                    workspace_id=workspace_id,
                    competitor_id=comp.id,
                    signal_event_id=signal_id,
                    signal_type=signal_type,
                    signal_title=signal_title[:500],
                    prompt_text=tp.prompt_text,
                    tracked_prompt_id=tp.id,
                    visibility_before=before_count,
                    visibility_after=after_count,
                    engines_affected=engines_affected,
                    citations=citations,
                    impact_score=impact_score,
                    priority_level=priority,
                    explanation=explanation,
                ))
                insights_created += 1

    if insights_created:
        db.commit()

    return {
        "insights_created": insights_created,
        "competitors_analyzed": len(competitors),
    }
