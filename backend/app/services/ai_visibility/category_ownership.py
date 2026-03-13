"""
AI Category Ownership Intelligence — computes which competitor dominates
AI answers across a category of prompts.

Categories group multiple prompts (e.g., "AI Code Editors" groups
"best ai code editors", "top ai coding assistants", etc.).

Ownership = competitor_mentions / total_mentions within a category.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone, timedelta

from sqlalchemy.orm import Session
from sqlalchemy import func as sa_func

from app.models.models import (
    AIImpactInsight,
    AITrackedPrompt,
    AIVisibilityEvent,
    CategoryVisibility,
    Competitor,
    InsightType,
    PriorityLevel,
    PromptCategory,
)

logger = logging.getLogger(__name__)


def compute_category_ownership(
    db: Session,
    workspace_id: str,
    days: int = 7,
) -> list[dict]:
    """
    Compute visibility share per competitor per category.
    Only processes categories that have at least one tracked prompt.

    Returns list of dicts:
    [{category_id, category_name, competitors: [{competitor_id, name, share, mentions, ...}]}]
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)

    categories = (
        db.query(PromptCategory)
        .filter(PromptCategory.workspace_id == workspace_id)
        .all()
    )

    if not categories:
        return []

    competitors = (
        db.query(Competitor)
        .filter(Competitor.workspace_id == workspace_id, Competitor.is_active == True)
        .all()
    )
    comp_map = {str(c.id): c.name for c in competitors}

    results = []
    for cat in categories:
        # Get prompts in this category
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

        # Count mentions per competitor across all prompts in category
        mention_counts = (
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

        total_mentions = sum(m.mentions for m in mention_counts)
        if total_mentions == 0:
            continue

        comp_shares = []
        for row in mention_counts:
            share = round(row.mentions / total_mentions * 100, 1)
            comp_shares.append({
                "competitor_id": str(row.competitor_id),
                "competitor_name": comp_map.get(str(row.competitor_id), "Unknown"),
                "visibility_share": share,
                "mentions": row.mentions,
                "engine_count": row.engines,
            })

        comp_shares.sort(key=lambda x: x["visibility_share"], reverse=True)

        results.append({
            "category_id": str(cat.id),
            "category_name": cat.category_name,
            "prompt_count": len(prompts),
            "total_mentions": total_mentions,
            "competitors": comp_shares,
        })

    return results


def store_category_visibility(
    db: Session,
    workspace_id: str,
    ownership_data: list[dict],
    time_window: str = "7d",
) -> int:
    """
    Store computed ownership data in category_visibility table.
    Clears previous entries for this workspace before inserting.
    """
    db.query(CategoryVisibility).filter(
        CategoryVisibility.workspace_id == workspace_id,
    ).delete(synchronize_session=False)
    db.flush()

    stored = 0
    for cat_data in ownership_data:
        for comp in cat_data["competitors"]:
            db.add(CategoryVisibility(
                workspace_id=workspace_id,
                category_id=cat_data["category_id"],
                competitor_id=comp["competitor_id"],
                visibility_share=comp["visibility_share"],
                engine_count=comp["engine_count"],
                prompt_count=cat_data["prompt_count"],
                total_mentions=comp["mentions"],
                time_window=time_window,
            ))
            stored += 1

    return stored


def generate_category_ownership_insights(
    db: Session,
    workspace_id: str,
    days: int = 7,
) -> int:
    """
    Generate category ownership insights for categories where a single
    competitor has a dominant share (>= 30%).
    Returns count of insights created.
    """
    ownership_data = compute_category_ownership(db, workspace_id, days)

    if not ownership_data:
        return 0

    store_category_visibility(db, workspace_id, ownership_data, f"{days}d")

    competitors = (
        db.query(Competitor)
        .filter(Competitor.workspace_id == workspace_id, Competitor.is_active == True)
        .all()
    )
    comp_map = {str(c.id): c for c in competitors}

    insights_created = 0
    for cat_data in ownership_data:
        if not cat_data["competitors"]:
            continue

        # Generate insight for top competitor in each category
        top = cat_data["competitors"][0]
        if top["visibility_share"] < 20.0:
            continue  # Not dominant enough

        comp = comp_map.get(top["competitor_id"])
        if not comp:
            continue

        explanation = (
            f"{comp.name} leads the '{cat_data['category_name']}' category "
            f"with {top['visibility_share']}% of AI mentions "
            f"across {cat_data['prompt_count']} prompts."
        )

        # Determine priority based on share
        if top["visibility_share"] >= 50:
            priority = PriorityLevel.P1.value
        elif top["visibility_share"] >= 35:
            priority = PriorityLevel.P2.value
        else:
            priority = PriorityLevel.P3.value

        db.add(AIImpactInsight(
            workspace_id=workspace_id,
            competitor_id=comp.id,
            insight_type=InsightType.AI_CATEGORY_OWNERSHIP.value,
            signal_type="ai_category_ownership",
            signal_title=f"{comp.name} leads '{cat_data['category_name']}' category",
            visibility_before=0,
            visibility_after=top["mentions"],
            visibility_delta=top["mentions"],
            engines_affected=[],
            impact_score=round(top["visibility_share"], 1),
            priority_level=priority,
            correlation_confidence=min(top["visibility_share"] + 20, 95.0),
            explanation=explanation,
            reasoning=(
                f"Category ownership computed across {cat_data['prompt_count']} prompts "
                f"in '{cat_data['category_name']}'. {comp.name} has {top['mentions']} mentions "
                f"out of {cat_data['total_mentions']} total ({top['visibility_share']}%)."
            ),
            short_title=f"Category Leader: {comp.name} in {cat_data['category_name']}",
            category_data=cat_data,
        ))
        insights_created += 1

    return insights_created
