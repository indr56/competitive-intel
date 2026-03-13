"""
AI Impact Correlation Engine — correlates visibility events with competitor signals.

PROMPT-9 upgrade: now produces four insight types:
  1. ai_impact          — signal → visibility change correlation
  2. ai_visibility_hijack — new competitor enters AI responses
  3. ai_visibility_loss   — competitor disappears from AI responses
  4. ai_dominance         — competitor appears across ALL engines

PROMPT-10 upgrade:
  - signal_headline      — concise 1-line signal description for compact card
  - summary_text         — one-liner insight summary (replaces paragraph in compact card)
  - confidence_factors   — explainable breakdown of confidence score
  - prompt_relevance_score — semantic signal↔prompt relevance (0-1)
  - Relevance filtering  — skips signal-prompt pairs below threshold to prevent false correlations

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
    AIEngineResult,
    AIImpactInsight,
    AIPromptCluster,
    AIPromptRun,
    AITrackedPrompt,
    AIVisibilityEvent,
    ChangeEvent,
    Competitor,
    CompetitorEvent,
    InsightType,
    PriorityLevel,
    RunStatusEnum,
)
from app.services.ai_visibility.prompt_signal_relevance import (
    compute_prompt_signal_relevance,
    PROMPT_SIGNAL_RELEVANCE_THRESHOLD,
)

logger = logging.getLogger(__name__)

# Window to look for visibility changes around a signal event
CORRELATION_WINDOW_DAYS = 7

# Max insights per competitor × prompt to avoid noise
MAX_INSIGHTS_PER_COMP_PROMPT = 5

# All AI engines
ALL_ENGINES = ["chatgpt", "perplexity", "claude", "gemini"]

# Weights by signal type (higher = more likely to cause visibility change)
SIGNAL_TYPE_WEIGHTS: dict[str, float] = {
    "pricing_change": 1.5,
    "positioning_change": 1.4,
    "funding": 1.3,
    "acquisition": 1.3,
    "product_launch": 1.2,
    "product_change": 1.2,
    "feature_release": 1.2,
    "integration_added": 1.1,
    "integration_removed": 1.1,
    "landing_page_created": 1.0,
    "hiring": 0.7,
    "blog_post": 0.6,
    "review": 0.6,
    "marketing": 0.5,
    "website_change": 0.5,
}


def _compute_priority(impact_score: float) -> str:
    """Determine priority level from impact score (0-100)."""
    if impact_score >= 70:
        return PriorityLevel.P0.value
    elif impact_score >= 40:
        return PriorityLevel.P1.value
    elif impact_score >= 15:
        return PriorityLevel.P2.value
    return PriorityLevel.P3.value


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


def _compute_correlation_confidence(
    days_since_signal: int,
    signal_type: str,
    engines_affected_count: int,
    visibility_delta: int,
) -> float:
    """
    Compute correlation confidence (0-100).
    Higher = more likely the signal caused the visibility change.
    """
    score = 50.0  # baseline

    # Time distance: closer = higher confidence
    if days_since_signal <= 1:
        score += 25
    elif days_since_signal <= 3:
        score += 15
    elif days_since_signal <= 7:
        score += 5
    else:
        score -= 10

    # Signal importance weight
    type_weight = SIGNAL_TYPE_WEIGHTS.get(signal_type, 0.8)
    score += (type_weight - 0.8) * 20  # range: -6 to +14

    # Number of engines detecting change
    score += min(engines_affected_count * 5, 20)

    # Visibility delta magnitude
    score += min(abs(visibility_delta) * 3, 15)

    return round(max(0.0, min(100.0, score)), 0)


def _compute_confidence_factors(
    days_since_signal: int,
    signal_type: str,
    engines_affected_count: int,
    visibility_delta: int,
    prompt_relevance_score: float = 1.0,
) -> dict:
    """
    Compute confidence score AND return an explainable factors dict.
    Returned dict: {score, time_distance_days, engines_count, visibility_delta,
                    prompt_relevance_score, signal_type_weight, factors_text}
    """
    score = 50.0
    factors_text: list[str] = []

    # Time distance
    if days_since_signal <= 1:
        score += 25
        factors_text.append(
            f"Signal detected within {'same day' if days_since_signal == 0 else '1 day'} of visibility change"
        )
    elif days_since_signal <= 3:
        score += 15
        factors_text.append(f"Signal detected {days_since_signal} days before visibility change")
    elif days_since_signal <= 7:
        score += 5
        factors_text.append(f"Signal detected {days_since_signal} days before visibility change")
    else:
        score -= 10
        factors_text.append(
            f"Signal detected {days_since_signal} days ago (weaker time correlation)"
        )

    # Signal type weight
    type_weight = SIGNAL_TYPE_WEIGHTS.get(signal_type, 0.8)
    score += (type_weight - 0.8) * 20
    if type_weight >= 1.3:
        factors_text.append(
            f"High-impact signal type: {signal_type.replace('_', ' ')}"
        )

    # Engines
    score += min(engines_affected_count * 5, 20)
    factors_text.append(
        f"{engines_affected_count} AI engine{'s' if engines_affected_count != 1 else ''} confirmed visibility change"
    )

    # Delta magnitude
    score += min(abs(visibility_delta) * 3, 15)

    # Prompt relevance contribution
    relevance_boost = (prompt_relevance_score - 0.5) * 10
    score += relevance_boost
    if prompt_relevance_score >= 0.7:
        factors_text.append(f"Prompt relevance score: {prompt_relevance_score:.2f} (high)")
    elif prompt_relevance_score < 0.3:
        factors_text.append(f"Prompt relevance score: {prompt_relevance_score:.2f} (low)")
    else:
        factors_text.append(f"Prompt relevance score: {prompt_relevance_score:.2f}")

    score = round(max(0.0, min(100.0, score)), 0)

    return {
        "score": score,
        "time_distance_days": days_since_signal,
        "engines_count": engines_affected_count,
        "visibility_delta": visibility_delta,
        "prompt_relevance_score": round(prompt_relevance_score, 3),
        "signal_type_weight": type_weight,
        "factors_text": factors_text,
    }


def _generate_short_title(
    insight_type: str,
    competitor_name: str,
    signal_type: str | None,
    signal_title: str | None,
) -> str:
    """Generate a concise short_title for the compact card."""
    sig_label = (signal_type or "").replace("_", " ").title()
    if insight_type == InsightType.AI_VISIBILITY_HIJACK.value:
        return f"New in AI: {competitor_name}"
    elif insight_type == InsightType.AI_VISIBILITY_LOSS.value:
        return f"Lost from AI: {competitor_name}"
    elif insight_type == InsightType.AI_DOMINANCE.value:
        return f"AI Dominance: {competitor_name}"
    elif signal_title and len(signal_title) <= 80:
        return signal_title
    elif sig_label:
        return f"{sig_label}: {competitor_name}"
    return f"Visibility change: {competitor_name}"


def _generate_signal_headline(
    signal_type: str,
    signal_title: str,
    insight_type: str,
) -> str:
    """
    Generate a concise one-line signal headline for the compact card.
    For non-signal insights (hijack/loss/dominance) returns an empty string.
    """
    if insight_type != InsightType.AI_IMPACT.value:
        return ""
    if not signal_title:
        return signal_type.replace("_", " ").title() if signal_type else ""
    # Truncate to first sentence if ≤100 chars, else hard truncate
    first = signal_title.split(".")[0].strip()
    if len(first) <= 100:
        return first
    if len(signal_title) <= 100:
        return signal_title
    return signal_title[:97] + "…"


def _generate_summary_text(
    insight_type: str,
    competitor_name: str,
    signal_type: str,
    engines_affected: list[str],
    visibility_delta: int,
    visibility_before: int,
    visibility_after: int,
) -> str:
    """
    Generate a one-line summary for the compact card.
    Maximum one sentence — no paragraphs.
    """
    eng_count = len(engines_affected)
    eng_plural = "engine" if eng_count == 1 else "engines"
    sig_label = (signal_type or "").replace("_", " ")

    if insight_type == InsightType.AI_VISIBILITY_HIJACK.value:
        return f"{competitor_name} newly entered AI responses across {eng_count} {eng_plural}."
    elif insight_type == InsightType.AI_VISIBILITY_LOSS.value:
        return f"{competitor_name} disappeared from AI responses ({eng_count} {eng_plural} previously)."
    elif insight_type == InsightType.AI_DOMINANCE.value:
        return f"{competitor_name} now dominates all {eng_count} AI {eng_plural}."
    else:
        # ai_impact
        if visibility_before == 0 and visibility_after > 0:
            return f"{competitor_name} appeared in AI responses after {sig_label}."
        elif visibility_delta > 0:
            return f"{competitor_name} gained +{visibility_delta} AI mentions after {sig_label}."
        else:
            return f"{competitor_name} lost {abs(visibility_delta)} AI mentions after {sig_label}."


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


def _generate_reasoning(
    insight_type: str,
    competitor_name: str,
    signal_type: str,
    signal_title: str,
    prompt_text: str,
    engines_affected: list[str],
    visibility_delta: int,
    prompt_cluster_name: str | None,
) -> str:
    """Generate structured reasoning explaining why the signal likely caused the change."""
    sig_label = signal_type.replace("_", " ")
    engines_str = ", ".join(engines_affected) if engines_affected else "none"
    cluster_ref = f' (cluster: "{prompt_cluster_name}")' if prompt_cluster_name else ""

    if insight_type == InsightType.AI_VISIBILITY_HIJACK.value:
        return (
            f"{competitor_name} was newly detected in AI engine responses for "
            f"\"{prompt_text}\"{cluster_ref}. This is a new market entrant in AI-generated "
            f"recommendations, appearing across {engines_str}. Monitor closely for sustained presence."
        )
    elif insight_type == InsightType.AI_VISIBILITY_LOSS.value:
        return (
            f"{competitor_name} has disappeared from AI engine responses for "
            f"\"{prompt_text}\"{cluster_ref}. Previously present, now absent from {engines_str}. "
            f"This may indicate reduced relevance or competitor displacement."
        )
    elif insight_type == InsightType.AI_DOMINANCE.value:
        return (
            f"{competitor_name} appears across all queried AI engines ({engines_str}) for "
            f"\"{prompt_text}\"{cluster_ref}. This dominant presence suggests strong brand "
            f"recognition and SEO/content authority in this category."
        )

    # Default: ai_impact
    return (
        f"{competitor_name} had a {sig_label} — \"{signal_title}\". "
        f"This likely {'improved' if visibility_delta > 0 else 'reduced'} relevance for "
        f"prompts related to \"{prompt_text}\"{cluster_ref}. "
        f"The visibility change was detected across {engines_str}, with a delta of "
        f"{'+' if visibility_delta > 0 else ''}{visibility_delta} mentions."
    )


def _normalize_to_date(dt: datetime) -> datetime:
    """Normalize a datetime to midnight UTC for date-only comparison."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    # Convert to UTC first, then strip time — avoids IST/other-tz midnight bugs
    dt_utc = dt.astimezone(timezone.utc)
    return dt_utc.replace(hour=0, minute=0, second=0, microsecond=0)


