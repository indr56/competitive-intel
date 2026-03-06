"""Generate AI analysis (summary + implications) for CompetitorEvents."""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models.models import CompetitorEvent, Competitor

logger = logging.getLogger(__name__)

SIGNAL_TYPE_LABELS = {
    "website_change": "Website Change",
    "pricing_change": "Pricing Change",
    "product_change": "Product Change",
    "blog_post": "Blog Post",
    "hiring": "Hiring Signal",
    "funding": "Funding Signal",
    "review": "Review Signal",
    "marketing": "Marketing Signal",
}


def generate_signal_analysis(
    event: CompetitorEvent,
    db: Session,
    competitor_name: Optional[str] = None,
) -> bool:
    """
    Generate ai_summary and ai_implications for a CompetitorEvent using LLM.
    Updates the event in-place and commits.
    Returns True if analysis was generated, False if skipped/failed.
    """
    if event.ai_summary and event.ai_implications:
        return False  # already has analysis

    if not competitor_name:
        comp = db.query(Competitor).filter(Competitor.id == event.competitor_id).first()
        competitor_name = comp.name if comp else "Unknown"

    signal_label = SIGNAL_TYPE_LABELS.get(event.signal_type, event.signal_type)
    metadata_str = ""
    if event.metadata_json:
        metadata_str = "\n".join(f"- {k}: {v}" for k, v in event.metadata_json.items())

    system_prompt = (
        "You are a competitive intelligence analyst for a SaaS company. "
        "You analyze competitor signals and produce actionable strategic insights."
    )

    user_prompt = f"""A competitor signal has been detected:

**Competitor:** {competitor_name}
**Signal Type:** {signal_label}
**Severity:** {event.severity or 'medium'}
**Title:** {event.title}
**Description:** {event.description or 'N/A'}
**Source URL:** {event.source_url or 'N/A'}
{f"**Metadata:**{chr(10)}{metadata_str}" if metadata_str else ""}

Respond in JSON with these exact keys:
{{
  "summary": "2-3 sentence executive summary of this signal and what it means",
  "implications": "2-3 concrete strategic implications and recommended actions for our team. Include specific next steps."
}}"""

    try:
        from app.core.llm_client import get_llm_client

        llm = get_llm_client()
        response = llm.chat_json(system_prompt, user_prompt)

        event.ai_summary = response.get("summary", "")
        event.ai_implications = response.get("implications", "")
        event.is_processed = True
        db.commit()

        logger.info(
            "Generated AI analysis for event %s (%s: %s)",
            event.id, event.signal_type, event.title[:50],
        )
        return True

    except Exception as exc:
        logger.warning(
            "AI analysis generation failed for event %s (non-fatal): %s",
            event.id, exc,
        )
        # Fallback: generate a rule-based summary so the field isn't empty
        event.ai_summary = _fallback_summary(event, competitor_name, signal_label)
        event.ai_implications = _fallback_implications(event, competitor_name, signal_label)
        event.is_processed = True
        db.commit()
        return True


def _fallback_summary(event: CompetitorEvent, competitor_name: str, signal_label: str) -> str:
    """Rule-based fallback summary when LLM is unavailable."""
    sev = (event.severity or "medium").capitalize()
    desc_snippet = f" {event.description[:120]}..." if event.description else ""
    return (
        f"{sev}-severity {signal_label.lower()} detected for {competitor_name}: "
        f"{event.title}.{desc_snippet}"
    )


def _fallback_implications(event: CompetitorEvent, competitor_name: str, signal_label: str) -> str:
    """Rule-based fallback implications when LLM is unavailable."""
    implications = {
        "hiring": (
            f"1. {competitor_name} is actively expanding their team — monitor for new product launches or market expansion.\n"
            f"2. Review our own hiring pipeline to ensure we're competitive for similar talent.\n"
            f"3. Track which roles they're filling to anticipate their strategic direction."
        ),
        "blog_post": (
            f"1. {competitor_name} published new content — review for positioning shifts or feature announcements.\n"
            f"2. Consider creating counter-content to address any claims made.\n"
            f"3. Share with sales team for competitive talking points."
        ),
        "funding": (
            f"1. {competitor_name} has funding activity — expect increased marketing spend and product investment.\n"
            f"2. Update competitive battlecards with this financial intelligence.\n"
            f"3. Brief leadership on potential market impact."
        ),
        "review": (
            f"1. Monitor {competitor_name}'s customer sentiment for weaknesses we can exploit.\n"
            f"2. Update sales materials with relevant review data.\n"
            f"3. Identify dissatisfied customers as potential conversion targets."
        ),
        "marketing": (
            f"1. {competitor_name} has updated their marketing — review for positioning or messaging changes.\n"
            f"2. Assess if our positioning needs adjustment in response.\n"
            f"3. Brief marketing team on competitive messaging shifts."
        ),
    }
    return implications.get(
        event.signal_type,
        f"1. Review this {signal_label.lower()} signal from {competitor_name} for strategic impact.\n"
        f"2. Update competitive intelligence documentation.\n"
        f"3. Share with relevant stakeholders.",
    )
