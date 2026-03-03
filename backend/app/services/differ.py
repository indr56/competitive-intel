from __future__ import annotations

import difflib
import logging
from dataclasses import dataclass, field

from app.core.config import get_settings
from app.services.noise_filter import normalize_text, filter_noise_lines, extract_noise_report

logger = logging.getLogger(__name__)


@dataclass
class DiffResult:
    raw_diff_lines: list[str]
    additions: list[str] = field(default_factory=list)
    removals: list[str] = field(default_factory=list)
    is_meaningful: bool = False
    changed_char_count: int = 0
    noise_report: dict = field(default_factory=dict)
    noise_score: float = 0.0
    impact_score: float = 0.0


def compute_diff(before_text: str, after_text: str) -> DiffResult:
    """
    Compute a structured diff between two text snapshots.
    1. Normalize both texts (strip noise patterns).
    2. Line-level unified diff.
    3. Filter noise lines from diff output.
    4. Determine if remaining diff crosses meaningful threshold.
    """
    settings = get_settings()

    # Normalize
    norm_before = normalize_text(before_text)
    norm_after = normalize_text(after_text)

    before_lines = filter_noise_lines(norm_before.splitlines())
    after_lines = filter_noise_lines(norm_after.splitlines())

    # Unified diff
    diff_lines = list(
        difflib.unified_diff(
            before_lines,
            after_lines,
            lineterm="",
            fromfile="before",
            tofile="after",
        )
    )

    # Extract noise from diff lines
    noise_report = extract_noise_report(before_text, after_text, diff_lines)
    meaningful_lines = noise_report["meaningful_diff_lines"]

    additions = [l[1:] for l in meaningful_lines if l.startswith("+") and not l.startswith("+++")]
    removals = [l[1:] for l in meaningful_lines if l.startswith("-") and not l.startswith("---")]

    changed_chars = sum(len(l) for l in additions) + sum(len(l) for l in removals)
    is_meaningful = changed_chars >= settings.DIFF_MEANINGFUL_THRESHOLD

    # Noise score: what fraction of diff lines were suppressed as noise
    total_suppressed = noise_report.get("total_suppressed", 0)
    total_diff_lines = total_suppressed + len(additions) + len(removals)
    n_score = round((total_suppressed / max(total_diff_lines, 1)) * 100, 1)

    logger.info(
        "Diff computed: %d additions, %d removals, %d changed chars, meaningful=%s, noise=%.1f%%",
        len(additions),
        len(removals),
        changed_chars,
        is_meaningful,
        n_score,
    )

    return DiffResult(
        raw_diff_lines=diff_lines,
        additions=additions,
        removals=removals,
        is_meaningful=is_meaningful,
        changed_char_count=changed_chars,
        noise_report=noise_report,
        noise_score=n_score,
    )


CATEGORY_WEIGHTS: dict[str, int] = {
    "pricing_change": 15,
    "plan_restructure": 12,
    "positioning_hero": 10,
    "cta_change": 8,
    "feature_claim": 8,
    "new_alternatives_content": 10,
    "other": 3,
}

SEVERITY_WEIGHTS: dict[str, int] = {
    "low": 10,
    "medium": 20,
    "high": 30,
    "critical": 40,
}


def compute_impact_score(
    changed_chars: int,
    severity: str,
    categories: list[str],
) -> float:
    """
    Composite impact score 0–100:
      char_score (0–30) + severity_score (0–40) + category_score (0–30)
    """
    char_score = min(changed_chars / 500.0, 1.0) * 30
    sev_score = SEVERITY_WEIGHTS.get(severity, 20)
    cat_score = min(sum(CATEGORY_WEIGHTS.get(c, 3) for c in categories), 30)
    return round(char_score + sev_score + cat_score, 1)
