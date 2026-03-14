"""
AI Competitive Strategy Alerts — converts insights into recommended actions.

Generates strategy alert insights when:
- An AI Impact Insight exists with positive visibility delta
- Confidence >= threshold
- Maps signal_type to concrete recommended actions
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.models import (
    AIImpactInsight,
    Competitor,
    InsightType,
    PriorityLevel,
)

logger = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = 50.0

# Signal type → recommended strategy actions
STRATEGY_MAP: dict[str, list[str]] = {
    "integration_added": [
        "Publish integrations comparison page",
        "Create integration ecosystem content",
        "Target prompt: 'best {category} integrations'",
    ],
    "landing_page_created": [
        "Create competing landing page",
        "Update SEO content targeting similar keywords",
        "Monitor competitor's new page messaging",
    ],
    "positioning_change": [
        "Update product messaging and positioning",
        "Refresh comparison pages",
        "Review sales talk tracks",
    ],
    "funding": [
        "Publish competitor comparison blog post",
        "Highlight your stability and track record",
        "Create 'why choose us over {competitor}' content",
    ],
    "pricing_change": [
        "Update pricing comparison page",
        "Create value-based messaging content",
        "Target prompt: 'best affordable {category}'",
    ],
    "feature_launch": [
        "Add feature comparison page",
        "Publish response content highlighting your strengths",
        "Update product roadmap communications",
    ],
    "product_change": [
        "Create competitive analysis update",
        "Update feature comparison documentation",
        "Brief sales team on competitor changes",
    ],
    "blog_post": [
        "Publish competing thought leadership content",
        "Create response blog post",
        "Update content calendar to address topic",
    ],
    "hiring": [
        "Monitor competitor's growth direction",
        "Highlight your team's expertise",
        "Create content about your team's capabilities",
    ],
    "website_change": [
        "Review and update your website messaging",
        "Analyze competitor's new positioning",
        "Update competitive intelligence brief",
    ],
}

DEFAULT_ACTIONS = [
    "Review competitor's recent changes",
    "Update competitive intelligence documentation",
    "Brief sales team on competitive landscape shifts",
]


def _get_strategy_actions(signal_type: str, competitor_name: str, prompt_text: str) -> list[str]:
    """Get recommended strategy actions for a signal type."""
    actions = STRATEGY_MAP.get(signal_type, DEFAULT_ACTIONS)
    # Personalize with competitor name and prompt
    result = []
    for action in actions:
        personalized = action.replace("{competitor}", competitor_name)
        # Extract category hint from prompt
        category = prompt_text.replace("best ", "").replace("top ", "").strip()
        personalized = personalized.replace("{category}", category)
        result.append(personalized)
    return result


def _generate_strategy_explanation(
    competitor_name: str,
    signal_type: str,
    visibility_delta: int,
    actions: list[str],
) -> str:
    """Generate explanation text for a strategy alert."""
    sig_label = signal_type.replace("_", " ")
    direction = "gained" if visibility_delta > 0 else "changed"
    action_text = actions[0] if actions else "review competitive positioning"
    return (
        f"{competitor_name} {direction} AI visibility after {sig_label}. "
        f"Recommended: {action_text}."
    )


def generate_strategy_alerts(
    db: Session,
    workspace_id: str,
) -> int:
    """
    Generate strategy alert insights from existing ai_impact insights.
    Only creates alerts for insights with positive delta and sufficient confidence.
    Returns count of strategy alerts created.
    """
    # Get ai_impact insights with positive visibility delta
    impact_insights = (
        db.query(AIImpactInsight)
        .filter(
            AIImpactInsight.workspace_id == workspace_id,
            AIImpactInsight.insight_type == InsightType.AI_IMPACT.value,
            AIImpactInsight.visibility_delta > 0,
            AIImpactInsight.correlation_confidence >= CONFIDENCE_THRESHOLD,
        )
        .all()
    )

    if not impact_insights:
        return 0

    # Build competitor name lookup
    comp_ids = {i.competitor_id for i in impact_insights}
    comps = db.query(Competitor).filter(Competitor.id.in_(comp_ids)).all() if comp_ids else []
    comp_map = {str(c.id): c.name for c in comps}

    alerts_created = 0
    seen_keys: set[str] = set()

    for insight in impact_insights:
        comp_name = comp_map.get(str(insight.competitor_id), "Unknown")
        signal_type = insight.signal_type or "website_change"

        # Deduplicate: one alert per competitor × signal_type
        dedup_key = f"{insight.competitor_id}:{signal_type}"
        if dedup_key in seen_keys:
            continue
        seen_keys.add(dedup_key)

        actions = _get_strategy_actions(signal_type, comp_name, insight.prompt_text or "")
        explanation = _generate_strategy_explanation(
            comp_name, signal_type, insight.visibility_delta or 0, actions,
        )

        # Compute priority — strategy alerts are typically P1 (actionable)
        priority = PriorityLevel.P1.value if (insight.impact_score or 0) >= 30 else PriorityLevel.P2.value

        db.add(AIImpactInsight(
            workspace_id=workspace_id,
            competitor_id=insight.competitor_id,
            insight_type=InsightType.AI_STRATEGY_ALERT.value,
            signal_type=signal_type,
            signal_title=insight.signal_title,
            signal_timestamp=insight.signal_timestamp,
            signal_event_id=insight.signal_event_id,
            prompt_text=insight.prompt_text,
            tracked_prompt_id=insight.tracked_prompt_id,
            visibility_before=insight.visibility_before,
            visibility_after=insight.visibility_after,
            visibility_delta=insight.visibility_delta,
            engines_affected=insight.engines_affected,
            citations=insight.citations,
            impact_score=insight.impact_score,
            priority_level=priority,
            correlation_confidence=insight.correlation_confidence,
            explanation=explanation,
            reasoning=f"Strategy alert generated from AI Impact Insight. {comp_name} showed increased visibility after {signal_type.replace('_', ' ')}.",
            short_title=f"Strategy: {comp_name} — {signal_type.replace('_', ' ').title()}",
            signal_headline=insight.signal_headline,
            confidence_factors=insight.confidence_factors,
            prompt_relevance_score=insight.prompt_relevance_score,
            strategy_actions=actions,
            prompt_cluster_name=insight.prompt_cluster_name,
        ))
        alerts_created += 1

    return alerts_created
