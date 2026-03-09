"""
AI Impact Correlation Engine — correlates visibility events with competitor signals.

Detects when:
1. A competitor signal occurs (e.g., "Cursor launched new pricing")
2. Visibility changes happen around the same time
3. Generates AI Impact Insights with priority levels

Key design decisions:
- Uses date-only comparison (not datetime) to avoid same-day timing artifacts
- Limits insights to top N signals per competitor×prompt to reduce noise
- Differentiates "first detection" from "actual change" in scoring
- Weights signals by type and recency for varied, meaningful scores
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta, date as date_type
from typing import List, Tuple

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

# Max insights per competitor × prompt to avoid noise
MAX_INSIGHTS_PER_COMP_PROMPT = 5

# Weights by signal type (higher = more likely to cause visibility change)
SIGNAL_TYPE_WEIGHTS: dict[str, float] = {
    "pricing_change": 1.5,
    "positioning_change": 1.4,
    "funding": 1.3,
    "acquisition": 1.3,
    "product_launch": 1.2,
    "feature_release": 1.2,
    "integration_added": 1.1,
    "integration_removed": 1.1,
    "landing_page_created": 1.0,
    "hiring": 0.7,
    "blog_post": 0.6,
    "website_change": 0.5,
}


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
    signal_type: str = "",
    days_since_signal: int = 0,
) -> float:
    """
    Compute impact score (0-100) based on visibility change magnitude,
    signal type weight, and recency.
    """
    if visibility_before == 0 and visibility_after == 0:
        return 0.0

    delta = visibility_after - visibility_before

    # First detection: before=0, after>0 — this is "we found them", not a change
    is_first_detection = (visibility_before == 0 and visibility_after > 0)

    if is_first_detection:
        # Moderate score for first-time detection (20-50 range)
        base_score = min(visibility_after * 8, 30)
        engine_factor = min(engines_affected_count / 4, 1.0)
        score = base_score + engine_factor * 20
        # Signal type weight
        type_weight = SIGNAL_TYPE_WEIGHTS.get(signal_type, 0.8)
        score *= type_weight
        return round(min(score, 50.0), 1)

    # No change
    if delta == 0:
        return 0.0

    # Actual change
    base = max(visibility_before, 1)
    change_pct = abs(delta) / base * 100

    engine_factor = min(engines_affected_count / 4, 1.0)
    base_score = change_pct * 0.4 + engine_factor * 25

    # Signal type weight
    type_weight = SIGNAL_TYPE_WEIGHTS.get(signal_type, 0.8)
    base_score *= type_weight

    # Recency bonus: more recent signals score higher
    if days_since_signal <= 1:
        recency_factor = 1.2
    elif days_since_signal <= 3:
        recency_factor = 1.0
    elif days_since_signal <= 7:
        recency_factor = 0.85
    else:
        recency_factor = 0.7

    score = base_score * recency_factor
    return round(min(score, 100.0), 1)


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
    engines_str = ", ".join(engines_affected) if engines_affected else "no engines"

    is_first_detection = (visibility_before == 0 and visibility_after > 0)

    if is_first_detection:
        return (
            f"{competitor_name} was detected in {visibility_after} AI engine "
            f"{'response' if visibility_after == 1 else 'responses'} "
            f"across {engines_str}. "
            f"This was found around the time of signal: \"{signal_title}\" ({signal_type}). "
            f"Detected via prompt: \"{prompt_text}\"."
        )

    direction = "increased" if delta > 0 else "decreased"
    return (
        f"{competitor_name} visibility {direction} from {visibility_before} to "
        f"{visibility_after} mentions across {engines_str}. "
        f"This correlates with the signal: \"{signal_title}\" ({signal_type}). "
        f"Detected via prompt: \"{prompt_text}\"."
    )


def _normalize_to_date(dt: datetime) -> datetime:
    """Normalize a datetime to midnight UTC for date-only comparison."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def correlate_signals_with_visibility(
    db: Session,
    workspace_id: str,
    days: int = CORRELATION_WINDOW_DAYS,
) -> dict:
    """
    Run correlation engine for a workspace.
    Looks at recent competitor signals and checks for visibility changes.

    Key improvements over naive approach:
    - Normalizes signal timestamps to dates for fair comparison with event_date
    - Limits insights per competitor×prompt to avoid noise from many signals
    - Ranks signals by type weight and recency to pick the most relevant ones
    - Skips zero-delta correlations (no actual visibility change)
    - Clears stale insights on re-run for clean results
    """
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days * 2)

    competitors = (
        db.query(Competitor)
        .filter(Competitor.workspace_id == workspace_id, Competitor.is_active == True)
        .all()
    )

    # Clear stale insights for this workspace before re-computing
    db.query(AIImpactInsight).filter(
        AIImpactInsight.workspace_id == workspace_id,
    ).delete(synchronize_session=False)
    db.flush()

    insights_created = 0

    for comp in competitors:
        # Gather all recent signals for this competitor
        signals: List[Tuple[str, str, str, datetime]] = []  # (id, type, title, time)

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

        for tp in tracked_prompts:
            # Rank signals by relevance (type weight × recency)
            scored_signals = []
            for sig_id, sig_type, sig_title, sig_time in signals:
                type_weight = SIGNAL_TYPE_WEIGHTS.get(sig_type, 0.8)
                days_ago = max((now - sig_time).days, 0)
                recency = 1.0 / (1 + days_ago * 0.15)
                relevance = type_weight * recency
                scored_signals.append((relevance, sig_id, sig_type, sig_title, sig_time))

            # Sort by relevance descending and take top N
            scored_signals.sort(key=lambda x: x[0], reverse=True)
            top_signals = scored_signals[:MAX_INSIGHTS_PER_COMP_PROMPT]

            for relevance, signal_id, signal_type, signal_title, signal_time in top_signals:
                # Normalize signal time to date-only (midnight UTC)
                # This prevents same-day timing artifacts where event_date
                # (midnight) is compared against signal created_at (later time)
                signal_date = _normalize_to_date(signal_time)

                before_start = signal_date - timedelta(days=days)
                after_end = signal_date + timedelta(days=days)

                # Count visibility events BEFORE signal date (strictly before)
                before_count = (
                    db.query(sa_func.count(AIVisibilityEvent.id))
                    .filter(
                        AIVisibilityEvent.competitor_id == comp.id,
                        AIVisibilityEvent.tracked_prompt_id == tp.id,
                        AIVisibilityEvent.mentioned == True,
                        AIVisibilityEvent.event_date >= before_start,
                        AIVisibilityEvent.event_date < signal_date,
                    )
                    .scalar() or 0
                )

                # Count visibility events ON or AFTER signal date
                after_count = (
                    db.query(sa_func.count(AIVisibilityEvent.id))
                    .filter(
                        AIVisibilityEvent.competitor_id == comp.id,
                        AIVisibilityEvent.tracked_prompt_id == tp.id,
                        AIVisibilityEvent.mentioned == True,
                        AIVisibilityEvent.event_date >= signal_date,
                        AIVisibilityEvent.event_date <= after_end,
                    )
                    .scalar() or 0
                )

                # Skip if no visibility data at all
                if before_count == 0 and after_count == 0:
                    continue

                # Skip zero-delta unless it's a first detection
                if before_count == after_count:
                    continue

                days_since = max((now - signal_time).days, 0)

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

                impact_score = _compute_impact_score(
                    before_count, after_count, len(engines_affected),
                    signal_type, days_since,
                )
                # Skip trivially low scores
                if impact_score < 5.0:
                    continue

                priority = _compute_priority(impact_score)

                explanation = _generate_explanation(
                    comp.name, signal_title, signal_type,
                    before_count, after_count, engines_affected, tp.prompt_text,
                )

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

    db.commit()

    return {
        "insights_created": insights_created,
        "competitors_analyzed": len(competitors),
    }
