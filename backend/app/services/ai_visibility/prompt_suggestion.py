"""
Prompt Suggestion Service — generates prompt suggestions from 5 sources.

Sources:
1. Manual — user-entered prompts
2. Competitor — generated from competitor names
3. Keyword — from user/auto-extracted keywords
4. Template — system templates applied to keywords/competitors
5. Category — from workspace category (if set)
"""

from __future__ import annotations

import logging
from typing import List

from sqlalchemy.orm import Session

from app.models.models import (
    AIPromptSource,
    AIWorkspaceKeyword,
    Competitor,
    PromptSourceType,
    PromptStatusEnum,
)

logger = logging.getLogger(__name__)

# System-defined prompt templates
KEYWORD_TEMPLATES = [
    "best {keyword} tools",
    "top {keyword} software",
    "{keyword} platforms",
    "{keyword} tools for businesses",
]

COMPETITOR_TEMPLATES = [
    "alternatives to {competitor}",
    "tools like {competitor}",
    "{competitor} competitors",
    "{competitor} vs",
]


def _upsert_suggestion(
    db: Session,
    workspace_id: str,
    prompt_text: str,
    source_type: str,
    source_detail: dict | None = None,
) -> bool:
    """Insert suggestion if not already present. Returns True if created."""
    prompt_text = prompt_text.strip().lower()
    if not prompt_text or len(prompt_text) < 5:
        return False

    existing = (
        db.query(AIPromptSource)
        .filter(
            AIPromptSource.workspace_id == workspace_id,
            AIPromptSource.prompt_text == prompt_text,
        )
        .first()
    )
    if existing:
        return False

    db.add(AIPromptSource(
        workspace_id=workspace_id,
        prompt_text=prompt_text,
        source_type=source_type,
        source_detail=source_detail,
        status=PromptStatusEnum.SUGGESTED.value,
    ))
    return True


def generate_competitor_suggestions(db: Session, workspace_id: str) -> int:
    """Generate prompt suggestions from competitor names."""
    competitors = (
        db.query(Competitor)
        .filter(Competitor.workspace_id == workspace_id, Competitor.is_active == True)
        .all()
    )
    created = 0
    for comp in competitors:
        for tmpl in COMPETITOR_TEMPLATES:
            text = tmpl.format(competitor=comp.name)
            if _upsert_suggestion(db, workspace_id, text, PromptSourceType.COMPETITOR.value,
                                  {"competitor_id": str(comp.id), "competitor_name": comp.name, "template": tmpl}):
                created += 1
    return created


def generate_keyword_suggestions(db: Session, workspace_id: str) -> int:
    """Generate prompt suggestions from approved keywords."""
    keywords = (
        db.query(AIWorkspaceKeyword)
        .filter(
            AIWorkspaceKeyword.workspace_id == workspace_id,
            AIWorkspaceKeyword.is_approved == True,
        )
        .all()
    )
    created = 0
    for kw in keywords:
        for tmpl in KEYWORD_TEMPLATES:
            text = tmpl.format(keyword=kw.keyword)
            if _upsert_suggestion(db, workspace_id, text, PromptSourceType.KEYWORD.value,
                                  {"keyword": kw.keyword, "template": tmpl}):
                created += 1
    return created


def generate_template_suggestions(db: Session, workspace_id: str) -> int:
    """Generate prompt suggestions using templates applied to both keywords and competitors."""
    created = 0

    # Keywords × keyword templates
    keywords = (
        db.query(AIWorkspaceKeyword)
        .filter(AIWorkspaceKeyword.workspace_id == workspace_id, AIWorkspaceKeyword.is_approved == True)
        .all()
    )
    for kw in keywords:
        for tmpl in KEYWORD_TEMPLATES:
            text = tmpl.format(keyword=kw.keyword)
            if _upsert_suggestion(db, workspace_id, text, PromptSourceType.TEMPLATE.value,
                                  {"keyword": kw.keyword, "template": tmpl}):
                created += 1

    # Competitors × competitor templates
    competitors = (
        db.query(Competitor)
        .filter(Competitor.workspace_id == workspace_id, Competitor.is_active == True)
        .all()
    )
    for comp in competitors:
        for tmpl in COMPETITOR_TEMPLATES:
            text = tmpl.format(competitor=comp.name)
            if _upsert_suggestion(db, workspace_id, text, PromptSourceType.TEMPLATE.value,
                                  {"competitor_name": comp.name, "template": tmpl}):
                created += 1

    return created


def generate_all_suggestions(
    db: Session,
    workspace_id: str,
    source_types: List[str] | None = None,
) -> dict:
    """
    Generate prompt suggestions from all requested sources.
    Returns summary of created suggestions.
    """
    by_source: dict[str, int] = {}
    total = 0

    sources = source_types or [
        PromptSourceType.COMPETITOR.value,
        PromptSourceType.KEYWORD.value,
        PromptSourceType.TEMPLATE.value,
    ]

    if PromptSourceType.COMPETITOR.value in sources:
        n = generate_competitor_suggestions(db, workspace_id)
        by_source["competitor"] = n
        total += n

    if PromptSourceType.KEYWORD.value in sources:
        n = generate_keyword_suggestions(db, workspace_id)
        by_source["keyword"] = n
        total += n

    if PromptSourceType.TEMPLATE.value in sources:
        n = generate_template_suggestions(db, workspace_id)
        by_source["template"] = n
        total += n

    if total > 0:
        db.commit()

    return {"suggestions_created": total, "by_source": by_source}
