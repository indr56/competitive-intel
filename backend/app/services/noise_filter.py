from __future__ import annotations

import re
import logging

logger = logging.getLogger(__name__)

# Regex patterns for noise that should be stripped before diffing
NOISE_PATTERNS: list[tuple[str, str]] = [
    # Dates in various formats
    (r"\b\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}\b", "[DATE]"),
    # Times
    (r"\b\d{1,2}:\d{2}\s?(?:AM|PM|am|pm)?\b", "[TIME]"),
    # Copyright years
    (r"©\s?\d{4}", "©[YEAR]"),
    # Vanity metrics: "10,000+ customers"
    (r"\d{1,3}(?:,\d{3})+\+?\s*(?:customers|users|companies|teams|businesses)", "[METRIC]"),
    # Cookie / consent banners
    (r"(?i)(?:we use cookies|cookie preferences|accept all cookies|privacy preference|consent to cookies).*?(?:\.|$)", ""),
    # Footer boilerplate
    (r"(?i)all rights reserved\.?", ""),
    # Timestamps like "Updated 2 hours ago"
    (r"(?i)(?:updated|modified|published)\s+\d+\s+(?:seconds?|minutes?|hours?|days?)\s+ago", "[TIMESTAMP]"),
]

# Lines that are pure noise if they match entirely
NOISE_LINE_PATTERNS: list[str] = [
    r"^\s*$",  # blank lines
    r"^(?:©|\(c\))\s*\d{4}",
    r"^(?:Privacy Policy|Terms of Service|Cookie Policy)\s*$",
]


def normalize_text(text: str) -> str:
    """Normalize text for comparison: lowercase, collapse whitespace, strip noise."""
    text = text.lower()
    # Apply pattern replacements
    for pattern, replacement in NOISE_PATTERNS:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def filter_noise_lines(lines: list[str]) -> list[str]:
    """Remove lines that are entirely noise."""
    filtered = []
    for line in lines:
        is_noise = False
        for pattern in NOISE_LINE_PATTERNS:
            if re.match(pattern, line.strip(), re.IGNORECASE):
                is_noise = True
                break
        if not is_noise:
            filtered.append(line)
    return filtered


def extract_noise_report(before_text: str, after_text: str, diff_lines: list[str]) -> dict:
    """
    Analyze diff lines and report which changes were suppressed as noise.
    Returns a dict with suppressed patterns and counts.
    """
    suppressed: dict[str, int] = {}
    meaningful_lines: list[str] = []

    for line in diff_lines:
        if not line.startswith(("+", "-")) or line.startswith(("+++", "---")):
            meaningful_lines.append(line)
            continue

        content = line[1:].strip()
        was_noise = False

        for pattern, replacement in NOISE_PATTERNS:
            if re.search(pattern, content, re.IGNORECASE):
                key = replacement or pattern[:30]
                suppressed[key] = suppressed.get(key, 0) + 1
                was_noise = True
                break

        for pattern in NOISE_LINE_PATTERNS:
            if re.match(pattern, content, re.IGNORECASE):
                suppressed["blank_or_boilerplate"] = suppressed.get("blank_or_boilerplate", 0) + 1
                was_noise = True
                break

        if not was_noise:
            meaningful_lines.append(line)

    return {
        "suppressed_patterns": suppressed,
        "total_suppressed": sum(suppressed.values()),
        "meaningful_diff_lines": meaningful_lines,
    }
