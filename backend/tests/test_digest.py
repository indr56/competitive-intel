"""
Unit tests for the Weekly Digest + White-Label System:
  - Signing (HMAC URL generation + verification)
  - Ranking algorithm
  - Email template generation (HTML + Markdown)
  - White-label theming
"""
from __future__ import annotations

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── Signing Tests ──


def test_sign_and_verify_digest_url():
    from app.core.signing import _compute_signature, verify_signature

    digest_id = "abc-123"
    exp = int(time.time()) + 3600
    sig = _compute_signature(digest_id, exp)

    assert verify_signature(digest_id, sig, exp) is True


def test_verify_signature_expired():
    from app.core.signing import _compute_signature, verify_signature

    digest_id = "abc-123"
    exp = int(time.time()) - 10  # already expired
    sig = _compute_signature(digest_id, exp)

    assert verify_signature(digest_id, sig, exp) is False


def test_verify_signature_wrong_sig():
    from app.core.signing import verify_signature

    exp = int(time.time()) + 3600
    assert verify_signature("abc-123", "wrong-signature", exp) is False


def test_sign_digest_url_format():
    from app.core.signing import sign_digest_url

    url = sign_digest_url("test-id", base_url="http://localhost:8000")
    assert "http://localhost:8000/api/report/test-id?" in url
    assert "sig=" in url
    assert "exp=" in url


def test_unsubscribe_token_sign_verify():
    from app.core.signing import sign_unsubscribe_token, verify_unsubscribe_token

    token = sign_unsubscribe_token("user-42")
    assert verify_unsubscribe_token("user-42", token) is True
    assert verify_unsubscribe_token("user-99", token) is False


# ── Ranking Tests ──


def test_compute_rank_score_critical():
    from app.services.digest import _compute_rank_score

    # critical=100, impact=80 → 100*0.4 + 80*0.6 = 40 + 48 = 88
    score = _compute_rank_score("critical", 80.0)
    assert abs(score - 88.0) < 0.01


def test_compute_rank_score_low():
    from app.services.digest import _compute_rank_score

    # low=25, impact=10 → 25*0.4 + 10*0.6 = 10 + 6 = 16
    score = _compute_rank_score("low", 10.0)
    assert abs(score - 16.0) < 0.01


def test_compute_rank_score_unknown_severity():
    from app.services.digest import _compute_rank_score

    # unknown defaults to 50
    score = _compute_rank_score("unknown", 50.0)
    assert abs(score - 50.0) < 0.01  # 50*0.4 + 50*0.6 = 20 + 30 = 50


def test_ranking_order():
    from app.services.digest import _compute_rank_score

    critical_high = _compute_rank_score("critical", 90)
    high_medium = _compute_rank_score("high", 50)
    low_low = _compute_rank_score("low", 10)

    assert critical_high > high_medium > low_low


# ── Email Template Tests ──


def test_build_html_default_theme():
    from app.services.email import build_digest_html

    changes = [{
        "competitor_name": "Acme Corp",
        "categories": ["pricing_change"],
        "severity": "high",
        "ai_summary": "Price increased by 20%",
        "ai_why_it_matters": "Opens pricing gap",
        "ai_next_moves": "Update matrix",
        "rank_score": 75.0,
        "impact_score": 60.0,
    }]

    html = build_digest_html("My Workspace", "Feb 25 – Mar 04, 2026", changes)
    assert "Acme Corp" in html
    assert "Price increased by 20%" in html
    assert "#111827" in html  # default brand color
    assert "Competitive Moves Intelligence" in html
    assert "pricing_change" in html


def test_build_html_custom_theme():
    from app.services.email import build_digest_html
    from app.services.digest import WhiteLabelTheme

    theme = WhiteLabelTheme(
        logo_url="https://example.com/logo.png",
        brand_color="#2563EB",
        company_name="Acme Intel",
        footer_text="Powered by Acme Intel Platform",
    )
    changes = [{
        "competitor_name": "Rival Inc",
        "categories": ["feature_claim"],
        "severity": "medium",
        "ai_summary": "New feature launched",
        "rank_score": 50.0,
        "impact_score": 40.0,
    }]

    html = build_digest_html("Acme WS", "Mar 01 – Mar 07, 2026", changes, theme)
    assert "#2563EB" in html
    assert "Acme Intel" in html
    assert "logo.png" in html
    assert "Powered by Acme Intel Platform" in html


def test_build_html_empty_changes():
    from app.services.email import build_digest_html

    html = build_digest_html("WS", "period", [])
    assert "No changes detected" in html


def test_build_markdown_output():
    from app.services.email import build_digest_markdown

    changes = [{
        "competitor_name": "Rival",
        "categories": ["pricing_change"],
        "severity": "high",
        "ai_summary": "Price went up",
        "ai_why_it_matters": "Opportunity for us",
        "ai_next_moves": "Update pricing page",
        "rank_score": 70.0,
    }]

    md = build_digest_markdown("My WS", "Feb – Mar 2026", changes)
    assert "# Competitive Intel Digest" in md
    assert "**My WS**" in md
    assert "## 1. Rival" in md
    assert "HIGH" in md
    assert "Price went up" in md
    assert "**Why it matters:**" in md
    assert "**Next moves:**" in md


def test_build_markdown_custom_theme():
    from app.services.email import build_digest_markdown
    from app.services.digest import WhiteLabelTheme

    theme = WhiteLabelTheme(company_name="Custom Corp")
    md = build_digest_markdown("WS", "period", [], theme)
    assert "*Custom Corp*" in md


# ── White-Label Theme Tests ──


def test_white_label_theme_defaults():
    from app.services.digest import WhiteLabelTheme

    theme = WhiteLabelTheme()
    assert theme.brand_color == "#111827"
    assert theme.sender_name == "Competitive Intel"
    assert theme.company_name == "Competitive Moves Intelligence"


def test_white_label_theme_custom():
    from app.services.digest import WhiteLabelTheme

    theme = WhiteLabelTheme(
        brand_color="#FF0000",
        sender_name="My Brand",
        company_name="My Company",
        logo_url="https://example.com/logo.png",
    )
    assert theme.brand_color == "#FF0000"
    assert theme.sender_name == "My Brand"
    assert theme.logo_url == "https://example.com/logo.png"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
