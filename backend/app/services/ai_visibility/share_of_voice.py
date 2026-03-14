"""
AI Share of Voice Intelligence — measures competitor visibility proportion
across prompts and engines within categories.

share_of_voice = competitor_mentions / total_mentions

Generates AI_SHARE_OF_VOICE insights when a competitor owns a significant
share of AI responses in a category.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy.orm import Session
from sqlalchemy import func as sa_func

from app.models.models import (
    AIImpactInsight,
    AITrackedPrompt,
    AIVisibilityEvent,
    Competitor,
    InsightType,
    PriorityLevel,
    PromptCategory,
)

logger = logging.getLogger(__name__)

SOV_THRESHOLD = 15.0  # Generate insight when share >= 15%


def generate_share_of_voice_insights(
    db: Session,
    workspace_id: str,
    days: int = 7,
) -> int:
    """
    Compute share of voice per competitor per category and generate insights.
    Only processes categories with assigned prompts.
    Returns count of insights created.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)

    categories = (
        db.query(PromptCategory)
        .filter(PromptCategory.workspace_id == workspace_id)
        .all()
    )
    if not categories:
        return 0

    competitors = (
        db.query(Competitor)
        .filter(Competitor.workspace_id == workspace_id, Competitor.is_active == True)
        .all()
    )
    comp_map = {str(c.id): c for c in competitors}

    insights_created = 0

    for cat in categories:
        prompts = (
            db.query(AITrackedPrompt)
            .filter(
                AITrackedPrompt.workspace_id == workspace_id,
                AITrackedPrompt.category_id == cat.id,
                AITrackedPrompt.is_active == True,
            )
            .all()
        )
        if not prompts:
            continue

        prompt_ids = [p.id for p in prompts]

        # Total mentions across all competitors in this category
        total_mentions = (
            db.query(sa_func.count(AIVisibilityEvent.id))
            .filter(
                AIVisibilityEvent.workspace_id == workspace_id,
                AIVisibilityEvent.tracked_prompt_id.in_(prompt_ids),
                AIVisibilityEvent.mentioned == True,
                AIVisibilityEvent.event_date >= since,
            )
            .scalar() or 0
        )

        if total_mentions == 0:
            continue

        # Mentions per competitor
        mention_rows = (
            db.query(
                AIVisibilityEvent.competitor_id,
                sa_func.count(AIVisibilityEvent.id).label("mentions"),
                sa_func.count(sa_func.distinct(AIVisibilityEvent.engine)).label("engines"),
            )
            .filter(
                AIVisibilityEvent.workspace_id == workspace_id,
                AIVisibilityEvent.tracked_prompt_id.in_(prompt_ids),
                AIVisibilityEvent.mentioned == True,
                AIVisibilityEvent.event_date >= since,
            )
            .group_by(AIVisibilityEvent.competitor_id)
            .all()
        )

        for row in mention_rows:
            comp = comp_map.get(str(row.competitor_id))
            if not comp:
                continue

            share = round(row.mentions / total_mentions * 100, 1)
            if share < SOV_THRESHOLD:
                continue

            # Priority based on share
            if share >= 50:
                priority = PriorityLevel.P1.value
            elif share >= 30:
                priority = PriorityLevel.P2.value
            else:
                priority = PriorityLevel.P3.value

            db.add(AIImpactInsight(
                workspace_id=workspace_id,
                competitor_id=comp.id,
                insight_type=InsightType.AI_SHARE_OF_VOICE.value,
                signal_type="ai_share_of_voice",
                signal_title=f"{comp.name} owns {share}% of AI responses in {cat.category_name}",
                prompt_text=f"Across {len(prompts)} prompts in '{cat.category_name}'",
                visibility_before=0,
                visibility_after=round(share),
                visibility_delta=round(share),
                engines_affected=[],
                impact_score=round(share, 1),
                priority_level=priority,
                correlation_confidence=min(share + 30, 95.0),
                explanation=(
                    f"{comp.name} now owns {share}% of AI responses "
                    f"in '{cat.category_name}' across {len(prompts)} prompts "
                    f"and {row.engines} AI engines ({row.mentions}/{total_mentions} mentions)."
                ),
                reasoning=(
                    f"Share of voice computed: {comp.name} has {row.mentions} mentions "
                    f"out of {total_mentions} total in '{cat.category_name}'. "
                    f"This represents {share}% narrative control across AI engines."
                ),
                short_title=f"Share of Voice: {comp.name} owns {share}% in {cat.category_name}",
                category_data={
                    "category_id": str(cat.id),
                    "category_name": cat.category_name,
                    "prompt_count": len(prompts),
                    "total_mentions": total_mentions,
                    "share_of_voice": share,
                    "competitor_mentions": row.mentions,
                    "engine_count": row.engines,
                },
            ))
            insights_created += 1

    return insights_created
