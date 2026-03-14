"""
AI Optimization Playbooks — converts intelligence insights into
recommended strategic actions.

Playbooks map insights to actionable strategy recommendations based on
the type and severity of visibility changes detected.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy.orm import Session

from app.models.models import (
    AIImpactInsight,
    Competitor,
    InsightType,
    PriorityLevel,
)

logger = logging.getLogger(__name__)

# Only generate playbooks for high-priority insights
PLAYBOOK_PRIORITY_THRESHOLD = {"P0", "P1"}

# Strategy templates by insight type
PLAYBOOK_TEMPLATES: dict[str, list[str]] = {
    InsightType.AI_VISIBILITY_HIJACK.value: [
        "Publish a comparison page: {our_brand} vs {competitor}",
        "Create content targeting the prompt: \"{prompt}\"",
        "Monitor {competitor} for continued AI visibility growth",
        "Optimize existing content for AI engine crawlability",
    ],
    InsightType.AI_DOMINANCE.value: [
        "Analyze why {competitor} dominates AI responses for \"{prompt}\"",
        "Create authoritative documentation covering this topic",
        "Build backlink strategy targeting AI-cited sources",
        "Publish expert content to compete for AI recommendations",
    ],
    InsightType.AI_VISIBILITY_LOSS.value: [
        "Audit content that previously earned AI visibility for \"{prompt}\"",
        "Refresh and update existing comparison pages",
        "Create new content targeting lost AI visibility topics",
        "Review competitor content changes that may have displaced you",
    ],
    InsightType.AI_IMPACT.value: [
        "Publish comparison page: Your Brand vs {competitor}",
        "Create documentation on: {prompt}",
        "Target prompts related to {competitor}'s signal",
        "Monitor {competitor}'s continued visibility trajectory",
    ],
    InsightType.AI_CATEGORY_OWNERSHIP.value: [
        "Create category-specific comparison content",
        "Target underperforming prompts in this category",
        "Build authoritative content to challenge {competitor}'s category dominance",
    ],
    InsightType.AI_SHARE_OF_VOICE.value: [
        "Increase content volume for prompts in this category",
        "Target AI engines where {competitor} has strong presence",
        "Create structured data and documentation for AI crawlers",
    ],
}


def generate_optimization_playbooks(
    db: Session,
    workspace_id: str,
) -> int:
    """
    Generate optimization playbook insights from existing high-priority insights.
    Scans recent P0/P1 insights and creates actionable playbook entries.
    Returns count of playbooks created.
    """
    # Get high-priority insights that aren't already playbooks
    base_insights = (
        db.query(AIImpactInsight)
        .filter(
            AIImpactInsight.workspace_id == workspace_id,
            AIImpactInsight.priority_level.in_(list(PLAYBOOK_PRIORITY_THRESHOLD)),
            AIImpactInsight.insight_type != InsightType.AI_OPTIMIZATION_PLAYBOOK.value,
        )
        .all()
    )

    if not base_insights:
        return 0

    competitors = (
        db.query(Competitor)
        .filter(Competitor.workspace_id == workspace_id, Competitor.is_active == True)
        .all()
    )
    comp_map = {str(c.id): c for c in competitors}

    # Group insights by competitor to avoid duplicate playbooks
    by_comp: dict[str, list[AIImpactInsight]] = {}
    for ins in base_insights:
        comp_id = str(ins.competitor_id)
        by_comp.setdefault(comp_id, []).append(ins)

    insights_created = 0

    for comp_id, comp_insights in by_comp.items():
        comp = comp_map.get(comp_id)
        if not comp:
            continue

        # Pick the highest-impact insight as the trigger
        trigger = max(comp_insights, key=lambda x: x.impact_score or 0)
        templates = PLAYBOOK_TEMPLATES.get(
            trigger.insight_type, PLAYBOOK_TEMPLATES[InsightType.AI_IMPACT.value]
        )

        # Format actions
        actions = []
        for tmpl in templates:
            action = tmpl.format(
                competitor=comp.name,
                our_brand="Your Brand",
                prompt=(trigger.prompt_text or "AI visibility topics")[:60],
            )
            actions.append(action)

        # Add cross-insight recommendations if multiple insight types
        insight_types = {i.insight_type for i in comp_insights}
        if len(insight_types) > 1:
            actions.append(
                f"Review all {len(comp_insights)} intelligence signals for {comp.name} to prioritize actions"
            )

        # Collect target prompts from insights
        target_prompts = list({
            i.prompt_text for i in comp_insights
            if i.prompt_text and not i.prompt_text.startswith("Across")
        })[:5]

        if target_prompts:
            prompt_list = ", ".join(f'"{p}"' for p in target_prompts[:3])
            actions.append(f"Target prompts: {prompt_list}")

        db.add(AIImpactInsight(
            workspace_id=workspace_id,
            competitor_id=comp.id,
            insight_type=InsightType.AI_OPTIMIZATION_PLAYBOOK.value,
            signal_type="ai_optimization_playbook",
            signal_title=f"Optimization Playbook: {comp.name}",
            prompt_text=trigger.prompt_text,
            visibility_before=trigger.visibility_before or 0,
            visibility_after=trigger.visibility_after or 0,
            visibility_delta=trigger.visibility_delta or 0,
            engines_affected=trigger.engines_affected or [],
            impact_score=round((trigger.impact_score or 50) * 0.8, 1),
            priority_level=trigger.priority_level,
            correlation_confidence=85.0,
            explanation=(
                f"Based on {len(comp_insights)} intelligence signals for {comp.name}, "
                f"here are recommended strategic actions to optimize AI visibility."
            ),
            reasoning=(
                f"Playbook generated from {len(comp_insights)} insights "
                f"(types: {', '.join(sorted(insight_types))}). "
                f"Trigger: {trigger.short_title or trigger.signal_title}."
            ),
            short_title=f"Playbook: {len(actions)} actions for {comp.name}",
            strategy_actions=actions,
            category_data={
                "trigger_insight_type": trigger.insight_type,
                "trigger_insight_id": str(trigger.id),
                "total_signals": len(comp_insights),
                "insight_types": sorted(insight_types),
                "target_prompts": target_prompts,
            },
        ))
        insights_created += 1

    return insights_created
