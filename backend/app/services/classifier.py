from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.core.llm_client import get_llm_client
from app.models.models import ChangeCategory, PageType
from app.services.differ import DiffResult

logger = logging.getLogger(__name__)

# ── Rule-based classification (runs first, no LLM cost) ──

KEYWORD_RULES: dict[ChangeCategory, list[str]] = {
    ChangeCategory.PRICING_CHANGE: [
        "$", "€", "£", "/mo", "/month", "/year", "/yr", "per month", "per year",
        "billed annually", "billed monthly", "free trial", "price",
    ],
    ChangeCategory.PLAN_RESTRUCTURE: [
        "starter", "pro plan", "enterprise", "business plan", "team plan",
        "free plan", "basic plan", "premium", "tier", "upgrade", "downgrade",
    ],
    ChangeCategory.POSITIONING_HERO: [
        "the #1", "leading", "best-in-class", "all-in-one", "the only",
        "built for", "designed for", "reimagine", "transform", "future of",
    ],
    ChangeCategory.CTA_CHANGE: [
        "get started", "sign up", "book a demo", "start free", "try for free",
        "request demo", "talk to sales", "start trial", "join now",
    ],
    ChangeCategory.FEATURE_CLAIM: [
        "new feature", "now available", "introducing", "announcing",
        "integration with", "supports", "compatible with", "powered by",
    ],
    ChangeCategory.NEW_ALTERNATIVES_CONTENT: [
        "vs ", "versus", "alternative to", "compared to", "competitor",
        "switch from", "migrate from", "better than",
    ],
}


@dataclass
class ClassificationResult:
    categories: list[str]
    severity: str
    ai_summary: str
    ai_why_it_matters: str
    ai_next_moves: str
    ai_battlecard_block: str
    ai_sales_talk_track: str
    raw_llm_response: dict[str, Any] | None = None
    used_llm: bool = False


def classify_with_rules(diff_result: DiffResult, page_type: PageType) -> list[ChangeCategory]:
    """Fast rule-based classification using keyword matching."""
    all_changed_text = " ".join(diff_result.additions + diff_result.removals).lower()
    matched: list[ChangeCategory] = []

    for category, keywords in KEYWORD_RULES.items():
        for kw in keywords:
            if kw.lower() in all_changed_text:
                matched.append(category)
                break

    # Page type heuristic: pricing page changes are very likely pricing-related
    if page_type == PageType.PRICING and ChangeCategory.PRICING_CHANGE not in matched:
        matched.append(ChangeCategory.PRICING_CHANGE)
    if page_type == PageType.HOME_HERO and ChangeCategory.POSITIONING_HERO not in matched:
        matched.append(ChangeCategory.POSITIONING_HERO)
    if page_type == PageType.ALTERNATIVES and ChangeCategory.NEW_ALTERNATIVES_CONTENT not in matched:
        matched.append(ChangeCategory.NEW_ALTERNATIVES_CONTENT)

    if not matched:
        matched.append(ChangeCategory.OTHER)

    return matched


def classify_change(
    diff_result: DiffResult,
    page_type: PageType,
    before_text: str,
    after_text: str,
) -> ClassificationResult:
    """
    Classify a meaningful diff:
    1. Run rule-based classification first.
    2. Call LLM for rich insights (summary, why it matters, next moves, etc.).
    """
    rule_categories = classify_with_rules(diff_result, page_type)

    # Build diff summary for LLM
    diff_summary = "\n".join(diff_result.raw_diff_lines[:200])  # cap context

    system_prompt = (
        "You are a competitive intelligence analyst for a SaaS company. "
        "You analyze changes on competitor websites and produce actionable insights."
    )

    user_prompt = f"""A competitor's **{page_type.value}** page has changed.

--- REMOVED TEXT ---
{chr(10).join(diff_result.removals[:50])}

--- ADDED TEXT ---
{chr(10).join(diff_result.additions[:50])}

--- DIFF ---
{diff_summary}

Rule-based categories detected: {[c.value for c in rule_categories]}

Respond in JSON with these exact keys:
{{
  "categories": ["pricing_change", ...],
  "severity": "low|medium|high|critical",
  "summary": "1-2 sentences: what specifically changed",
  "why_it_matters": "Strategic implication for us",
  "next_moves": "2-3 concrete recommended actions",
  "battlecard_block": "Drop-in competitive snippet for sales team",
  "sales_talk_track": "How to position against this change in a sales call"
}}"""

    try:
        llm = get_llm_client()
        llm_response = llm.chat_json(system_prompt, user_prompt)

        return ClassificationResult(
            categories=llm_response.get("categories", [c.value for c in rule_categories]),
            severity=llm_response.get("severity", "medium"),
            ai_summary=llm_response.get("summary", ""),
            ai_why_it_matters=llm_response.get("why_it_matters", ""),
            ai_next_moves=llm_response.get("next_moves", ""),
            ai_battlecard_block=llm_response.get("battlecard_block", ""),
            ai_sales_talk_track=llm_response.get("sales_talk_track", ""),
            raw_llm_response=llm_response,
            used_llm=True,
        )
    except Exception as exc:
        logger.error("LLM classification failed, falling back to rules only: %s", exc)
        return ClassificationResult(
            categories=[c.value for c in rule_categories],
            severity="medium",
            ai_summary=f"Detected changes: {', '.join(c.value for c in rule_categories)}",
            ai_why_it_matters="LLM unavailable — manual review recommended.",
            ai_next_moves="Review the diff manually and assess impact.",
            ai_battlecard_block="",
            ai_sales_talk_track="",
            raw_llm_response={"error": str(exc)},
            used_llm=False,
        )