def _get_engine_breakdown(
    db: Session,
    comp_id: str,
    tp_id: str,
    date_start: datetime,
    date_end: datetime,
) -> dict:
    """Build per-engine breakdown: {engine: {rank, mentioned, citation_url}}."""
    events = (
        db.query(AIVisibilityEvent)
        .filter(
            AIVisibilityEvent.competitor_id == comp_id,
            AIVisibilityEvent.tracked_prompt_id == tp_id,
            AIVisibilityEvent.mentioned == True,
            AIVisibilityEvent.event_date >= date_start,
            AIVisibilityEvent.event_date <= date_end,
        )
        .all()
    )
    breakdown = {}
    for ev in events:
        breakdown[ev.engine] = {
            "rank": ev.rank_position,
            "mentioned": True,
            "citation_url": ev.citation_url,
        }
    return breakdown


def _get_mentioned_brands_for_prompt(
    db: Session,
    tp: AITrackedPrompt,
    date_start: datetime,
    date_end: datetime,
) -> list[str]:
    """Get all mentioned brands across engines for this prompt in a date range."""
    from app.services.ai_visibility.prompt_execution import normalize_prompt
    norm = normalize_prompt(tp.prompt_text)
    runs = (
        db.query(AIPromptRun)
        .filter(
            AIPromptRun.normalized_text == norm,
            AIPromptRun.run_date >= date_start,
            AIPromptRun.run_date <= date_end,
            AIPromptRun.status == RunStatusEnum.COMPLETED.value,
        )
        .all()
    )
    brands = set()
    for run in runs:
        results = db.query(AIEngineResult).filter(
            AIEngineResult.prompt_run_id == run.id,
            AIEngineResult.status == RunStatusEnum.COMPLETED.value,
        ).all()
        for er in results:
            for b in (er.mentioned_brands or []):
                brands.add(b)
    return sorted(brands)


