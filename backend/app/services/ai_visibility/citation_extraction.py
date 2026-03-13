"""
Citation Extraction Service — extracts citation URLs from AI engine responses.

Parses raw AI engine responses to find URLs, domains, and surrounding context.
Stores results in the prompt_engine_citations table.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse
from typing import List

from sqlalchemy.orm import Session

from app.models.models import (
    AIEngineResult,
    AIPromptRun,
    Competitor,
    PromptEngineCitation,
)

logger = logging.getLogger(__name__)

# URL regex — matches http/https URLs
_URL_PATTERN = re.compile(r'https?://[^\s\)\]\"\'>]+')

# Domain-like pattern (e.g., "cursor.sh", "github.com/cursor")
_DOMAIN_PATTERN = re.compile(
    r'(?<!\w)([a-zA-Z0-9][-a-zA-Z0-9]*\.'
    r'(?:com|org|net|io|sh|dev|ai|co|app|tech|cloud|us|uk|de|fr|ca|au|in|blog)'
    r'(?:/[^\s\)\]\"\'>]*)?)'
)


def _extract_domain(url: str) -> str:
    """Extract the domain from a URL string."""
    try:
        if url.startswith("http"):
            parsed = urlparse(url)
            return parsed.netloc.lower().lstrip("www.")
        # Bare domain like "cursor.sh/blog"
        parts = url.split("/")
        return parts[0].lower().lstrip("www.")
    except Exception:
        return url.split("/")[0].lower()


def _get_context_around_url(text: str, url: str, window: int = 120) -> str:
    """Get surrounding text around a URL for context."""
    idx = text.find(url)
    if idx == -1:
        return ""
    start = max(0, idx - window)
    end = min(len(text), idx + len(url) + window)
    snippet = text[start:end].strip()
    # Clean up to nearest word boundary
    if start > 0:
        snippet = "…" + snippet[snippet.find(" ") + 1:] if " " in snippet[:20] else "…" + snippet
    if end < len(text):
        last_space = snippet.rfind(" ", -30)
        if last_space > len(snippet) - 40:
            snippet = snippet[:last_space] + "…"
    return snippet


def extract_citations_from_response(raw_response: str) -> list[dict]:
    """
    Extract citation URLs from a raw AI engine response.

    Returns list of dicts: [{url, domain, context}, ...]
    """
    if not raw_response:
        return []

    citations: list[dict] = []
    seen_urls: set[str] = set()

    # 1. Extract full URLs (http/https)
    for match in _URL_PATTERN.finditer(raw_response):
        url = match.group().rstrip(".,;:)")
        if url not in seen_urls:
            seen_urls.add(url)
            citations.append({
                "url": url,
                "domain": _extract_domain(url),
                "context": _get_context_around_url(raw_response, url),
            })

    # 2. Extract bare domain references (e.g., "cursor.sh", "github.com/cursor")
    for match in _DOMAIN_PATTERN.finditer(raw_response):
        domain_url = match.group()
        full_url = f"https://{domain_url}"
        if full_url not in seen_urls and domain_url not in seen_urls:
            seen_urls.add(full_url)
            citations.append({
                "url": full_url,
                "domain": _extract_domain(domain_url),
                "context": _get_context_around_url(raw_response, domain_url),
            })

    return citations


def store_citations_for_workspace(
    db: Session,
    workspace_id: str,
    prompt_run_id: str,
    engine: str,
    citations: list[dict],
    competitor_id: str | None = None,
    rank: int | None = None,
) -> int:
    """
    Store extracted citations in the prompt_engine_citations table.
    Returns count of citations stored.
    """
    stored = 0
    for cit in citations:
        db.add(PromptEngineCitation(
            workspace_id=workspace_id,
            prompt_run_id=prompt_run_id,
            engine=engine,
            competitor_id=competitor_id,
            citation_url=cit["url"],
            citation_domain=cit.get("domain", ""),
            citation_context=cit.get("context", ""),
            rank=rank,
        ))
        stored += 1
    return stored


def extract_and_store_citations(
    db: Session,
    workspace_id: str,
    competitors: list,
    days: int = 7,
) -> int:
    """
    Extract citations from recent engine results and store them.
    Called during the correlation pipeline after prompt runs.
    Returns total citations stored.
    """
    from datetime import datetime, timezone, timedelta

    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)

    # Get recent prompt runs
    runs = (
        db.query(AIPromptRun)
        .filter(AIPromptRun.run_date >= since)
        .all()
    )

    # Build competitor domain lookup for matching
    comp_domains = {}
    for c in competitors:
        domain = c.domain.lower().replace("www.", "")
        comp_domains[domain] = str(c.id)
        # Also add common variations
        base = domain.split(".")[0]
        comp_domains[base] = str(c.id)

    total_stored = 0
    for run in runs:
        results = (
            db.query(AIEngineResult)
            .filter(
                AIEngineResult.prompt_run_id == run.id,
                AIEngineResult.raw_response != None,
            )
            .all()
        )

        for result in results:
            # Check if we already extracted citations for this result
            existing = (
                db.query(PromptEngineCitation)
                .filter(
                    PromptEngineCitation.workspace_id == workspace_id,
                    PromptEngineCitation.prompt_run_id == run.id,
                    PromptEngineCitation.engine == result.engine,
                )
                .first()
            )
            if existing:
                continue

            citations = extract_citations_from_response(result.raw_response)

            # Try to match citations to competitors
            for cit in citations:
                matched_comp_id = None
                domain = cit.get("domain", "")
                for comp_domain, comp_id in comp_domains.items():
                    if comp_domain in domain or domain in comp_domain:
                        matched_comp_id = comp_id
                        break

                # Get rank from ranking_data if available
                rank = None
                if result.ranking_data:
                    for rd in result.ranking_data:
                        if matched_comp_id and rd.get("brand"):
                            rank = rd.get("position")
                            break

                db.add(PromptEngineCitation(
                    workspace_id=workspace_id,
                    prompt_run_id=run.id,
                    engine=result.engine,
                    competitor_id=matched_comp_id,
                    citation_url=cit["url"],
                    citation_domain=cit.get("domain", ""),
                    citation_context=cit.get("context", ""),
                    rank=rank,
                ))
                total_stored += 1

    return total_stored
