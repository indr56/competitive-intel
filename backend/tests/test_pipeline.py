"""
Unit tests for the Competitive Monitoring Core:
  - NoiseFilter
  - DiffService (differ.py)
  - ClassificationService (classifier.py)
  - impact_score / noise_score calculations
"""
from __future__ import annotations

import sys
import os

# Ensure the backend package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── NoiseFilter tests ──


def test_normalize_text_strips_dates():
    from app.services.noise_filter import normalize_text

    text = "Updated on 03/04/2026 at 2:30 PM"
    result = normalize_text(text)
    assert "[DATE]" in result
    assert "[TIME]" in result
    assert "03/04/2026" not in result


def test_normalize_text_strips_copyright():
    from app.services.noise_filter import normalize_text

    text = "© 2024 Acme Corp. All rights reserved."
    result = normalize_text(text)
    assert "©[YEAR]" in result
    assert "all rights reserved" not in result


def test_normalize_text_strips_vanity_metrics():
    from app.services.noise_filter import normalize_text

    text = "Trusted by 10,000+ customers worldwide"
    result = normalize_text(text)
    assert "[METRIC]" in result


def test_filter_noise_lines_removes_blanks():
    from app.services.noise_filter import filter_noise_lines

    lines = ["real content", "   ", "", "more content"]
    result = filter_noise_lines(lines)
    assert result == ["real content", "more content"]


def test_filter_noise_lines_removes_boilerplate():
    from app.services.noise_filter import filter_noise_lines

    lines = ["Privacy Policy", "Terms of Service", "actual text"]
    result = filter_noise_lines(lines)
    assert result == ["actual text"]


def test_extract_noise_report_separates_noise():
    from app.services.noise_filter import extract_noise_report

    diff_lines = [
        "--- before",
        "+++ after",
        "-old line",
        "+new line",
        "-© 2024 Acme Corp",
        "+© 2025 Acme Corp",
    ]
    report = extract_noise_report("", "", diff_lines)
    assert report["total_suppressed"] >= 2
    assert len(report["meaningful_diff_lines"]) < len(diff_lines)


# ── Differ tests ──


def test_compute_diff_identical_texts():
    from app.services.differ import compute_diff

    result = compute_diff("hello world", "hello world")
    assert result.is_meaningful is False
    assert result.changed_char_count == 0
    assert len(result.additions) == 0
    assert len(result.removals) == 0


def test_compute_diff_meaningful_change():
    from app.services.differ import compute_diff

    before = "Our product costs $99/month for teams."
    after = "Our product costs $149/month for teams. New enterprise plan available."
    result = compute_diff(before, after)
    assert result.changed_char_count > 0
    assert result.is_meaningful is True
    assert result.noise_score >= 0


def test_compute_diff_noise_only_change():
    from app.services.differ import compute_diff

    before = "Hello world. Updated 2 hours ago. © 2024"
    after = "Hello world. Updated 5 hours ago. © 2025"
    result = compute_diff(before, after)
    # After normalization, these should collapse to the same placeholders
    # so the diff should not be meaningful
    assert result.is_meaningful is False


def test_noise_score_calculation():
    from app.services.differ import compute_diff

    # Mix of noise and real changes
    before = "Price: $50/mo\n© 2024 Acme\nUpdated 1 hours ago"
    after = "Price: $75/mo\n© 2025 Acme\nUpdated 3 hours ago"
    result = compute_diff(before, after)
    assert 0 <= result.noise_score <= 100


# ── Impact score tests ──


def test_impact_score_high_severity_pricing():
    from app.services.differ import compute_impact_score

    score = compute_impact_score(
        changed_chars=300,
        severity="high",
        categories=["pricing_change", "plan_restructure"],
    )
    # char_score = min(300/500, 1.0) * 30 = 18
    # sev_score = 30
    # cat_score = min(15 + 12, 30) = 27
    assert score == 75.0


def test_impact_score_low_severity_other():
    from app.services.differ import compute_impact_score

    score = compute_impact_score(
        changed_chars=20,
        severity="low",
        categories=["other"],
    )
    # char_score = min(20/500, 1.0) * 30 = 1.2
    # sev_score = 10
    # cat_score = 3
    assert score == 14.2


def test_impact_score_caps_at_100():
    from app.services.differ import compute_impact_score

    score = compute_impact_score(
        changed_chars=10000,
        severity="critical",
        categories=["pricing_change", "plan_restructure", "positioning_hero", "cta_change"],
    )
    # char_score = 30 (capped)
    # sev_score = 40
    # cat_score = min(15+12+10+8, 30) = 30
    assert score == 100.0


# ── Classifier tests ──


def test_classify_with_rules_pricing_keywords():
    from app.services.classifier import classify_with_rules
    from app.services.differ import DiffResult
    from app.models.models import ChangeCategory, PageType

    diff = DiffResult(
        raw_diff_lines=[],
        additions=["New price: $99/month billed annually"],
        removals=["Old price: $79/month"],
    )
    categories = classify_with_rules(diff, PageType.PRICING)
    assert ChangeCategory.PRICING_CHANGE in categories


def test_classify_with_rules_page_type_heuristic():
    from app.services.classifier import classify_with_rules
    from app.services.differ import DiffResult
    from app.models.models import ChangeCategory, PageType

    diff = DiffResult(
        raw_diff_lines=[],
        additions=["some generic text change"],
        removals=[],
    )
    # Pricing page should auto-add PRICING_CHANGE even without keywords
    categories = classify_with_rules(diff, PageType.PRICING)
    assert ChangeCategory.PRICING_CHANGE in categories

    # Home hero page should auto-add POSITIONING_HERO
    categories = classify_with_rules(diff, PageType.HOME_HERO)
    assert ChangeCategory.POSITIONING_HERO in categories


def test_classify_with_rules_cta_keywords():
    from app.services.classifier import classify_with_rules
    from app.services.differ import DiffResult
    from app.models.models import ChangeCategory, PageType

    diff = DiffResult(
        raw_diff_lines=[],
        additions=["Get started free today! Book a demo now."],
        removals=["Start your trial"],
    )
    categories = classify_with_rules(diff, PageType.LANDING)
    assert ChangeCategory.CTA_CHANGE in categories


def test_classify_with_rules_fallback_to_other():
    from app.services.classifier import classify_with_rules
    from app.services.differ import DiffResult
    from app.models.models import ChangeCategory, PageType

    diff = DiffResult(
        raw_diff_lines=[],
        additions=["lorem ipsum dolor sit amet"],
        removals=[],
    )
    categories = classify_with_rules(diff, PageType.FEATURES_DOCS)
    assert ChangeCategory.OTHER in categories


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