def _get_prompt_cluster_name(db: Session, tp: AITrackedPrompt) -> str | None:
    """Get the cluster name for a tracked prompt, if any."""
    if tp.cluster_id:
        cluster = db.query(AIPromptCluster).filter(
            AIPromptCluster.id == tp.cluster_id
        ).first()
        if cluster:
            return cluster.cluster_topic
    return None


def _get_citations_by_engine(
    db: Session,
    comp_id: str,
    tp_id: str,
    date_start: datetime,
    date_end: datetime,
) -> dict[str, list[str]]:
    """Get citations grouped by engine."""
    events = (
        db.query(AIVisibilityEvent.engine, AIVisibilityEvent.citation_url)
        .filter(
            AIVisibilityEvent.competitor_id == comp_id,
            AIVisibilityEvent.tracked_prompt_id == tp_id,
            AIVisibilityEvent.citation_url != None,
            AIVisibilityEvent.event_date >= date_start,
            AIVisibilityEvent.event_date <= date_end,
        )
        .distinct()
        .limit(20)
        .all()
    )
    result: dict[str, list[str]] = {}
    for engine, url in events:
        if url:
            result.setdefault(engine, []).append(url)
    return result


def correlate_signals_with_visibility(
    db: Session,
    workspace_id: str,
    days: int = CORRELATION_WINDOW_DAYS,
) -> dict:
    """
    Run correlation engine for a workspace.
    Generates four types of insights:
    1. ai_impact — signal-correlated visibility changes
    2. ai_visibility_hijack — new competitor enters AI responses
    3. ai_visibility_loss — competitor disappears from AI responses
    4. ai_dominance — competitor across ALL engines
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

    tracked_prompts = (
        db.query(AITrackedPrompt)
        .filter(
            AITrackedPrompt.workspace_id == workspace_id,
            AITrackedPrompt.is_active == True,
        )
        .all()
    )

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

        # ── Type 1: AI Impact Insights (signal → visibility correlation) ──
        if signals:
            for tp in tracked_prompts:
                cluster_name = _get_prompt_cluster_name(db, tp)
                scored_signals = []
                for sig_id, sig_type, sig_title, sig_time in signals:
                    # Prompt-signal relevance filter (PROMPT-10)
                    relevance_score = compute_prompt_signal_relevance(
                        sig_type, sig_title, tp.prompt_text, comp.name
                    )
                    if relevance_score < PROMPT_SIGNAL_RELEVANCE_THRESHOLD:
                        logger.debug(
                            "Skipping signal '%s' (%s) for prompt '%s' — relevance %.3f < %.2f",
                            sig_title[:50], sig_type, tp.prompt_text[:50],
                            relevance_score, PROMPT_SIGNAL_RELEVANCE_THRESHOLD,
                        )
                        continue

                    type_weight = SIGNAL_TYPE_WEIGHTS.get(sig_type, 0.8)
                    days_ago = max((now - sig_time).days, 0)
                    recency = 1.0 / (1 + days_ago * 0.15)
                    signal_score = type_weight * recency
                    scored_signals.append((signal_score, relevance_score, sig_id, sig_type, sig_title, sig_time))

                scored_signals.sort(key=lambda x: x[0], reverse=True)
                top_signals = scored_signals[:MAX_INSIGHTS_PER_COMP_PROMPT]

                for signal_score, prompt_relevance, signal_id, signal_type, signal_title, signal_time in top_signals:
                    signal_date = _normalize_to_date(signal_time)
                    before_start = signal_date - timedelta(days=days)
                    after_end = signal_date + timedelta(days=days)

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

                    if before_count == 0 and after_count == 0:
                        continue
                    if before_count == after_count:
                        continue

                    days_since = max((now - signal_time).days, 0)
                    delta = after_count - before_count

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
                    if impact_score < 5.0:
                        continue

                    priority = _compute_priority(impact_score)
                    conf_factors = _compute_confidence_factors(
                        days_since, signal_type, len(engines_affected), delta,
                        prompt_relevance,
                    )
                    confidence = conf_factors["score"]

                    explanation = _generate_explanation(
                        comp.name, signal_title, signal_type,
                        before_count, after_count, engines_affected, tp.prompt_text,
                    )
                    reasoning = _generate_reasoning(
                        InsightType.AI_IMPACT.value, comp.name,
                        signal_type, signal_title, tp.prompt_text,
                        engines_affected, delta, cluster_name,
                    )
                    short_title = _generate_short_title(
                        InsightType.AI_IMPACT.value, comp.name,
                        signal_type, signal_title,
                    )
                    signal_headline = _generate_signal_headline(
                        signal_type, signal_title, InsightType.AI_IMPACT.value,
                    )
                    summary_text = _generate_summary_text(
                        InsightType.AI_IMPACT.value, comp.name, signal_type,
                        engines_affected, delta, before_count, after_count,
                    )
                    engine_breakdown = _get_engine_breakdown(
                        db, comp.id, tp.id, before_start, after_end,
                    )

                    # Get previous/current mentions evidence
                    prev_mentions = _get_mentioned_brands_for_prompt(
                        db, tp, before_start, signal_date,
                    )
                    curr_mentions = _get_mentioned_brands_for_prompt(
                        db, tp, signal_date, after_end,
                    )

                    db.add(AIImpactInsight(
                        workspace_id=workspace_id,
                        competitor_id=comp.id,
                        insight_type=InsightType.AI_IMPACT.value,
                        signal_event_id=signal_id,
                        signal_type=signal_type,
                        signal_title=signal_title[:500],
                        signal_timestamp=signal_time,
                        prompt_text=tp.prompt_text,
                        tracked_prompt_id=tp.id,
                        visibility_before=before_count,
                        visibility_after=after_count,
                        visibility_delta=delta,
                        engines_affected=engines_affected,
                        citations=citations,
                        impact_score=impact_score,
                        priority_level=priority,
                        correlation_confidence=confidence,
                        explanation=explanation,
                        reasoning=reasoning,
                        short_title=short_title,
                        signal_headline=signal_headline,
                        confidence_factors=conf_factors,
                        prompt_relevance_score=prompt_relevance,
                        engine_breakdown=engine_breakdown,
                        previous_mentions=prev_mentions,
                        current_mentions=curr_mentions,
                        prompt_cluster_name=cluster_name,
                    ))
                    insights_created += 1

        # ── Types 2-4: Hijack / Loss / Dominance (signal-independent) ──
        for tp in tracked_prompts:
            cluster_name = _get_prompt_cluster_name(db, tp)
            today = _normalize_to_date(now)
            yesterday = today - timedelta(days=1)
            window_start = today - timedelta(days=days)

            # Get current engines where this competitor is mentioned (today or most recent)
            current_engines = (
                db.query(AIVisibilityEvent.engine)
                .filter(
                    AIVisibilityEvent.competitor_id == comp.id,
                    AIVisibilityEvent.tracked_prompt_id == tp.id,
                    AIVisibilityEvent.mentioned == True,
                    AIVisibilityEvent.event_date >= yesterday,
                    AIVisibilityEvent.event_date <= today,
                )
                .distinct()
                .all()
            )
            current_engine_set = {e[0] for e in current_engines}

            # Get previous engines (before yesterday)
            prev_engines = (
                db.query(AIVisibilityEvent.engine)
                .filter(
                    AIVisibilityEvent.competitor_id == comp.id,
                    AIVisibilityEvent.tracked_prompt_id == tp.id,
                    AIVisibilityEvent.mentioned == True,
                    AIVisibilityEvent.event_date >= window_start,
                    AIVisibilityEvent.event_date < yesterday,
                )
                .distinct()
                .all()
            )
            prev_engine_set = {e[0] for e in prev_engines}

            prev_mentions = _get_mentioned_brands_for_prompt(
                db, tp, window_start, yesterday,
            )
            curr_mentions = _get_mentioned_brands_for_prompt(
                db, tp, yesterday, today,
            )

            # ── Type 2: AI Visibility Hijack (new competitor in responses) ──
            if current_engine_set and not prev_engine_set:
                eng_list = sorted(current_engine_set)
                engine_bd = _get_engine_breakdown(
                    db, comp.id, tp.id, yesterday, today,
                )
                impact = min(len(current_engine_set) * 15 + 10, 60.0)
                priority = _compute_priority(impact)
                confidence = _compute_correlation_confidence(
                    0, "", len(current_engine_set), len(current_engine_set),
                )
                short_title = _generate_short_title(
                    InsightType.AI_VISIBILITY_HIJACK.value, comp.name, None, None,
                )
                reasoning = _generate_reasoning(
                    InsightType.AI_VISIBILITY_HIJACK.value, comp.name,
                    "", "", tp.prompt_text, eng_list, len(current_engine_set),
                    cluster_name,
                )

                db.add(AIImpactInsight(
                    workspace_id=workspace_id,
                    competitor_id=comp.id,
                    insight_type=InsightType.AI_VISIBILITY_HIJACK.value,
                    signal_type="ai_visibility_hijack",
                    signal_title=f"{comp.name} newly detected in AI responses",
                    prompt_text=tp.prompt_text,
                    tracked_prompt_id=tp.id,
                    visibility_before=0,
                    visibility_after=len(current_engine_set),
                    visibility_delta=len(current_engine_set),
                    engines_affected=eng_list,
                    impact_score=round(impact, 1),
                    priority_level=priority,
                    correlation_confidence=confidence,
                    explanation=f"{comp.name} was newly detected in {len(eng_list)} AI engine(s): {', '.join(eng_list)}.",
                    reasoning=reasoning,
                    short_title=short_title,
                    engine_breakdown=engine_bd,
                    previous_mentions=prev_mentions,
                    current_mentions=curr_mentions,
                    prompt_cluster_name=cluster_name,
                ))
                insights_created += 1

            # ── Type 3: AI Visibility Loss (disappeared from responses) ──
            if prev_engine_set and not current_engine_set:
                eng_list = sorted(prev_engine_set)
                impact = min(len(prev_engine_set) * 12 + 8, 50.0)
                priority = _compute_priority(impact)
                confidence = _compute_correlation_confidence(
                    0, "", len(prev_engine_set), -len(prev_engine_set),
                )
                short_title = _generate_short_title(
                    InsightType.AI_VISIBILITY_LOSS.value, comp.name, None, None,
                )
                reasoning = _generate_reasoning(
                    InsightType.AI_VISIBILITY_LOSS.value, comp.name,
                    "", "", tp.prompt_text, eng_list, -len(prev_engine_set),
                    cluster_name,
                )

                db.add(AIImpactInsight(
                    workspace_id=workspace_id,
                    competitor_id=comp.id,
                    insight_type=InsightType.AI_VISIBILITY_LOSS.value,
                    signal_type="ai_visibility_loss",
                    signal_title=f"{comp.name} disappeared from AI responses",
                    prompt_text=tp.prompt_text,
                    tracked_prompt_id=tp.id,
                    visibility_before=len(prev_engine_set),
                    visibility_after=0,
                    visibility_delta=-len(prev_engine_set),
                    engines_affected=eng_list,
                    impact_score=round(impact, 1),
                    priority_level=priority,
                    correlation_confidence=confidence,
                    explanation=f"{comp.name} was previously in {len(eng_list)} engine(s) but is no longer detected.",
                    reasoning=reasoning,
                    short_title=short_title,
                    previous_mentions=prev_mentions,
                    current_mentions=curr_mentions,
                    prompt_cluster_name=cluster_name,
                ))
                insights_created += 1

            # ── Type 4: AI Dominance (appears in ALL engines) ──
            if len(current_engine_set) >= len(ALL_ENGINES):
                eng_list = sorted(current_engine_set)
                engine_bd = _get_engine_breakdown(
                    db, comp.id, tp.id, yesterday, today,
                )
                impact = 75.0  # Dominance is always high impact
                priority = _compute_priority(impact)
                confidence = 90.0  # Very high — data-driven
                short_title = _generate_short_title(
                    InsightType.AI_DOMINANCE.value, comp.name, None, None,
                )
                reasoning = _generate_reasoning(
                    InsightType.AI_DOMINANCE.value, comp.name,
                    "", "", tp.prompt_text, eng_list, len(current_engine_set),
                    cluster_name,
                )

                db.add(AIImpactInsight(
                    workspace_id=workspace_id,
                    competitor_id=comp.id,
                    insight_type=InsightType.AI_DOMINANCE.value,
                    signal_type="ai_dominance",
                    signal_title=f"{comp.name} dominates all AI engines",
                    prompt_text=tp.prompt_text,
                    tracked_prompt_id=tp.id,
                    visibility_before=0,
                    visibility_after=len(current_engine_set),
                    visibility_delta=len(current_engine_set),
                    engines_affected=eng_list,
                    impact_score=impact,
                    priority_level=priority,
                    correlation_confidence=confidence,
                    explanation=f"{comp.name} appears in ALL {len(eng_list)} AI engines: {', '.join(eng_list)}.",
                    reasoning=reasoning,
                    short_title=short_title,
                    engine_breakdown=engine_bd,
                    previous_mentions=prev_mentions,
                    current_mentions=curr_mentions,
                    prompt_cluster_name=cluster_name,
                ))
                insights_created += 1

    db.commit()

    return {
        "insights_created": insights_created,
        "competitors_analyzed": len(competitors),
    }
