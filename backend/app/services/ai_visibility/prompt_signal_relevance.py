"""
Prompt-Signal Relevance Scoring.

Computes semantic relevance between a competitor signal and a tracked prompt
to prevent false AI Impact correlations.

Algorithm:
- Generic/company-wide signal types (pricing, funding, etc.) are always
  considered relevant (score = 1.0) — they can affect any prompt.
- Domain-specific signal types (feature_release, integration_added, etc.)
  use keyword overlap (Jaccard similarity) with simple suffix-stemming.
- Score range: 0.0 – 1.0.  Threshold = 0.1 (only filter clear domain mismatches).
"""

from __future__ import annotations

import re

# ── Signal types that are company-wide and potentially relevant to any prompt ──
ALWAYS_RELEVANT_SIGNAL_TYPES: frozenset[str] = frozenset(
    {
        "pricing_change",
        "funding",
        "acquisition",
        "hiring",
        "positioning_change",
        "website_change",
        "review",
        "marketing",
    }
)

# ── Threshold: prompts scoring below this are skipped during ai_impact correlation ──
PROMPT_SIGNAL_RELEVANCE_THRESHOLD: float = 0.1

_STOPWORDS: frozenset[str] = frozenset(
    {
        "the", "a", "an", "is", "are", "was", "were", "has", "have", "had",
        "in", "on", "at", "to", "for", "of", "and", "or", "but", "with",
        "from", "by", "be", "it", "its", "this", "that", "we", "they", "i",
        "my", "our", "you", "your", "he", "she", "after", "before", "up",
        "out", "new", "about", "into", "than", "then", "will", "can", "as",
        "more", "no", "not", "so", "if", "what", "which", "who", "how",
        "when", "where", "there", "all", "each", "both", "few", "do", "did",
        "does", "been", "being", "just", "also", "such", "test", "signal",
    }
)


def _stem(word: str) -> str:
    """Simple suffix removal to normalise morphological variants."""
    for suffix in ("tions", "tion", "ing", "ers", "ed", "es", "er", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    return word


def _tokenize(text: str) -> set[str]:
    """Lower-case, keep alpha tokens ≥3 chars, remove stopwords, apply stem."""
    words = re.findall(r"\b[a-z]{3,}\b", text.lower())
    return {_stem(w) for w in words if w not in _STOPWORDS}


def compute_prompt_signal_relevance(
    signal_type: str,
    signal_title: str,
    prompt_text: str,
    competitor_name: str = "",
) -> float:
    """
    Return a 0.0-1.0 relevance score.

    - Generic signal types → 1.0 (always relevant)
    - Domain-specific types → Jaccard similarity of stemmed keyword sets,
      with a small prefix-match boost for near-synonyms.
    """
    if signal_type in ALWAYS_RELEVANT_SIGNAL_TYPES:
        return 1.0

    signal_context = f"{competitor_name} {signal_type.replace('_', ' ')} {signal_title}"
    sig_tokens = _tokenize(signal_context)
    prompt_tokens = _tokenize(prompt_text)

    if not sig_tokens or not prompt_tokens:
        return 0.5  # insufficient data — be permissive

    intersection = sig_tokens & prompt_tokens
    union = sig_tokens | prompt_tokens
    jaccard = len(intersection) / len(union) if union else 0.0

    # Prefix-match boost for near-synonyms not captured by stemming
    prefix_bonus = 0.0
    for s in sig_tokens:
        for p in prompt_tokens:
            if s != p and len(s) >= 4 and len(p) >= 4:
                if s[:4] == p[:4]:
                    prefix_bonus += 0.04

    score = jaccard + min(prefix_bonus, 0.20)
    return round(min(1.0, score), 3)


def filter_prompts_by_relevance(
    signal_type: str,
    signal_title: str,
    competitor_name: str,
    tracked_prompts: list,
    threshold: float = PROMPT_SIGNAL_RELEVANCE_THRESHOLD,
) -> list[tuple]:
    """
    Return [(tracked_prompt, relevance_score), ...] for prompts that pass
    the relevance threshold.  Preserves original order.
    """
    result = []
    for tp in tracked_prompts:
        score = compute_prompt_signal_relevance(
            signal_type, signal_title, tp.prompt_text, competitor_name
        )
        if score >= threshold:
            result.append((tp, score))
    return result
