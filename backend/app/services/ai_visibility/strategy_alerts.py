"""
AI Competitive Strategy Alerts — converts insights into recommended actions.

Generates strategy alert insights when:
- An AI Impact Insight exists with positive visibility delta
- Confidence >= threshold
- Maps signal_type to concrete recommended actions

PROMPT-12: Enhanced with category-awareness, citation-awareness,
and AI-answer-optimization-focused actions instead of generic marketing.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.models import (
    AIImpactInsight,
    AITrackedPrompt,
    Competitor,
    InsightType,
    PriorityLevel,
    PromptCategory,
    PromptEngineCitation,
)

logger = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = 50.0

# Signal type → recommended strategy actions (AI-answer-optimization focused)
STRATEGY_MAP: dict[str, list[str]] = {
    "integration_added": [
        "Publish content targeting \"{prompt}\" with integration comparisons",
        "Create documentation showing your integration ecosystem vs {competitor}",
        "Target prompt variations: 'best {category} integrations'",
    ],
    "landing_page_created": [
        "Create competing content optimized for \"{prompt}\"",
        "Publish comparison page: your product vs {competitor}",
        "Add structured data to help AI engines find your content",
    ],
    "positioning_change": [
        "Update product pages to counter {competitor}'s new positioning",
        "Publish a positioning comparison targeting \"{prompt}\"",
        "Create FAQ content addressing {competitor}'s claims",
    ],
    "funding": [
        "Publish thought leadership content about \"{prompt}\" to maintain authority",
        "Highlight your track record and stability vs {competitor}",
        "Create 'why choose us over {competitor}' content targeting \"{prompt}\"",
    ],
    "pricing_change": [
        "Update pricing comparison targeting \"{prompt}\"",
        "Publish value-based content showing ROI vs {competitor}",
        "Target prompt variations: 'best affordable {category}'",
    ],
    "feature_launch": [
        "Add feature comparison content targeting \"{prompt}\"",
        "Publish response content highlighting your strengths vs {competitor}",
        "Create technical documentation referenced by AI engines",
    ],
    "product_change": [
        "Update feature comparison documentation for \"{prompt}\"",
        "Create competitive analysis content that AI engines can cite",
        "Brief sales team on {competitor}'s changes",
    ],
    "blog_post": [
        "Publish competing thought leadership targeting \"{prompt}\"",
        "Create response content that outranks {competitor} in AI answers",
        "Update content calendar to address topic",
    ],
    "hiring": [
        "Highlight your team's expertise in content targeting \"{prompt}\"",
        "Create content about your engineering capabilities vs {competitor}",
        "Publish hiring-related thought leadership",
    ],
    "website_change": [
        "Review and update your content targeting \"{prompt}\"",
        "Analyze {competitor}'s new positioning and counter with content",
        "Update competitive intelligence brief",
    ],
}

DEFAULT_ACTIONS = [
    "Review {competitor}'s recent changes and their impact on \"{prompt}\"",
    "Update competitive content documentation",
    "Create AI-engine-optimized content targeting \"{prompt}\"",
]


def _get_strategy_actions(
    signal_type: str,
    competitor_name: str,
    prompt_text: str,
    category_name: str | None = None,
    citation_domains: list[str] | None = None,
) -> list[str]:
    """Get recommended strategy actions for a signal type, enriched with context."""
    actions = STRATEGY_MAP.get(signal_type, DEFAULT_ACTIONS)
    # Derive category from either the real category or the prompt text
    category = category_name or prompt_text.replace("best ", "").replace("top ", "").strip()

    result = []
    for action in actions:
        personalized = action.replace("{competitor}", competitor_name)
        personalized = personalized.replace("{category}", category)
        personalized = personalized.replace("{prompt}", prompt_text or "")
        result.append(personalized)

    # Add citation-aware action if citation sources are available
    if citation_domains and len(citation_domains) >= 1:
        top = ", ".join(citation_domains[:2])
        result.append(
            f"Get your content cited on influential sources ({top}) to compete with {competitor_name}"
        )

    # Add category-aware action if category exists
    if category_name:
        result.append(
            f"Target prompt variations across the \"{category_name}\" category to build category ownership"
        )

    return result


def _generate_strategy_explanation(
    competitor_name: str,
    signal_type: str,
    visibility_delta: int,
    prompt_text: str,
    category_name: str | None,
    actions: list[str],
) -> str:
    """Generate explanation text for a strategy alert."""
    sig_label = signal_type.replace("_", " ")
    direction = "gained" if visibility_delta > 0 else "changed"
    action_text = actions[0] if actions else "review competitive positioning"
    parts = [f"{competitor_name} {direction} AI visibility after {sig_label}."]
    if prompt_text:
        parts.append(f'Prompt: "{prompt_text}".')
    if category_name:
        parts.append(f"Category: {category_name}.")
    parts.append(f"Recommended: {action_text}.")
    return " ".join(parts)


def generate_strategy_alerts(
    db: Session,
    workspace_id: str,
) -> int:
    """
    Generate strategy alert insights from existing ai_impact insights.
    Only creates alerts for insights with positive delta and sufficient confidence.
    P12: Enriched with category context and citation domains.
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

    # P12: Build category lookup for tracked prompts
    tp_ids = {i.tracked_prompt_id for i in impact_insights if i.tracked_prompt_id}
    cat_map: dict[str, str] = {}  # tracked_prompt_id -> category_name
    if tp_ids:
        tps = db.query(AITrackedPrompt).filter(AITrackedPrompt.id.in_(tp_ids)).all()
        cat_ids = {tp.category_id for tp in tps if tp.category_id}
        if cat_ids:
            cats = db.query(PromptCategory).filter(PromptCategory.id.in_(cat_ids)).all()
            cat_name_map = {str(c.id): c.category_name for c in cats}
            for tp in tps:
                if tp.category_id and str(tp.category_id) in cat_name_map:
                    cat_map[str(tp.id)] = cat_name_map[str(tp.category_id)]

    # P12: Build citation domain lookup per competitor
    cit_domains: dict[str, list[str]] = {}
    cit_rows = (
        db.query(PromptEngineCitation.competitor_id, PromptEngineCitation.citation_domain)
        .filter(PromptEngineCitation.workspace_id == workspace_id)
        .distinct()
        .limit(200)
        .all()
    )
    for row in cit_rows:
        if row.competitor_id and row.citation_domain:
            cit_domains.setdefault(str(row.competitor_id), []).append(row.citation_domain)

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

        # P12: Get category context
        category_name = cat_map.get(str(insight.tracked_prompt_id)) if insight.tracked_prompt_id else None

        # P12: Get citation domains for this competitor
        comp_cit_domains = cit_domains.get(str(insight.competitor_id), [])

        actions = _get_strategy_actions(
            signal_type, comp_name, insight.prompt_text or "",
            category_name=category_name,
            citation_domains=comp_cit_domains[:3],
        )
        explanation = _generate_strategy_explanation(
            comp_name, signal_type, insight.visibility_delta or 0,
            insight.prompt_text or "", category_name, actions,
        )

        # Compute priority — strategy alerts are typically P1 (actionable)
        priority = PriorityLevel.P1.value if (insight.impact_score or 0) >= 30 else PriorityLevel.P2.value

        # P12: Include category_data when category is available
        cat_data = {"category_name": category_name} if category_name else None

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
            reasoning=(
                f"Strategy alert generated from AI Impact Insight. "
                f"{comp_name} showed increased visibility after {signal_type.replace('_', ' ')}."
                + (f" Category: {category_name}." if category_name else "")
            ),
            short_title=f"Strategy: {comp_name} — {signal_type.replace('_', ' ').title()}",
            signal_headline=insight.signal_headline,
            confidence_factors=insight.confidence_factors,
            prompt_relevance_score=insight.prompt_relevance_score,
            strategy_actions=actions,
            prompt_cluster_name=insight.prompt_cluster_name,
            category_data=cat_data,
        ))
        alerts_created += 1

    return alerts_created
