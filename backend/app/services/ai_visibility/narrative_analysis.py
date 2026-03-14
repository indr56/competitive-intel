"""
AI Narrative Analysis — detects how AI engines describe competitors
and identifies positioning shifts in AI-generated responses.

Extracts narrative descriptors from AI engine responses and generates
AI_NARRATIVE insights when competitors are consistently described
with specific positioning language.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from datetime import datetime, timezone, timedelta

from sqlalchemy.orm import Session
from sqlalchemy import func as sa_func

from app.models.models import (
    AIEngineResult,
    AIImpactInsight,
    AIPromptRun,
    AITrackedPrompt,
    AIVisibilityEvent,
    Competitor,
    InsightType,
    PriorityLevel,
    RunStatusEnum,
)
from app.services.ai_visibility.prompt_execution import normalize_prompt

logger = logging.getLogger(__name__)

# Minimum occurrences of a descriptor to generate an insight
MIN_DESCRIPTOR_COUNT = 2

# Common filler phrases to exclude
FILLER_PHRASES = {
    "a tool", "an app", "a platform", "a service", "a product",
    "a company", "a solution", "one of the", "known for",
}


def _extract_descriptors(text: str, brand_name: str) -> list[str]:
    """
    Extract narrative descriptors for a brand from AI response text.
    Looks for patterns like:
      - "Brand is [descriptor]"
      - "Brand, [descriptor],"
      - "Brand — [descriptor]"
      - "[descriptor] like Brand"
    """
    if not text or not brand_name:
        return []

    descriptors = []
    text_lower = text.lower()
    brand_lower = brand_name.lower()

    # Also try core brand (first word)
    core_brand = brand_lower.split()[0] if brand_lower else brand_lower

    for name in {brand_lower, core_brand}:
        if not name or len(name) < 2:
            continue

        # Pattern: "Brand is/are [descriptor]"
        for pattern in [
            rf'{re.escape(name)}\s+is\s+(?:a|an|the)?\s*([^.,:;]{{5,60}})',
            rf'{re.escape(name)}\s+are\s+(?:a|an|the)?\s*([^.,:;]{{5,60}})',
            rf'{re.escape(name)},?\s+(?:a|an|the)\s+([^.,:;]{{5,60}})',
            rf'(?:best|top|leading|popular)\s+([^.,:;]{{5,40}})\s+(?:like|such as)\s+{re.escape(name)}',
        ]:
            matches = re.findall(pattern, text_lower)
            for m in matches:
                desc = m.strip().rstrip(".")
                if len(desc) >= 5 and desc not in FILLER_PHRASES:
                    descriptors.append(desc)

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for d in descriptors:
        if d not in seen:
            seen.add(d)
            unique.append(d)

    return unique[:5]  # Limit to top 5 per response


def generate_narrative_insights(
    db: Session,
    workspace_id: str,
    days: int = 7,
) -> int:
    """
    Analyze AI engine responses for narrative descriptors about competitors.
    Generates AI_NARRATIVE insights when patterns are detected.
    Returns count of insights created.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)

    competitors = (
        db.query(Competitor)
        .filter(Competitor.workspace_id == workspace_id, Competitor.is_active == True)
        .all()
    )
    if not competitors:
        return 0

    tracked_prompts = (
        db.query(AITrackedPrompt)
        .filter(
            AITrackedPrompt.workspace_id == workspace_id,
            AITrackedPrompt.is_active == True,
        )
        .all()
    )
    if not tracked_prompts:
        return 0

    insights_created = 0

    for comp in competitors:
        # Gather all recent AI responses that mention this competitor
        descriptor_counts: dict[str, int] = defaultdict(int)
        descriptor_engines: dict[str, set] = defaultdict(set)
        total_responses_checked = 0

        for tp in tracked_prompts:
            norm = normalize_prompt(tp.prompt_text)

            # Check if competitor is mentioned for this prompt
            mentioned = (
                db.query(AIVisibilityEvent)
                .filter(
                    AIVisibilityEvent.workspace_id == workspace_id,
                    AIVisibilityEvent.competitor_id == comp.id,
                    AIVisibilityEvent.tracked_prompt_id == tp.id,
                    AIVisibilityEvent.mentioned == True,
                    AIVisibilityEvent.event_date >= since,
                )
                .first()
            )
            if not mentioned:
                continue

            # Get engine results for this prompt
            runs = (
                db.query(AIPromptRun)
                .filter(
                    AIPromptRun.normalized_text == norm,
                    AIPromptRun.run_date >= since,
                    AIPromptRun.status == RunStatusEnum.COMPLETED.value,
                )
                .all()
            )

            for run in runs:
                results = (
                    db.query(AIEngineResult)
                    .filter(
                        AIEngineResult.prompt_run_id == run.id,
                        AIEngineResult.status == RunStatusEnum.COMPLETED.value,
                    )
                    .all()
                )

                for er in results:
                    if not er.raw_response:
                        continue
                    total_responses_checked += 1
                    descriptors = _extract_descriptors(er.raw_response, comp.name)
                    for desc in descriptors:
                        descriptor_counts[desc] += 1
                        descriptor_engines[desc].add(er.engine)

        if not descriptor_counts:
            continue

        # Find the most common descriptor
        sorted_descs = sorted(descriptor_counts.items(), key=lambda x: x[1], reverse=True)
        top_desc, top_count = sorted_descs[0]

        if top_count < MIN_DESCRIPTOR_COUNT:
            continue

        engine_count = len(descriptor_engines.get(top_desc, set()))
        engines_list = sorted(descriptor_engines.get(top_desc, set()))

        # Priority based on frequency and engine spread
        if top_count >= 4 and engine_count >= 3:
            priority = PriorityLevel.P1.value
        elif top_count >= 3 or engine_count >= 2:
            priority = PriorityLevel.P2.value
        else:
            priority = PriorityLevel.P3.value

        # Build top descriptors summary
        top_descriptors = [
            {"descriptor": d, "count": c, "engines": sorted(descriptor_engines[d])}
            for d, c in sorted_descs[:5]
        ]

        db.add(AIImpactInsight(
            workspace_id=workspace_id,
            competitor_id=comp.id,
            insight_type=InsightType.AI_NARRATIVE.value,
            signal_type="ai_narrative",
            signal_title=f'{comp.name} is described as "{top_desc}" across AI engines',
            prompt_text=f"Across {total_responses_checked} AI responses",
            visibility_before=0,
            visibility_after=top_count,
            visibility_delta=top_count,
            engines_affected=engines_list,
            impact_score=round(min(top_count * 15 + engine_count * 10, 85), 1),
            priority_level=priority,
            correlation_confidence=min(top_count * 20 + engine_count * 15, 95.0),
            explanation=(
                f'{comp.name} is increasingly described as "{top_desc}" '
                f"across {engine_count} AI engine{'s' if engine_count != 1 else ''}. "
                f"Found {top_count} occurrences in recent AI responses."
            ),
            reasoning=(
                f"Narrative analysis detected consistent positioning language for {comp.name}. "
                f'The descriptor "{top_desc}" appeared {top_count} times across {engines_list}. '
                f"This suggests AI engines are converging on this market positioning."
            ),
            short_title=f'Narrative: {comp.name} → "{top_desc}"',
            category_data={
                "descriptors": top_descriptors,
                "total_responses": total_responses_checked,
            },
        ))
        insights_created += 1

    return insights_created
