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
    ChangeCategory.POSITIONING_CHANGE: [
        "ai-powered", "platform for", "automation platform", "next-generation",
        "world's first", "fastest", "most powerful", "reimagined",
    ],
    ChangeCategory.INTEGRATION_ADDED: [
        "new integration", "now integrates", "connect with", "works with",
        "marketplace", "app store", "partner",
    ],
    ChangeCategory.INTEGRATION_REMOVED: [
        "removed integration", "no longer supports", "discontinued",
        "deprecated integration",
    ],
    ChangeCategory.LANDING_PAGE_CREATED: [
        "/ai", "/automation", "/enterprise", "/use-cases",
        "/solutions", "/platform", "/product",
    ],
}

# URL patterns for landing page detection
LANDING_PAGE_FOCUS_PATTERNS = [
    "/ai", "/automation", "/enterprise", "/use-cases",
    "/solutions", "/platform", "/product", "/security",
    "/compliance", "/analytics", "/workflow",
]
LANDING_PAGE_IGNORE_PATTERNS = [
    "/blog/", "/docs/", "/help/", "/support/",
    "/careers/", "/jobs/", "/legal/", "/privacy",
    "/terms", "/sitemap", "/feed", "/rss",
]


# ── Signal type derivation from categories ──

CATEGORY_TO_SIGNAL: dict[str, str] = {
    "pricing_change": "pricing_change",
    "plan_restructure": "pricing_change",
    "positioning_hero": "positioning_change",
    "positioning_change": "positioning_change",
    "cta_change": "website_change",
    "feature_claim": "product_change",
    "new_alternatives_content": "website_change",
    "integration_added": "integration_added",
    "integration_removed": "integration_removed",
    "landing_page_created": "landing_page_created",
    "other": "website_change",
}


def derive_signal_type(categories: list[str]) -> str:
    """Derive the primary signal_type from a list of change categories."""
    priority = [
        "positioning_change", "pricing_change", "integration_added",
        "integration_removed", "landing_page_created", "plan_restructure",
        "feature_claim", "positioning_hero", "cta_change",
        "new_alternatives_content", "other",
    ]
    for cat in priority:
        if cat in categories:
            return CATEGORY_TO_SIGNAL.get(cat, "website_change")
    return "website_change"


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

    # Page type heuristics
    if page_type == PageType.PRICING and ChangeCategory.PRICING_CHANGE not in matched:
        matched.append(ChangeCategory.PRICING_CHANGE)
    if page_type == PageType.HOME_HERO:
        if ChangeCategory.POSITIONING_HERO not in matched:
            matched.append(ChangeCategory.POSITIONING_HERO)
        if ChangeCategory.POSITIONING_CHANGE not in matched:
            matched.append(ChangeCategory.POSITIONING_CHANGE)
    if page_type == PageType.ALTERNATIVES and ChangeCategory.NEW_ALTERNATIVES_CONTENT not in matched:
        matched.append(ChangeCategory.NEW_ALTERNATIVES_CONTENT)
    if page_type == PageType.INTEGRATIONS:
        if ChangeCategory.INTEGRATION_ADDED not in matched and ChangeCategory.INTEGRATION_REMOVED not in matched:
            if diff_result.additions:
                matched.append(ChangeCategory.INTEGRATION_ADDED)
            if diff_result.removals:
                matched.append(ChangeCategory.INTEGRATION_REMOVED)
    if page_type == PageType.LANDING:
        if ChangeCategory.POSITIONING_CHANGE not in matched:
            matched.append(ChangeCategory.POSITIONING_CHANGE)

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

Available categories:
- pricing_change: pricing/cost changes
- plan_restructure: plan tier changes
- positioning_hero: hero headline/tagline changes
- positioning_change: strategic messaging/copy changes (headlines, subheadlines, feature descriptions, NOT layout)
- cta_change: call-to-action changes
- feature_claim: new feature announcements
- new_alternatives_content: competitor comparison content
- integration_added: new integrations or partnerships added
- integration_removed: integrations removed or deprecated
- landing_page_created: new strategic landing page detected
- other: doesn't fit above

IMPORTANT: Distinguish between UI/layout changes (classify as "other" with low severity) and semantic messaging changes (classify as "positioning_change" or relevant category).

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
