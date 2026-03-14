"""
AI Citation Influence Intelligence — identifies which content sources
influence AI engine recommendations for a competitor.

Aggregates citation frequency across engines and computes influence scores.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone, timedelta

from sqlalchemy.orm import Session
from sqlalchemy import func as sa_func

from app.models.models import (
    AIImpactInsight,
    AIVisibilityEvent,
    Competitor,
    InsightType,
    PriorityLevel,
    PromptEngineCitation,
)

logger = logging.getLogger(__name__)

# Weight per engine — engines with more authority have higher weight
ENGINE_WEIGHTS: dict[str, float] = {
    "chatgpt": 1.2,
    "perplexity": 1.3,  # Perplexity is citation-heavy
    "claude": 1.0,
    "gemini": 1.0,
}

MIN_CITATIONS_FOR_INSIGHT = 2  # Need at least 2 citations to generate an influence insight


def compute_citation_influence(
    db: Session,
    workspace_id: str,
    days: int = 7,
) -> dict[str, list[dict]]:
    """
    Compute citation influence scores per competitor.

    Returns: {competitor_id: [{domain, url, score, engines, count}, ...]}
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)

    citations = (
        db.query(PromptEngineCitation)
        .filter(
            PromptEngineCitation.workspace_id == workspace_id,
            PromptEngineCitation.created_at >= since,
        )
        .all()
    )

    if not citations:
        return {}

    # Aggregate: competitor_id -> domain -> {count, engines, urls}
    influence: dict[str, dict[str, dict]] = defaultdict(lambda: defaultdict(
        lambda: {"count": 0, "engines": set(), "urls": set()}
    ))

    for cit in citations:
        comp_key = str(cit.competitor_id) if cit.competitor_id else "_unmatched"
        domain = cit.citation_domain or "unknown"
        influence[comp_key][domain]["count"] += 1
        influence[comp_key][domain]["engines"].add(cit.engine)
        influence[comp_key][domain]["urls"].add(cit.citation_url)

    # Compute scores
    result: dict[str, list[dict]] = {}
    for comp_id, domains in influence.items():
        sources = []
        for domain, data in domains.items():
            engine_weight = sum(ENGINE_WEIGHTS.get(e, 1.0) for e in data["engines"])
            score = round(data["count"] * engine_weight, 1)
            sources.append({
                "domain": domain,
                "url": sorted(data["urls"])[0] if data["urls"] else "",
                "score": score,
                "engines": sorted(data["engines"]),
                "count": data["count"],
            })
        sources.sort(key=lambda x: x["score"], reverse=True)
        result[comp_id] = sources[:10]  # Top 10 sources

    return result


def generate_citation_influence_insights(
    db: Session,
    workspace_id: str,
    days: int = 7,
) -> int:
    """
    Generate citation influence insights for competitors that have enough citation data.
    Returns count of insights created.
    """
    influence_data = compute_citation_influence(db, workspace_id, days)

    if not influence_data:
        return 0

    competitors = (
        db.query(Competitor)
        .filter(Competitor.workspace_id == workspace_id, Competitor.is_active == True)
        .all()
    )
    comp_map = {str(c.id): c for c in competitors}

    insights_created = 0
    for comp_id, sources in influence_data.items():
        if comp_id == "_unmatched" or comp_id not in comp_map:
            continue

        if len(sources) < MIN_CITATIONS_FOR_INSIGHT:
            continue

        comp = comp_map[comp_id]
        top_domains = [s["domain"] for s in sources[:5]]
        total_score = sum(s["score"] for s in sources)

        all_engines = sorted({e for s in sources for e in s["engines"]})
        top3 = ", ".join(top_domains[:3])

        explanation = (
            f"{comp.name} is cited through {len(sources)} source(s) across "
            f"{len(all_engines)} AI engine(s). "
            f"Top sources: {top3}."
        )

        # P12: Build a more descriptive short_title with top domains
        short_title = f"Citation Influence: {comp.name} — {top3}"

        db.add(AIImpactInsight(
            workspace_id=workspace_id,
            competitor_id=comp.id,
            insight_type=InsightType.AI_CITATION_INFLUENCE.value,
            signal_type="ai_citation_influence",
            signal_title=f"Citation sources influencing AI answers about {comp.name}",
            visibility_before=0,
            visibility_after=len(sources),
            visibility_delta=len(sources),
            engines_affected=all_engines,
            impact_score=min(total_score * 2, 80.0),
            priority_level=PriorityLevel.P2.value,
            correlation_confidence=min(total_score * 3, 90.0),
            explanation=explanation,
            reasoning=(
                f"Citation influence analysis found {len(sources)} unique source(s) "
                f"influencing AI recommendations about {comp.name}. "
                f"Top domains: {top3}."
            ),
            short_title=short_title,
            influential_sources=sources,
        ))
        insights_created += 1

    return insights_created
