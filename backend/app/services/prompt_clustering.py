"""
Prompt clustering service — normalizes prompts, computes similarity,
and groups them into clusters to prevent duplicate prompt runs.
"""

from __future__ import annotations

import logging
import math
import re
import string
from collections import defaultdict
from typing import Any

from sqlalchemy.orm import Session

from app.models.models import MonitoredPrompt, PromptCluster

logger = logging.getLogger(__name__)

# ── Stopwords (common English) ──

STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "shall", "can", "this", "that",
    "these", "those", "it", "its", "i", "me", "my", "we", "our", "you",
    "your", "he", "she", "they", "them", "their", "what", "which", "who",
    "whom", "how", "when", "where", "why", "not", "no", "so", "if",
    "about", "up", "out", "just", "than", "then", "into", "over", "after",
    "before", "between", "under", "above", "most", "very", "too", "also",
}

# ── Simple lemmatization rules (suffix stripping) ──

LEMMA_RULES = [
    ("ies", "y"),     # companies -> company
    ("ves", "f"),     # lives -> life
    ("ses", "s"),     # analyses -> analysis
    ("ing", ""),      # running -> run
    ("tion", ""),     # automation -> automat
    ("ment", ""),     # management -> manage
    ("ness", ""),     # business -> busi
    ("ers", ""),      # providers -> provid
    ("ed", ""),       # powered -> power
    ("ly", ""),       # quickly -> quick
    ("s", ""),        # tools -> tool
]


def normalize_prompt(raw_text: str) -> str:
    """
    Normalize a prompt string:
    1. Lowercase
    2. Remove punctuation
    3. Remove stopwords
    4. Simple lemmatization (suffix stripping)
    5. Sort remaining keywords alphabetically
    6. Join with space

    Examples:
        "best CRM tools" -> "crm"
        "top CRM software for startups" -> "crm software startup"
        "workflow automation platforms" -> "automat platform workflow"
    """
    # Lowercase
    text = raw_text.lower().strip()

    # Remove punctuation
    text = text.translate(str.maketrans("", "", string.punctuation))

    # Tokenize
    tokens = text.split()

    # Remove stopwords
    tokens = [t for t in tokens if t not in STOPWORDS and len(t) > 1]

    # Simple lemmatization
    lemmatized = []
    for token in tokens:
        lemma = _simple_lemmatize(token)
        if lemma and len(lemma) > 1:
            lemmatized.append(lemma)

    # Deduplicate and sort
    unique = sorted(set(lemmatized))

    return " ".join(unique) if unique else raw_text.lower().strip()


def _simple_lemmatize(word: str) -> str:
    """Apply simple suffix-stripping lemmatization."""
    for suffix, replacement in LEMMA_RULES:
        if word.endswith(suffix) and len(word) > len(suffix) + 2:
            return word[: -len(suffix)] + replacement
    return word


# ── Embedding & Similarity ──


def compute_embedding(text: str) -> list[float]:
    """
    Compute a simple TF-based embedding for a normalized prompt.
    Uses character n-grams (2-4) as features for lightweight similarity.
    No external dependencies required.
    """
    ngrams = _char_ngrams(text, 2, 4)
    # Build a frequency vector
    freq: dict[str, int] = defaultdict(int)
    for ng in ngrams:
        freq[ng] += 1
    # Normalize to unit vector
    magnitude = math.sqrt(sum(v * v for v in freq.values())) or 1.0
    return {k: round(v / magnitude, 6) for k, v in freq.items()}


def _char_ngrams(text: str, min_n: int, max_n: int) -> list[str]:
    """Extract character n-grams from text."""
    ngrams = []
    for n in range(min_n, max_n + 1):
        for i in range(len(text) - n + 1):
            ngrams.append(text[i: i + n])
    return ngrams


def cosine_similarity(emb_a: dict, emb_b: dict) -> float:
    """Compute cosine similarity between two sparse embedding dicts."""
    if not emb_a or not emb_b:
        return 0.0

    # Dot product over shared keys
    shared_keys = set(emb_a.keys()) & set(emb_b.keys())
    if not shared_keys:
        return 0.0

    dot = sum(emb_a[k] * emb_b[k] for k in shared_keys)
    mag_a = math.sqrt(sum(v * v for v in emb_a.values()))
    mag_b = math.sqrt(sum(v * v for v in emb_b.values()))

    if mag_a == 0 or mag_b == 0:
        return 0.0

    return round(dot / (mag_a * mag_b), 4)


# ── Clustering Logic ──

SIMILARITY_THRESHOLD = 0.65


