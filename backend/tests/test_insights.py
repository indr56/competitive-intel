"""
Unit tests for the AI Insight Generation Engine:
  - Insight schemas (Pydantic output validation)
  - Prompt templates (registry, rendering)
  - LLM service (rate limiting, evidence grounding, cost estimation)
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── Insight Schema Tests ──


def test_change_analysis_schema_validates():
    from app.core.insight_schemas import ChangeAnalysisOutput

    data = {
        "summary": "Competitor raised prices 20%",
        "key_changes": [
            {"type": "pricing", "detail": "Pro plan $79→$99", "evidence": "$99/month"}
        ],
        "strategic_impact": "high",
        "why_it_matters": "Opens pricing gap",
        "recommended_actions": ["Update matrix", "Notify sales"],
        "confidence": 0.9,
        "evidence": ["$99/month", "billed annually"],
    }
    result = ChangeAnalysisOutput.model_validate(data)
    assert result.summary == "Competitor raised prices 20%"
    assert result.strategic_impact == "high"
    assert len(result.key_changes) == 1
    assert result.key_changes[0].evidence == "$99/month"
    assert result.confidence == 0.9


def test_change_analysis_schema_rejects_missing_fields():
    from app.core.insight_schemas import ChangeAnalysisOutput
    from pydantic import ValidationError

    try:
        ChangeAnalysisOutput.model_validate({"summary": "test"})
        assert False, "Should have raised ValidationError"
    except ValidationError:
        pass


def test_battlecard_schema_validates():
    from app.core.insight_schemas import BattlecardOutput

    data = {
        "competitor_positioning": "Enterprise focus",
        "our_advantages": ["Lower price"],
        "their_advantages": ["Brand"],
        "objection_handlers": [
            {"objection": "They have more features", "response": "We focus on..."}
        ],
        "key_talking_points": ["Price advantage"],
        "evidence": ["$99/month"],
    }
    result = BattlecardOutput.model_validate(data)
    assert result.competitor_positioning == "Enterprise focus"
    assert len(result.objection_handlers) == 1


def test_executive_brief_schema_validates():
    from app.core.insight_schemas import ExecutiveBriefOutput

    data = {
        "headline": "Competitor X raises prices",
        "tldr": "Summary paragraph",
        "market_implications": "Market impact",
        "risk_level": "medium",
        "opportunity": "Price gap",
        "recommended_response": "Update pricing",
        "evidence": ["$99"],
    }
    result = ExecutiveBriefOutput.model_validate(data)
    assert result.risk_level == "medium"


def test_sales_enablement_schema_validates():
    from app.core.insight_schemas import SalesEnablementOutput

    data = {
        "talk_track": "When prospects mention...",
        "discovery_questions": ["Have you evaluated..."],
        "win_themes": ["Price advantage"],
        "trap_questions": ["Ask about pricing history"],
        "email_snippet": "Ready-to-paste paragraph",
        "evidence": ["$99/month"],
    }
    result = SalesEnablementOutput.model_validate(data)
    assert len(result.discovery_questions) == 1


# ── Prompt Template Tests ──


def test_template_registry_has_all_types():
    from app.core.prompt_templates import TEMPLATE_REGISTRY, LATEST_TEMPLATE_BY_TYPE

    assert "change_analysis_v1" in TEMPLATE_REGISTRY
    assert "battlecard_v1" in TEMPLATE_REGISTRY
    assert "executive_brief_v1" in TEMPLATE_REGISTRY
    assert "sales_enablement_v1" in TEMPLATE_REGISTRY

    assert "change_analysis" in LATEST_TEMPLATE_BY_TYPE
    assert "battlecard" in LATEST_TEMPLATE_BY_TYPE
    assert "executive_brief" in LATEST_TEMPLATE_BY_TYPE
    assert "sales_enablement" in LATEST_TEMPLATE_BY_TYPE


def test_get_template_by_id():
    from app.core.prompt_templates import get_template

    t = get_template("change_analysis_v1")
    assert t.insight_type == "change_analysis"
    assert t.version == "1.0"


def test_get_template_unknown_raises():
    from app.core.prompt_templates import get_template
    import pytest

    with pytest.raises(ValueError, match="Unknown template"):
        get_template("nonexistent_v99")


def test_get_latest_template():
    from app.core.prompt_templates import get_latest_template

    t = get_latest_template("battlecard")
    assert t.template_id == "battlecard_v1"


def test_render_prompt():
    from app.core.prompt_templates import get_template, render_prompt

    t = get_template("change_analysis_v1")
    context = {
        "page_type": "pricing",
        "removals": "Old price: $79",
        "additions": "New price: $99",
        "diff_lines": "-Old price: $79\n+New price: $99",
        "rule_categories": "['pricing_change']",
    }
    system, user = render_prompt(t, context)
    assert "competitive intelligence" in system.lower()
    assert "pricing" in user
    assert "$79" in user
    assert "$99" in user


def test_all_templates_have_evidence_guardrail():
    from app.core.prompt_templates import TEMPLATE_REGISTRY, EVIDENCE_GUARDRAIL

    for tid, template in TEMPLATE_REGISTRY.items():
        assert EVIDENCE_GUARDRAIL in template.system_prompt, (
            f"Template {tid} missing evidence guardrail"
        )


# ── LLM Service Tests ──


def test_token_estimation():
    from app.core.llm_service import estimate_tokens

    assert estimate_tokens("hello world") == 2  # 11 chars / 4 = 2
    assert estimate_tokens("a" * 400) == 100
    assert estimate_tokens("") == 1  # min 1


def test_cost_estimation():
    from app.core.llm_service import estimate_cost

    cost = estimate_cost("gpt-4o", 1000, 500)
    # input: 1000/1000 * 0.005 = 0.005
    # output: 500/1000 * 0.015 = 0.0075
    assert abs(cost - 0.0125) < 0.0001


def test_cost_estimation_unknown_model():
    from app.core.llm_service import estimate_cost

    cost = estimate_cost("unknown-model", 1000, 500)
    # Falls back to gpt-4o rates
    assert cost > 0


def test_rate_limiter_allows_under_limit():
    from app.core.llm_service import SlidingWindowRateLimiter

    limiter = SlidingWindowRateLimiter(max_calls=5, window_seconds=60)
    for _ in range(5):
        assert limiter.check("ws-test") is True


def test_rate_limiter_blocks_over_limit():
    from app.core.llm_service import SlidingWindowRateLimiter

    limiter = SlidingWindowRateLimiter(max_calls=3, window_seconds=60)
    for _ in range(3):
        assert limiter.check("ws-limit-test") is True
    assert limiter.check("ws-limit-test") is False


def test_rate_limiter_separate_workspaces():
    from app.core.llm_service import SlidingWindowRateLimiter

    limiter = SlidingWindowRateLimiter(max_calls=2, window_seconds=60)
    assert limiter.check("ws-a") is True
    assert limiter.check("ws-a") is True
    assert limiter.check("ws-a") is False
    # Different workspace should still be allowed
    assert limiter.check("ws-b") is True


def test_rate_limiter_remaining():
    from app.core.llm_service import SlidingWindowRateLimiter

    limiter = SlidingWindowRateLimiter(max_calls=5, window_seconds=60)
    assert limiter.remaining("ws-remain") == 5
    limiter.check("ws-remain")
    assert limiter.remaining("ws-remain") == 4


# ── Evidence Grounding Tests ──


def test_evidence_grounding_exact_match():
    from app.core.llm_service import verify_evidence_grounding

    refs = ["$99/month billed annually"]
    additions = ["New price: $99/month billed annually"]
    removals = ["Old price: $79/month"]

    grounded, is_ok = verify_evidence_grounding(refs, additions, removals)
    assert is_ok is True
    assert len(grounded) == 1


def test_evidence_grounding_partial_match():
    from app.core.llm_service import verify_evidence_grounding

    refs = ["price increased to ninety nine dollars"]
    additions = ["price increased to ninety nine dollars monthly"]
    removals = []

    grounded, is_ok = verify_evidence_grounding(refs, additions, removals)
    assert is_ok is True


def test_evidence_grounding_no_match():
    from app.core.llm_service import verify_evidence_grounding

    refs = ["completely fabricated claim"]
    additions = ["real change text"]
    removals = ["old text"]

    grounded, is_ok = verify_evidence_grounding(refs, additions, removals)
    assert is_ok is False
    assert len(grounded) == 0


def test_evidence_grounding_empty_refs():
    from app.core.llm_service import verify_evidence_grounding

    grounded, is_ok = verify_evidence_grounding([], ["some text"], [])
    assert is_ok is False


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
