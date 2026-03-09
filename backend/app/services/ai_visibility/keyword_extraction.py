"""
Keyword Extraction Service — extracts keywords from competitor content.

Sources:
- Homepage text (snapshots)
- Feature pages
- Integration pages
- Landing pages
- Blog titles (competitor events)
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from typing import List

from sqlalchemy.orm import Session

from app.models.models import (
    AIWorkspaceKeyword,
    Competitor,
    CompetitorEvent,
    Snapshot,
    TrackedPage,
)

logger = logging.getLogger(__name__)

# Common stopwords to filter out
STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "it", "that", "this", "was", "are",
    "be", "has", "had", "have", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "can", "not", "no", "so", "if",
    "then", "than", "too", "very", "just", "about", "up", "out", "all",
    "as", "its", "our", "your", "their", "we", "you", "they", "i", "he",
    "she", "my", "his", "her", "us", "them", "what", "which", "who",
    "when", "where", "how", "more", "most", "some", "any", "each",
    "every", "both", "few", "many", "much", "own", "other", "into",
    "over", "after", "before", "between", "under", "again", "here",
    "there", "once", "also", "been", "being", "get", "got", "new",
    "now", "way", "use", "using", "one", "two", "like", "make",
}

# Minimum keyword length
MIN_KW_LEN = 3
MAX_KW_LEN = 60


def _extract_ngrams(text: str, n: int = 2) -> List[str]:
    """Extract n-grams from text."""
    words = re.findall(r'\b[a-z][a-z\-]+\b', text.lower())
    words = [w for w in words if w not in STOPWORDS and len(w) >= MIN_KW_LEN]
    ngrams = []
    for i in range(len(words) - n + 1):
        gram = " ".join(words[i:i + n])
        if len(gram) <= MAX_KW_LEN:
            ngrams.append(gram)
    # Also add single meaningful words (>=5 chars)
    for w in words:
        if len(w) >= 5:
            ngrams.append(w)
    return ngrams


def _score_keywords(ngrams: List[str], min_count: int = 2) -> List[str]:
    """Score and rank keywords by frequency, return top candidates."""
    counts = Counter(ngrams)
    # Filter by minimum count and sort
    scored = [(kw, c) for kw, c in counts.items() if c >= min_count]
    scored.sort(key=lambda x: (-x[1], x[0]))
    return [kw for kw, _ in scored[:50]]  # top 50


def extract_keywords_for_workspace(db: Session, workspace_id: str) -> dict:
    """
    Extract keywords from all competitor content in a workspace.
    Creates AIWorkspaceKeyword records with source='auto_extracted'.
    Returns summary of what was extracted.
    """
    competitors = (
        db.query(Competitor)
        .filter(Competitor.workspace_id == workspace_id, Competitor.is_active == True)
        .all()
    )

    all_ngrams: List[str] = []
    sources_used: dict[str, int] = {}

    for comp in competitors:
        # Extract from tracked page snapshots
        pages = (
            db.query(TrackedPage)
            .filter(TrackedPage.competitor_id == comp.id, TrackedPage.is_active == True)
            .all()
        )
        for page in pages:
            latest_snap = (
                db.query(Snapshot)
                .filter(Snapshot.tracked_page_id == page.id)
                .order_by(Snapshot.captured_at.desc())
                .first()
            )
            if latest_snap and latest_snap.extracted_text:
                ngrams = _extract_ngrams(latest_snap.extracted_text)
                all_ngrams.extend(ngrams)
                src_key = f"page:{page.page_type.value}" if page.page_type else "page:unknown"
                sources_used[src_key] = sources_used.get(src_key, 0) + len(ngrams)

        # Extract from blog post titles
        blog_events = (
            db.query(CompetitorEvent)
            .filter(
                CompetitorEvent.competitor_id == comp.id,
                CompetitorEvent.signal_type == "blog_post",
            )
            .limit(50)
            .all()
        )
        for ev in blog_events:
            if ev.title:
                ngrams = _extract_ngrams(ev.title, n=2)
                all_ngrams.extend(ngrams)
                sources_used["blog_title"] = sources_used.get("blog_title", 0) + len(ngrams)

    # Score and rank
    top_keywords = _score_keywords(all_ngrams, min_count=1)

    created = 0
    for kw in top_keywords:
        existing = (
            db.query(AIWorkspaceKeyword)
            .filter(
                AIWorkspaceKeyword.workspace_id == workspace_id,
                AIWorkspaceKeyword.keyword == kw,
            )
            .first()
        )
        if not existing:
            db.add(AIWorkspaceKeyword(
                workspace_id=workspace_id,
                keyword=kw,
                source="auto_extracted",
                is_approved=False,
                extracted_from="competitor_content",
            ))
            created += 1

    if created:
        db.commit()

    return {
        "keywords_extracted": len(top_keywords),
        "keywords_created": created,
        "sources_used": sources_used,
    }