def cluster_prompts(
    db: Session,
    workspace_id: str,
    threshold: float = SIMILARITY_THRESHOLD,
) -> dict[str, Any]:
    """
    Run clustering on all monitored prompts in a workspace.
    1. Compute embeddings for prompts missing them
    2. Group prompts by similarity
    3. Create/update PromptCluster records
    """
    prompts = (
        db.query(MonitoredPrompt)
        .filter(
            MonitoredPrompt.workspace_id == workspace_id,
            MonitoredPrompt.is_active == True,  # noqa: E712
        )
        .all()
    )

    if not prompts:
        return {
            "clusters_created": 0,
            "clusters_updated": 0,
            "prompts_clustered": 0,
            "prompts_unclustered": 0,
        }

    # Step 1: Ensure all prompts have embeddings
    for p in prompts:
        if not p.embedding:
            p.embedding = compute_embedding(p.normalized_text)
    db.commit()

    # Step 2: Greedy clustering
    unclustered = list(prompts)
    clusters: list[list[MonitoredPrompt]] = []

    while unclustered:
        seed = unclustered.pop(0)
        group = [seed]
        remaining = []

        for p in unclustered:
            sim = cosine_similarity(seed.embedding, p.embedding)
            if sim >= threshold:
                group.append(p)
            else:
                remaining.append(p)

        clusters.append(group)
        unclustered = remaining

    # Step 3: Create/update PromptCluster records
    # First, remove existing clusters for this workspace (rebuild)
    existing_clusters = (
        db.query(PromptCluster)
        .filter(PromptCluster.workspace_id == workspace_id)
        .all()
    )
    for ec in existing_clusters:
        db.delete(ec)
    db.flush()

    clusters_created = 0
    prompts_clustered = 0
    prompts_unclustered = 0

    for group in clusters:
        if len(group) < 2:
            # Single prompt — unclustered, clear its cluster_id
            group[0].cluster_id = None
            prompts_unclustered += 1
            continue

        # Determine cluster topic from most common normalized tokens
        topic = _derive_cluster_topic(group)

        cluster = PromptCluster(
            workspace_id=workspace_id,
            cluster_topic=topic,
            normalized_topic=normalize_prompt(topic),
            description=f"Cluster of {len(group)} similar prompts about '{topic}'",
        )
        db.add(cluster)
        db.flush()

        for p in group:
            p.cluster_id = cluster.id
            prompts_clustered += 1

        clusters_created += 1

    db.commit()

    return {
        "clusters_created": clusters_created,
        "clusters_updated": 0,
        "prompts_clustered": prompts_clustered,
        "prompts_unclustered": prompts_unclustered,
    }


def _derive_cluster_topic(group: list[MonitoredPrompt]) -> str:
    """Derive a human-readable topic from a group of prompts."""
    # Count word frequency across all raw texts
    word_freq: dict[str, int] = defaultdict(int)
    for p in group:
        words = p.raw_text.lower().split()
        for w in words:
            clean = w.strip(string.punctuation)
            if clean and clean not in STOPWORDS and len(clean) > 2:
                word_freq[clean] += 1

    # Take the top 2-3 most frequent words
    sorted_words = sorted(word_freq.items(), key=lambda x: -x[1])
    top_words = [w for w, _ in sorted_words[:3]]

    if top_words:
        return " ".join(w.capitalize() for w in top_words)
    return group[0].raw_text[:50]


def add_prompt_to_workspace(
    db: Session,
    workspace_id: str,
    raw_text: str,
) -> MonitoredPrompt:
    """
    Add a new monitored prompt to a workspace.
    Normalizes the text and computes embedding.
    """
    normalized = normalize_prompt(raw_text)
    embedding = compute_embedding(normalized)

    prompt = MonitoredPrompt(
        workspace_id=workspace_id,
        raw_text=raw_text.strip(),
        normalized_text=normalized,
        embedding=embedding,
    )
    db.add(prompt)
    db.commit()
    db.refresh(prompt)

    # Try to assign to an existing cluster
    _try_assign_cluster(db, prompt, workspace_id)

    return prompt


def _try_assign_cluster(
    db: Session,
    prompt: MonitoredPrompt,
    workspace_id: str,
    threshold: float = SIMILARITY_THRESHOLD,
) -> None:
    """Try to assign a new prompt to an existing cluster based on similarity."""
    clusters = (
        db.query(PromptCluster)
        .filter(PromptCluster.workspace_id == workspace_id)
        .all()
    )

    for cluster in clusters:
        # Check similarity against cluster members
        members = (
            db.query(MonitoredPrompt)
            .filter(MonitoredPrompt.cluster_id == cluster.id)
            .all()
        )
        if not members:
            continue

        avg_sim = sum(
            cosine_similarity(prompt.embedding, m.embedding)
            for m in members
        ) / len(members)

        if avg_sim >= threshold:
            prompt.cluster_id = cluster.id
            db.commit()
            return

    # No matching cluster found — stays unclustered
