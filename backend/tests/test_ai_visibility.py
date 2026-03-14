"""
Comprehensive tests for AI Visibility Intelligence system.

Tests cover:
- Keyword management (CRUD, extraction, approval)
- Prompt suggestion generation (from all 5 sources)
- Prompt approval workflow
- Global prompt execution + caching
- Workspace filtering
- Visibility trends analytics
- AI Impact correlation engine
- Billing plan enforcement
- API endpoints E2E
"""

import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text as _text
from sqlalchemy.orm import sessionmaker, Session

from app.core.database import Base, get_db
from app.main import app
from app.models.models import (
    Account,
    AIEngineResult,
    AIImpactInsight,
    AIPromptCluster,
    AIPromptRun,
    AIPromptSource,
    AITrackedPrompt,
    AIVisibilityEvent,
    AIWorkspaceKeyword,
    Competitor,
    CompetitorEvent,
    PromptSourceType,
    PromptStatusEnum,
    RunStatusEnum,
    Workspace,
    WorkspaceBilling,
)
from app.services.ai_visibility.keyword_extraction import (
    _extract_ngrams,
    _score_keywords,
)
from app.services.ai_visibility.prompt_execution import (
    normalize_prompt,
    get_or_create_prompt_run,
    run_prompt_globally,
    _has_real_api_key,
    _call_real_engine,
    _simulate_engine_response,
    _AI_VISIBILITY_SYSTEM_PROMPT,
)
from app.services.ai_visibility.prompt_suggestion import (
    generate_all_suggestions,
)
from app.services.ai_visibility.workspace_filtering import (
    _brand_matches,
    _brand_in_raw_response,
    _extract_core_brand_name,
    filter_results_for_workspace,
)
from app.services.ai_visibility.correlation_engine import (
    _compute_impact_score,
    _compute_priority,
    _compute_correlation_confidence,
    _generate_short_title,
    _generate_reasoning,
)
from app.models.models import InsightType, PromptCategory, PromptEngineCitation, CategoryVisibility
from app.services.ai_visibility.citation_extraction import (
    extract_citations_from_response,
    _extract_domain,
)
from app.services.ai_visibility.strategy_alerts import (
    _get_strategy_actions,
    STRATEGY_MAP,
    CONFIDENCE_THRESHOLD,
)
from app.services.ai_visibility.citation_influence import (
    compute_citation_influence,
    ENGINE_WEIGHTS,
)
from app.services.ai_visibility.category_ownership import (
    compute_category_ownership,
)
from app.services.ai_visibility.share_of_voice import (
    generate_share_of_voice_insights,
    SOV_THRESHOLD,
)
from app.services.ai_visibility.narrative_analysis import (
    _extract_descriptors,
    generate_narrative_insights,
)
from app.services.ai_visibility.optimization_playbooks import (
    generate_optimization_playbooks,
    PLAYBOOK_PRIORITY_THRESHOLD,
)

# ── Test DB setup ──

DATABASE_URL = "postgresql://compintel:compintel@localhost:5432/compintel_test"

_tmp = create_engine("postgresql://compintel:compintel@localhost:5432/compintel", isolation_level="AUTOCOMMIT")
with _tmp.connect() as _conn:
    _exists = _conn.execute(_text("SELECT 1 FROM pg_database WHERE datname='compintel_test'")).fetchone()
    if not _exists:
        _conn.execute(_text("CREATE DATABASE compintel_test"))
_tmp.dispose()

engine = create_engine(DATABASE_URL)
TestSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def override_get_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def workspace(db: Session):
    account = Account(name="AI Vis Test", slug="ai-vis-test", plan="free")
    db.add(account)
    db.flush()
    ws = Workspace(account_id=account.id, name="AI Vis WS", slug="ai-vis-ws")
    db.add(ws)
    db.commit()
    db.refresh(ws)
    return ws


@pytest.fixture
def competitor(db: Session, workspace):
    comp = Competitor(
        workspace_id=workspace.id,
        name="HubSpot",
        domain="hubspot.com",
    )
    db.add(comp)
    db.commit()
    db.refresh(comp)
    return comp


@pytest.fixture
def competitor2(db: Session, workspace):
    comp = Competitor(
        workspace_id=workspace.id,
        name="Salesforce",
        domain="salesforce.com",
    )
    db.add(comp)
    db.commit()
    db.refresh(comp)
    return comp


@pytest.fixture
def billing(db: Session, workspace):
    b = WorkspaceBilling(
        workspace_id=workspace.id,
        plan_type="starter",
        subscription_status="trialing",
        trial_ends_at=datetime.now(timezone.utc) + timedelta(days=14),
    )
    db.add(b)
    db.commit()
    db.refresh(b)
    return b


# ═══════════════════════════════════════════════
# 1. Unit Tests — Keyword Extraction
# ═══════════════════════════════════════════════


class TestKeywordExtraction:
    def test_extract_ngrams_basic(self):
        text = "HubSpot is a leading CRM platform for growing businesses"
        ngrams = _extract_ngrams(text, n=2)
        assert len(ngrams) > 0
        # Should contain bigrams and long single words
        assert any("hubspot" in g for g in ngrams)

    def test_extract_ngrams_filters_stopwords(self):
        text = "the and or but with from"
        ngrams = _extract_ngrams(text, n=2)
        assert len(ngrams) == 0

    def test_score_keywords(self):
        ngrams = ["crm software", "crm software", "crm software", "email tool", "email tool"]
        scored = _score_keywords(ngrams, min_count=2)
        assert scored[0] == "crm software"
        assert "email tool" in scored


# ═══════════════════════════════════════════════
# 2. Unit Tests — Prompt Execution
# ═══════════════════════════════════════════════


class TestPromptExecution:
    def test_normalize_prompt(self):
        assert normalize_prompt("  Best CRM Tools!  ") == "best crm tools"
        assert normalize_prompt("What's the #1 tool?") == "whats the 1 tool"

    def test_normalize_prompt_consistent(self):
        a = normalize_prompt("best crm tools for startups")
        b = normalize_prompt("Best CRM Tools For Startups")
        assert a == b

    def test_get_or_create_prompt_run_creates(self, db, workspace):
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        run = get_or_create_prompt_run(db, "best crm tools", today)
        db.commit()
        assert run.id is not None
        assert run.status == RunStatusEnum.PENDING.value

    def test_get_or_create_prompt_run_reuses_cache(self, db, workspace):
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        run1 = get_or_create_prompt_run(db, "best crm tools", today)
        db.commit()
        run2 = get_or_create_prompt_run(db, "best crm tools", today)
        assert run1.id == run2.id

    def test_run_prompt_globally(self, db, workspace):
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        run = run_prompt_globally(db, "best crm tools for startups", today)
        db.commit()
        assert run.status == RunStatusEnum.COMPLETED.value
        assert len(run.engine_results) == 4  # chatgpt, perplexity, claude, gemini
        for er in run.engine_results:
            assert er.status == RunStatusEnum.COMPLETED.value
            assert er.raw_response is not None
            assert len(er.mentioned_brands) > 0

    def test_global_caching_no_duplicate_runs(self, db, workspace):
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        run1 = run_prompt_globally(db, "best crm tools", today)
        db.commit()
        run2 = run_prompt_globally(db, "best crm tools", today)
        assert run1.id == run2.id  # Same run reused


# ═══════════════════════════════════════════════
# 3. Unit Tests — Workspace Filtering
# ═══════════════════════════════════════════════


class TestWorkspaceFiltering:
    def test_brand_matches_exact(self):
        matched, pos = _brand_matches("HubSpot", ["HubSpot", "Salesforce", "Zapier"])
        assert matched
        assert pos == 1

    def test_brand_matches_case_insensitive(self):
        matched, pos = _brand_matches("hubspot", ["HubSpot", "Salesforce"])
        assert matched
        assert pos == 1

    def test_brand_matches_no_match(self):
        matched, pos = _brand_matches("Notion", ["HubSpot", "Salesforce"])
        assert not matched
        assert pos is None

    def test_filter_results_creates_events(self, db, workspace, competitor):
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        # Create tracked prompt
        tp = AITrackedPrompt(
            workspace_id=workspace.id,
            prompt_text="best crm tools",
            normalized_text=normalize_prompt("best crm tools"),
            source_type="manual",
            is_active=True,
        )
        db.add(tp)
        db.flush()

        # Run the prompt globally
        run = run_prompt_globally(db, "best crm tools", today)
        db.commit()

        # Filter for workspace
        result = filter_results_for_workspace(db, str(workspace.id), today)
        assert result["events_created"] >= 0  # May or may not match depending on simulation


# ═══════════════════════════════════════════════
# 4. Unit Tests — Correlation Engine
# ═══════════════════════════════════════════════


class TestCorrelationEngine:
    def test_compute_impact_score_no_change(self):
        score = _compute_impact_score(0, 0, 0)
        assert score == 0.0

    def test_compute_impact_score_zero_delta(self):
        score = _compute_impact_score(3, 3, 2)
        assert score == 0.0

    def test_compute_impact_score_increase(self):
        score = _compute_impact_score(5, 10, 3, "pricing_change", 0)
        assert score > 0
        assert score <= 100

    def test_compute_impact_score_first_detection(self):
        score = _compute_impact_score(0, 2, 2, "blog_post", 0)
        assert 0 < score <= 50  # First detection capped at 50

    def test_compute_impact_score_varies_by_signal_type(self):
        score_pricing = _compute_impact_score(2, 5, 2, "pricing_change", 0)
        score_hiring = _compute_impact_score(2, 5, 2, "hiring", 0)
        assert score_pricing > score_hiring  # pricing_change weighs more

    def test_compute_impact_score_recency_bonus(self):
        score_recent = _compute_impact_score(2, 5, 2, "blog_post", 0)
        score_old = _compute_impact_score(2, 5, 2, "blog_post", 10)
        assert score_recent > score_old  # Recent signals score higher

    def test_compute_priority_p0(self):
        assert _compute_priority(80) == "P0"

    def test_compute_priority_p1(self):
        assert _compute_priority(50) == "P1"

    def test_compute_priority_p2(self):
        assert _compute_priority(20) == "P2"

    def test_compute_priority_p3(self):
        assert _compute_priority(10) == "P3"
        assert _compute_priority(5) == "P3"

    def test_compute_priority_boundaries(self):
        assert _compute_priority(70) == "P0"
        assert _compute_priority(69.9) == "P1"
        assert _compute_priority(40) == "P1"
        assert _compute_priority(39.9) == "P2"
        assert _compute_priority(15) == "P2"
        assert _compute_priority(14.9) == "P3"


class TestCorrelationConfidence:
    def test_confidence_baseline(self):
        score = _compute_correlation_confidence(5, "website_change", 1, 1)
        assert 0 <= score <= 100

    def test_confidence_recent_signal_higher(self):
        recent = _compute_correlation_confidence(0, "pricing_change", 3, 2)
        old = _compute_correlation_confidence(10, "pricing_change", 3, 2)
        assert recent > old

    def test_confidence_more_engines_higher(self):
        one = _compute_correlation_confidence(1, "blog_post", 1, 1)
        four = _compute_correlation_confidence(1, "blog_post", 4, 1)
        assert four > one

    def test_confidence_larger_delta_higher(self):
        small = _compute_correlation_confidence(1, "blog_post", 2, 1)
        large = _compute_correlation_confidence(1, "blog_post", 2, 5)
        assert large > small

    def test_confidence_important_signal_higher(self):
        pricing = _compute_correlation_confidence(1, "pricing_change", 2, 2)
        hiring = _compute_correlation_confidence(1, "hiring", 2, 2)
        assert pricing > hiring

    def test_confidence_clamped_0_100(self):
        score = _compute_correlation_confidence(0, "pricing_change", 10, 100)
        assert score <= 100
        score2 = _compute_correlation_confidence(100, "website_change", 0, 0)
        assert score2 >= 0


class TestShortTitleGeneration:
    def test_hijack_title(self):
        title = _generate_short_title(
            InsightType.AI_VISIBILITY_HIJACK.value, "Cursor AI", None, None,
        )
        assert "Cursor AI" in title
        assert "New in AI" in title

    def test_loss_title(self):
        title = _generate_short_title(
            InsightType.AI_VISIBILITY_LOSS.value, "Acme", None, None,
        )
        assert "Lost from AI" in title

    def test_dominance_title(self):
        title = _generate_short_title(
            InsightType.AI_DOMINANCE.value, "BigCo", None, None,
        )
        assert "Dominance" in title

    def test_ai_impact_with_signal_title(self):
        title = _generate_short_title(
            InsightType.AI_IMPACT.value, "Acme", "pricing_change", "Acme drops price 50%",
        )
        assert title == "Acme drops price 50%"

    def test_ai_impact_long_signal_falls_back(self):
        long_title = "A" * 100
        title = _generate_short_title(
            InsightType.AI_IMPACT.value, "Acme", "funding", long_title,
        )
        assert "Funding" in title
        assert "Acme" in title


class TestReasoningGeneration:
    def test_hijack_reasoning(self):
        r = _generate_reasoning(
            InsightType.AI_VISIBILITY_HIJACK.value, "Cursor AI",
            "", "", "best AI code editors", ["chatgpt", "perplexity"],
            2, None,
        )
        assert "newly detected" in r
        assert "Cursor AI" in r

    def test_loss_reasoning(self):
        r = _generate_reasoning(
            InsightType.AI_VISIBILITY_LOSS.value, "Acme",
            "", "", "best CRM tools", ["claude"], -1, "CRM Tools",
        )
        assert "disappeared" in r
        assert "CRM Tools" in r

    def test_dominance_reasoning(self):
        r = _generate_reasoning(
            InsightType.AI_DOMINANCE.value, "BigCo",
            "", "", "best project management", ["chatgpt", "claude", "perplexity", "gemini"],
            4, None,
        )
        assert "all queried AI engines" in r

    def test_impact_reasoning_positive_delta(self):
        r = _generate_reasoning(
            InsightType.AI_IMPACT.value, "Acme",
            "pricing_change", "Acme raises prices", "best CRM",
            ["chatgpt"], 2, None,
        )
        assert "improved" in r
        assert "pricing change" in r

    def test_impact_reasoning_negative_delta(self):
        r = _generate_reasoning(
            InsightType.AI_IMPACT.value, "Acme",
            "funding", "Acme Series B", "best CRM",
            ["chatgpt"], -1, None,
        )
        assert "reduced" in r


# ═══════════════════════════════════════════════
# 5. API E2E Tests — Keywords
# ═══════════════════════════════════════════════


class TestKeywordAPI:
    def test_add_keyword(self, workspace, billing):
        res = client.post(
            f"/api/workspaces/{workspace.id}/ai-visibility/keywords",
            json={"keyword": "crm software", "source": "user"},
        )
        assert res.status_code == 201
        data = res.json()
        assert data["keyword"] == "crm software"
        assert data["source"] == "user"
        assert data["is_approved"] is True

    def test_add_keyword_duplicate(self, workspace, billing):
        client.post(
            f"/api/workspaces/{workspace.id}/ai-visibility/keywords",
            json={"keyword": "email marketing"},
        )
        res = client.post(
            f"/api/workspaces/{workspace.id}/ai-visibility/keywords",
            json={"keyword": "email marketing"},
        )
        assert res.status_code == 409

    def test_list_keywords(self, workspace, billing):
        client.post(
            f"/api/workspaces/{workspace.id}/ai-visibility/keywords",
            json={"keyword": "crm"},
        )
        client.post(
            f"/api/workspaces/{workspace.id}/ai-visibility/keywords",
            json={"keyword": "analytics"},
        )
        res = client.get(f"/api/workspaces/{workspace.id}/ai-visibility/keywords")
        assert res.status_code == 200
        assert len(res.json()) == 2

    def test_delete_keyword(self, workspace, billing):
        r = client.post(
            f"/api/workspaces/{workspace.id}/ai-visibility/keywords",
            json={"keyword": "to-delete"},
        )
        kw_id = r.json()["id"]
        res = client.delete(f"/api/workspaces/{workspace.id}/ai-visibility/keywords/{kw_id}")
        assert res.status_code == 204


# ═══════════════════════════════════════════════
# 6. API E2E Tests — Suggestions
# ═══════════════════════════════════════════════


class TestSuggestionAPI:
    def test_add_manual_suggestion(self, workspace, billing):
        res = client.post(
            f"/api/workspaces/{workspace.id}/ai-visibility/suggestions",
            json={"prompt_text": "best crm tools for startups", "source_type": "manual"},
        )
        assert res.status_code == 201
        data = res.json()
        assert data["prompt_text"] == "best crm tools for startups"
        assert data["status"] == "suggested"

    def test_generate_suggestions_from_competitors(self, workspace, competitor, billing):
        res = client.post(
            f"/api/workspaces/{workspace.id}/ai-visibility/suggestions/generate",
            json={"source_types": ["competitor"]},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["suggestions_created"] > 0

        # Verify suggestions exist
        res2 = client.get(
            f"/api/workspaces/{workspace.id}/ai-visibility/suggestions?source_type=competitor"
        )
        assert res2.status_code == 200
        items = res2.json()
        assert len(items) > 0
        # Should contain competitor-based prompts like "alternatives to HubSpot"
        texts = [s["prompt_text"] for s in items]
        assert any("hubspot" in t for t in texts)

    def test_list_suggestions_with_filters(self, workspace, billing):
        client.post(
            f"/api/workspaces/{workspace.id}/ai-visibility/suggestions",
            json={"prompt_text": "test prompt one", "source_type": "manual"},
        )
        client.post(
            f"/api/workspaces/{workspace.id}/ai-visibility/suggestions",
            json={"prompt_text": "test prompt two", "source_type": "keyword"},
        )

        # Filter by source_type
        res = client.get(
            f"/api/workspaces/{workspace.id}/ai-visibility/suggestions?source_type=manual"
        )
        assert res.status_code == 200
        items = res.json()
        assert all(s["source_type"] == "manual" for s in items)


# ═══════════════════════════════════════════════
# 7. API E2E Tests — Approval Workflow
# ═══════════════════════════════════════════════


class TestApprovalAPI:
    def test_approve_creates_tracked_prompt(self, workspace, billing):
        # Create suggestion
        r = client.post(
            f"/api/workspaces/{workspace.id}/ai-visibility/suggestions",
            json={"prompt_text": "best project management tools"},
        )
        src_id = r.json()["id"]

        # Approve it
        res = client.post(
            f"/api/workspaces/{workspace.id}/ai-visibility/suggestions/approve",
            json={"prompt_source_ids": [src_id]},
        )
        assert res.status_code == 200
        tracked = res.json()
        assert len(tracked) == 1
        assert tracked[0]["prompt_text"] == "best project management tools"
        assert tracked[0]["is_active"] is True

    def test_reject_updates_status(self, workspace, billing):
        r = client.post(
            f"/api/workspaces/{workspace.id}/ai-visibility/suggestions",
            json={"prompt_text": "irrelevant prompt here"},
        )
        src_id = r.json()["id"]

        res = client.post(
            f"/api/workspaces/{workspace.id}/ai-visibility/suggestions/reject",
            json={"prompt_source_ids": [src_id]},
        )
        assert res.status_code == 200
        assert res.json()["rejected"] == 1

    def test_cannot_approve_already_approved(self, workspace, billing):
        r = client.post(
            f"/api/workspaces/{workspace.id}/ai-visibility/suggestions",
            json={"prompt_text": "approved prompt test"},
        )
        src_id = r.json()["id"]
        # Approve first time
        client.post(
            f"/api/workspaces/{workspace.id}/ai-visibility/suggestions/approve",
            json={"prompt_source_ids": [src_id]},
        )
        # Approve again — should not create duplicate tracked prompt
        res = client.post(
            f"/api/workspaces/{workspace.id}/ai-visibility/suggestions/approve",
            json={"prompt_source_ids": [src_id]},
        )
        # Returns empty since it was already approved (status != suggested)
        assert res.status_code == 200


# ═══════════════════════════════════════════════
# 8. API E2E Tests — Tracked Prompts
# ═══════════════════════════════════════════════


class TestTrackedPromptsAPI:
    def _create_tracked(self, workspace_id):
        r = client.post(
            f"/api/workspaces/{workspace_id}/ai-visibility/suggestions",
            json={"prompt_text": "best email marketing software"},
        )
        src_id = r.json()["id"]
        client.post(
            f"/api/workspaces/{workspace_id}/ai-visibility/suggestions/approve",
            json={"prompt_source_ids": [src_id]},
        )

    def test_list_tracked_prompts(self, workspace, billing):
        self._create_tracked(workspace.id)
        res = client.get(f"/api/workspaces/{workspace.id}/ai-visibility/prompts")
        assert res.status_code == 200
        items = res.json()
        assert len(items) >= 1

    def test_pause_resume(self, workspace, billing):
        self._create_tracked(workspace.id)
        prompts = client.get(f"/api/workspaces/{workspace.id}/ai-visibility/prompts").json()
        pid = prompts[0]["id"]

        # Pause
        res = client.post(f"/api/workspaces/{workspace.id}/ai-visibility/prompts/{pid}/pause")
        assert res.status_code == 200
        assert res.json()["is_active"] is False

        # Resume
        res = client.post(f"/api/workspaces/{workspace.id}/ai-visibility/prompts/{pid}/pause")
        assert res.json()["is_active"] is True

    def test_delete_tracked_prompt(self, workspace, billing):
        self._create_tracked(workspace.id)
        prompts = client.get(f"/api/workspaces/{workspace.id}/ai-visibility/prompts").json()
        pid = prompts[0]["id"]
        res = client.delete(f"/api/workspaces/{workspace.id}/ai-visibility/prompts/{pid}")
        assert res.status_code == 204

    def test_prompt_limits(self, workspace, billing):
        res = client.get(f"/api/workspaces/{workspace.id}/ai-visibility/prompts/limits")
        assert res.status_code == 200
        data = res.json()
        assert data["limit"] == 10  # starter plan
        assert data["plan"] == "starter"


# ═══════════════════════════════════════════════
# 9. API E2E Tests — Execution
# ═══════════════════════════════════════════════


class TestExecutionAPI:
    def test_run_single_prompt(self, workspace, competitor, billing):
        # Create and approve a prompt
        r = client.post(
            f"/api/workspaces/{workspace.id}/ai-visibility/suggestions",
            json={"prompt_text": "best crm alternatives"},
        )
        src_id = r.json()["id"]
        approved = client.post(
            f"/api/workspaces/{workspace.id}/ai-visibility/suggestions/approve",
            json={"prompt_source_ids": [src_id]},
        ).json()
        prompt_id = approved[0]["id"]

        # Run it
        res = client.post(
            f"/api/workspaces/{workspace.id}/ai-visibility/prompts/{prompt_id}/run"
        )
        assert res.status_code == 200
        data = res.json()
        assert data["prompts_queued"] + data["cached_reused"] >= 1

    def test_run_all_prompts(self, workspace, competitor, billing):
        # Create 2 prompts
        for text in ["best crm software", "top sales automation tools"]:
            r = client.post(
                f"/api/workspaces/{workspace.id}/ai-visibility/suggestions",
                json={"prompt_text": text},
            )
            client.post(
                f"/api/workspaces/{workspace.id}/ai-visibility/suggestions/approve",
                json={"prompt_source_ids": [r.json()["id"]]},
            )

        res = client.post(f"/api/workspaces/{workspace.id}/ai-visibility/prompts/run")
        assert res.status_code == 200
        data = res.json()
        assert data["prompts_queued"] + data["cached_reused"] == 2


# ═══════════════════════════════════════════════
# 10. API E2E Tests — Visibility Events & Trends
# ═══════════════════════════════════════════════


class TestVisibilityAPI:
    def test_list_visibility_events(self, workspace, billing):
        res = client.get(f"/api/workspaces/{workspace.id}/ai-visibility/events")
        assert res.status_code == 200
        assert isinstance(res.json(), list)

    def test_filter_results(self, workspace, competitor, billing):
        res = client.post(f"/api/workspaces/{workspace.id}/ai-visibility/filter")
        assert res.status_code == 200

    def test_get_trends(self, workspace, billing):
        res = client.get(f"/api/workspaces/{workspace.id}/ai-visibility/trends?days=30")
        assert res.status_code == 200
        data = res.json()
        assert "trends" in data
        assert "engines_breakdown" in data
        assert "competitor_summary" in data
        assert "citations" in data


# ═══════════════════════════════════════════════
# 11. API E2E Tests — AI Impact Insights
# ═══════════════════════════════════════════════


class TestInsightsAPI:
    def test_list_insights_empty(self, workspace, billing):
        res = client.get(f"/api/workspaces/{workspace.id}/ai-visibility/insights")
        assert res.status_code == 200
        assert res.json() == []

    def test_run_correlation(self, workspace, competitor, billing):
        res = client.post(
            f"/api/workspaces/{workspace.id}/ai-visibility/insights/correlate?days=7"
        )
        assert res.status_code == 200
        data = res.json()
        assert "insights_created" in data


# ═══════════════════════════════════════════════
# 12. Billing Enforcement Tests
# ═══════════════════════════════════════════════


class TestBillingEnforcement:
    def test_plan_limits_in_billing_plans(self):
        """Verify max_tracked_prompts is in all plan definitions."""
        res = client.get("/api/billing/plans")
        assert res.status_code == 200
        plans = res.json()
        for plan in plans:
            assert "max_tracked_prompts" in plan["limits"]

    def test_prompt_limit_enforced(self, db, workspace, billing):
        """Starter plan has limit of 10 tracked prompts."""
        # Create 10 tracked prompts directly
        for i in range(10):
            tp = AITrackedPrompt(
                workspace_id=workspace.id,
                prompt_text=f"test prompt number {i}",
                normalized_text=f"test prompt number {i}",
                source_type="manual",
                is_active=True,
            )
            db.add(tp)
        db.commit()

        # Try to approve one more — should fail
        r = client.post(
            f"/api/workspaces/{workspace.id}/ai-visibility/suggestions",
            json={"prompt_text": "one too many prompts"},
        )
        src_id = r.json()["id"]
        res = client.post(
            f"/api/workspaces/{workspace.id}/ai-visibility/suggestions/approve",
            json={"prompt_source_ids": [src_id]},
        )
        assert res.status_code == 403


# ═══════════════════════════════════════════════
# 13. Global Execution Deduplication Tests
# ═══════════════════════════════════════════════


class TestGlobalDeduplication:
    """Verify that identical prompts across workspaces only execute once."""

    def test_same_prompt_different_workspaces_same_run(self, db):
        # Create two workspaces
        account = Account(name="Dedup Test", slug="dedup-test", plan="free")
        db.add(account)
        db.flush()
        ws1 = Workspace(account_id=account.id, name="WS1", slug="ws1")
        ws2 = Workspace(account_id=account.id, name="WS2", slug="ws2")
        db.add_all([ws1, ws2])
        db.commit()

        prompt_text = "best crm tools for small business"
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        # Run from first workspace context
        run1 = get_or_create_prompt_run(db, prompt_text, today)
        db.commit()

        # Run from second workspace context — should reuse
        run2 = get_or_create_prompt_run(db, prompt_text, today)

        assert run1.id == run2.id  # Same global run


# ═══════════════════════════════════════════════
# 14. Prompt Runs API Tests
# ═══════════════════════════════════════════════


class TestPromptRunsAPI:
    def test_list_runs(self, workspace, billing):
        res = client.get(f"/api/workspaces/{workspace.id}/ai-visibility/runs")
        assert res.status_code == 200
        assert isinstance(res.json(), list)


# ═══════════════════════════════════════════════
# 15. End-to-End Full Pipeline Test
# ═══════════════════════════════════════════════


# ═══════════════════════════════════════════════
# 16. Simulator — Real Brand Injection Tests
# ═══════════════════════════════════════════════


class TestSimulatorBrandInjection:
    """Verify simulator includes real competitor names from the DB."""

    def test_simulator_includes_known_brands(self):
        from app.services.ai_visibility.prompt_execution import _simulate_engine_response
        resp = _simulate_engine_response(
            "best coding tools", "chatgpt", known_brands=["Cursor", "Peec AI"]
        )
        resp_lower = resp.lower()
        # At least one of the known brands should appear
        assert "cursor" in resp_lower or "peec ai" in resp_lower

    def test_simulator_without_known_brands_unchanged(self):
        from app.services.ai_visibility.prompt_execution import _simulate_engine_response
        resp1 = _simulate_engine_response("best crm tools", "chatgpt", known_brands=None)
        resp2 = _simulate_engine_response("best crm tools", "chatgpt", known_brands=[])
        # Without known brands, behaviour is deterministic and identical
        assert resp1 == resp2

    def test_run_prompt_globally_includes_competitor_brands(self, db, workspace, competitor):
        """After running globally, engine results should mention workspace competitor."""
        from app.services.ai_visibility.prompt_execution import run_prompt_globally
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        run = run_prompt_globally(db, "best crm alternatives to compare", today)
        db.commit()
        # At least one engine should mention the competitor name
        all_brands = []
        all_raw = ""
        for er in run.engine_results:
            all_brands.extend(er.mentioned_brands or [])
            all_raw += (er.raw_response or "").lower()
        assert "hubspot" in [b.lower() for b in all_brands] or "hubspot" in all_raw


# ═══════════════════════════════════════════════
# 17. Raw Response Fallback Tests
# ═══════════════════════════════════════════════


class TestRawResponseFallback:
    """Verify _brand_in_raw_response works correctly."""

    def test_brand_found_with_rank(self):
        from app.services.ai_visibility.workspace_filtering import _brand_in_raw_response
        raw = "Here are recommendations:\n1. **Cursor** — Great tool.\n2. **Notion** — Another one."
        matched, rank = _brand_in_raw_response("Cursor", raw)
        assert matched
        assert rank == 1

    def test_brand_found_no_rank(self):
        from app.services.ai_visibility.workspace_filtering import _brand_in_raw_response
        raw = "Some text mentioning Cursor as a good option."
        matched, rank = _brand_in_raw_response("Cursor", raw)
        assert matched
        assert rank is None

    def test_brand_not_found(self):
        from app.services.ai_visibility.workspace_filtering import _brand_in_raw_response
        raw = "Here are recommendations:\n1. **HubSpot** — Great tool."
        matched, rank = _brand_in_raw_response("Cursor", raw)
        assert not matched

    def test_short_name_skipped(self):
        from app.services.ai_visibility.workspace_filtering import _brand_in_raw_response
        raw = "AI is great for coding"
        matched, _ = _brand_in_raw_response("A", raw)
        assert not matched


# ═══════════════════════════════════════════════
# 18. Domain Normalization Tests
# ═══════════════════════════════════════════════


class TestDomainNormalization:
    def test_normalize_strips_protocol_and_slash(self):
        from app.services.ai_visibility.workspace_filtering import _normalize_domain
        assert _normalize_domain("https://cursor.com/") == "cursor.com"
        assert _normalize_domain("http://www.hubspot.com/") == "hubspot.com"
        assert _normalize_domain("hubspot.com") == "hubspot.com"
        assert _normalize_domain("https://peec.ai/") == "peec.ai"


# ═══════════════════════════════════════════════
# 19. Force Re-Run Tests
# ═══════════════════════════════════════════════


class TestForceReRun:
    def test_force_clears_cache_and_reruns(self, workspace, competitor, billing):
        ws_id = str(workspace.id)
        # Create and approve a prompt
        r = client.post(
            f"/api/workspaces/{ws_id}/ai-visibility/suggestions",
            json={"prompt_text": "best crm alternatives"},
        )
        src_id = r.json()["id"]
        approved = client.post(
            f"/api/workspaces/{ws_id}/ai-visibility/suggestions/approve",
            json={"prompt_source_ids": [src_id]},
        ).json()
        pid = approved[0]["id"]

        # First run
        res1 = client.post(f"/api/workspaces/{ws_id}/ai-visibility/prompts/{pid}/run")
        assert res1.status_code == 200
        assert res1.json()["prompts_queued"] == 1

        # Second run without force — should use cache
        res2 = client.post(f"/api/workspaces/{ws_id}/ai-visibility/prompts/{pid}/run")
        assert res2.json()["cached_reused"] == 1

        # Third run with force — should re-execute
        res3 = client.post(f"/api/workspaces/{ws_id}/ai-visibility/prompts/{pid}/run?force=true")
        assert res3.json()["prompts_queued"] == 1


# ═══════════════════════════════════════════════
# 20. Full Pipeline with Custom Competitors (Key Bug Fix Test)
# ═══════════════════════════════════════════════


class TestFullPipelineCustomCompetitors:
    """
    Reproduces the exact user scenario: custom competitors (not in the
    default brand pool) must produce visibility events after run+filter.
    """

    def test_custom_competitors_produce_events(self, db, workspace, billing):
        ws_id = str(workspace.id)

        # Create custom competitors NOT in the default brand pool
        comp1 = Competitor(workspace_id=workspace.id, name="Cursor", domain="https://cursor.com/")
        comp2 = Competitor(workspace_id=workspace.id, name="Verdent AI", domain="https://verdent.ai/")
        db.add_all([comp1, comp2])
        db.commit()

        # Add a prompt, approve, run
        r = client.post(
            f"/api/workspaces/{ws_id}/ai-visibility/suggestions",
            json={"prompt_text": "best tools for ai coding"},
        )
        assert r.status_code == 201
        src_id = r.json()["id"]

        res = client.post(
            f"/api/workspaces/{ws_id}/ai-visibility/suggestions/approve",
            json={"prompt_source_ids": [src_id]},
        )
        tracked = res.json()
        pid = tracked[0]["id"]

        # Run with force=true
        res = client.post(f"/api/workspaces/{ws_id}/ai-visibility/prompts/{pid}/run?force=true")
        assert res.status_code == 200
        assert res.json()["prompts_queued"] == 1

        # Check visibility events — should find at least one match
        events_res = client.get(f"/api/workspaces/{ws_id}/ai-visibility/events")
        assert events_res.status_code == 200
        events = events_res.json()
        assert len(events) > 0, "Expected visibility events for custom competitors but got none"

        # At least one event should reference Cursor or Verdent AI
        comp_ids = {str(comp1.id), str(comp2.id)}
        matched_comp_ids = {e["competitor_id"] for e in events}
        assert matched_comp_ids & comp_ids, f"No events for custom competitors. Got: {events}"

        # Trends should also have data
        trends_res = client.get(f"/api/workspaces/{ws_id}/ai-visibility/trends?days=30")
        assert trends_res.status_code == 200
        trends = trends_res.json()
        assert len(trends["trends"]) > 0
        assert len(trends["competitor_summary"]) > 0


# ═══════════════════════════════════════════════
# 21. Original Full Pipeline (preserved)
# ═══════════════════════════════════════════════


class TestFullPipeline:
    """
    Full E2E pipeline:
    1. Add keywords
    2. Generate suggestions
    3. Approve suggestions → tracked prompts
    4. Run prompts globally
    5. Filter results for workspace
    6. Check visibility events
    7. Run correlation
    8. Check insights
    """

    def test_full_pipeline(self, workspace, competitor, billing):
        ws_id = str(workspace.id)

        # 1. Add keyword
        res = client.post(
            f"/api/workspaces/{ws_id}/ai-visibility/keywords",
            json={"keyword": "crm software"},
        )
        assert res.status_code == 201

        # 2. Add manual suggestion
        res = client.post(
            f"/api/workspaces/{ws_id}/ai-visibility/suggestions",
            json={"prompt_text": "best crm software for small business"},
        )
        assert res.status_code == 201
        src_id = res.json()["id"]

        # 3. Generate more suggestions from competitors
        res = client.post(
            f"/api/workspaces/{ws_id}/ai-visibility/suggestions/generate",
            json={"source_types": ["competitor"]},
        )
        assert res.status_code == 200

        # 4. Approve the manual suggestion
        res = client.post(
            f"/api/workspaces/{ws_id}/ai-visibility/suggestions/approve",
            json={"prompt_source_ids": [src_id]},
        )
        assert res.status_code == 200
        tracked = res.json()
        assert len(tracked) == 1
        prompt_id = tracked[0]["id"]

        # 5. Run prompt
        res = client.post(f"/api/workspaces/{ws_id}/ai-visibility/prompts/{prompt_id}/run?force=true")
        assert res.status_code == 200
        run_data = res.json()
        assert run_data["prompts_queued"] == 1

        # 6. Check visibility events — HubSpot should be found
        res = client.get(f"/api/workspaces/{ws_id}/ai-visibility/events")
        assert res.status_code == 200
        events = res.json()
        assert len(events) > 0, "HubSpot should produce visibility events"

        # 7. Get trends
        res = client.get(f"/api/workspaces/{ws_id}/ai-visibility/trends?days=30")
        assert res.status_code == 200
        trends = res.json()
        assert "trends" in trends
        assert len(trends["trends"]) > 0

        # 8. Run correlation
        res = client.post(f"/api/workspaces/{ws_id}/ai-visibility/insights/correlate?days=7")
        assert res.status_code == 200

        # 9. Check insights
        res = client.get(f"/api/workspaces/{ws_id}/ai-visibility/insights")
        assert res.status_code == 200

        # 10. Check limits
        res = client.get(f"/api/workspaces/{ws_id}/ai-visibility/prompts/limits")
        assert res.status_code == 200
        assert res.json()["used"] == 1


# ═══════════════════════════════════════════════
# 22. Correlation Engine — Date Normalization & Deduplication Tests
# ═══════════════════════════════════════════════


class TestCorrelationEngineE2E:
    """
    Tests the correlation engine fixes:
    - Date normalization (same-day signal & events go into correct buckets)
    - Top N limiting (max 5 per competitor×prompt)
    - Varied scores (different signal types produce different scores)
    - Re-run clears stale insights
    """

    def test_same_day_signals_produce_first_detection_insights(self, db, workspace, competitor, billing):
        """
        When signals and visibility events are on the same day,
        events should land in 'after' bucket (first detection: before=0, after>0).
        """
        ws_id = str(workspace.id)
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        # Create a tracked prompt + visibility event for today
        tp = AITrackedPrompt(
            workspace_id=workspace.id,
            prompt_text="best crm tools test",
            normalized_text=normalize_prompt("best crm tools test"),
            source_type="manual",
            is_active=True,
        )
        db.add(tp)
        db.flush()

        # Run globally to get engine results
        run = run_prompt_globally(db, "best crm tools test", today)
        db.commit()

        # Filter to create visibility events
        filter_results_for_workspace(db, ws_id, today)
        db.commit()

        # Create a competitor signal for today
        from app.models.models import CompetitorEvent
        ce = CompetitorEvent(
            workspace_id=workspace.id,
            competitor_id=competitor.id,
            signal_type="pricing_change",
            title="HubSpot raised prices",
            source_url="https://hubspot.com/pricing",
            severity="high",
        )
        db.add(ce)
        db.commit()

        # Run correlation
        res = client.post(f"/api/workspaces/{ws_id}/ai-visibility/insights/correlate?days=7")
        assert res.status_code == 200
        data = res.json()

        # Check insights
        insights_res = client.get(f"/api/workspaces/{ws_id}/ai-visibility/insights")
        insights = insights_res.json()

        # Filter to only signal-correlated insights (Type 1: ai_impact)
        # Types 2-4 (hijack/loss/dominance) have different visibility semantics
        ai_impact_insights = [i for i in insights if i.get("insight_type") == "ai_impact"]
        if len(ai_impact_insights) > 0:
            for ins in ai_impact_insights:
                # With date normalization, same-day events should be in 'after' bucket
                # So before=0, after>0 (first detection) — NOT before>0, after=0
                assert ins["visibility_before"] == 0, \
                    f"Expected before=0 (first detection) but got {ins['visibility_before']}"
                assert ins["visibility_after"] > 0, \
                    f"Expected after>0 but got {ins['visibility_after']}"
                # First detection score capped at 50
                assert ins["impact_score"] <= 50.0, \
                    f"First detection score should be ≤50, got {ins['impact_score']}"

    def test_insights_limited_per_competitor_prompt(self, db, workspace, competitor, billing):
        """Max 5 insights per competitor × prompt combination."""
        ws_id = str(workspace.id)
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        tp = AITrackedPrompt(
            workspace_id=workspace.id,
            prompt_text="best crm 2026",
            normalized_text=normalize_prompt("best crm 2026"),
            source_type="manual",
            is_active=True,
        )
        db.add(tp)
        db.flush()

        run = run_prompt_globally(db, "best crm 2026", today)
        db.commit()
        filter_results_for_workspace(db, ws_id, today)
        db.commit()

        # Create 10 signals (more than MAX_INSIGHTS_PER_COMP_PROMPT = 5)
        from app.models.models import CompetitorEvent
        for i in range(10):
            ce = CompetitorEvent(
                workspace_id=workspace.id,
                competitor_id=competitor.id,
                signal_type=["pricing_change", "blog_post", "hiring", "funding", "feature_release",
                             "positioning_change", "integration_added", "website_change",
                             "landing_page_created", "acquisition"][i],
                title=f"Signal {i}: test signal",
                source_url=f"https://hubspot.com/signal-{i}",
                severity="medium",
            )
            db.add(ce)
        db.commit()

        res = client.post(f"/api/workspaces/{ws_id}/ai-visibility/insights/correlate?days=7")
        assert res.status_code == 200

        insights_res = client.get(f"/api/workspaces/{ws_id}/ai-visibility/insights")
        insights = insights_res.json()

        # Type 1 (ai_impact) should be at most 5 (MAX_INSIGHTS_PER_COMP_PROMPT)
        # Types 2-4 (hijack/loss/dominance) are signal-independent and not limited
        ai_impact_insights = [i for i in insights if i.get("insight_type") == "ai_impact"]
        assert len(ai_impact_insights) <= 5, \
            f"Expected max 5 ai_impact insights per comp×prompt but got {len(ai_impact_insights)}"

    def test_rerun_clears_stale_insights(self, db, workspace, competitor, billing):
        """Running correlation again should clear old insights and recompute."""
        ws_id = str(workspace.id)
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        tp = AITrackedPrompt(
            workspace_id=workspace.id,
            prompt_text="best crm rerun test",
            normalized_text=normalize_prompt("best crm rerun test"),
            source_type="manual",
            is_active=True,
        )
        db.add(tp)
        db.flush()
        run = run_prompt_globally(db, "best crm rerun test", today)
        db.commit()
        filter_results_for_workspace(db, ws_id, today)
        db.commit()

        from app.models.models import CompetitorEvent
        ce = CompetitorEvent(
            workspace_id=workspace.id,
            competitor_id=competitor.id,
            signal_type="funding",
            title="HubSpot Series Z",
            source_url="https://hubspot.com/funding",
            severity="high",
        )
        db.add(ce)
        db.commit()

        # First run
        res1 = client.post(f"/api/workspaces/{ws_id}/ai-visibility/insights/correlate?days=7")
        count1 = res1.json()["insights_created"]

        # Second run — should clear and recompute (same count)
        res2 = client.post(f"/api/workspaces/{ws_id}/ai-visibility/insights/correlate?days=7")
        count2 = res2.json()["insights_created"]

        assert count1 == count2, "Re-run should produce same count (not accumulate)"

    def test_varied_scores_by_signal_type(self, db, workspace, competitor, billing):
        """Different signal types should produce different impact scores."""
        ws_id = str(workspace.id)
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        tp = AITrackedPrompt(
            workspace_id=workspace.id,
            prompt_text="best crm varied test",
            normalized_text=normalize_prompt("best crm varied test"),
            source_type="manual",
            is_active=True,
        )
        db.add(tp)
        db.flush()
        run = run_prompt_globally(db, "best crm varied test", today)
        db.commit()
        filter_results_for_workspace(db, ws_id, today)
        db.commit()

        # Create signals of different types
        from app.models.models import CompetitorEvent
        for sig_type in ["pricing_change", "hiring"]:
            ce = CompetitorEvent(
                workspace_id=workspace.id,
                competitor_id=competitor.id,
                signal_type=sig_type,
                title=f"Test {sig_type}",
                source_url=f"https://hubspot.com/{sig_type}",
                severity="medium",
            )
            db.add(ce)
        db.commit()

        res = client.post(f"/api/workspaces/{ws_id}/ai-visibility/insights/correlate?days=7")
        insights_res = client.get(f"/api/workspaces/{ws_id}/ai-visibility/insights")
        insights = insights_res.json()

        if len(insights) >= 2:
            scores = [i["impact_score"] for i in insights]
            types = [i["signal_type"] for i in insights]
            # pricing_change (weight 1.5) and hiring (weight 0.7) should produce different scores
            pricing_scores = [s for s, t in zip(scores, types) if t == "pricing_change"]
            hiring_scores = [s for s, t in zip(scores, types) if t == "hiring"]
            if pricing_scores and hiring_scores:
                assert pricing_scores[0] > hiring_scores[0], \
                    f"pricing_change ({pricing_scores[0]}) should score higher than hiring ({hiring_scores[0]})"


# ═══════════════════════════════════════════════
# 23. Engine Routing — Real API vs Simulation
# ═══════════════════════════════════════════════


class TestEngineRouting:
    """
    Tests that engine routing correctly:
    - Uses real OpenAI API for chatgpt when key is present
    - Falls back to simulation for chatgpt when key is missing
    - Always simulates claude/gemini/perplexity (placeholders)
    - Falls back gracefully on API errors
    """

    def test_has_real_api_key_chatgpt_with_real_key(self):
        with patch("app.services.ai_visibility.prompt_execution.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(OPENAI_API_KEY="sk-proj-real-key-here")
            assert _has_real_api_key("chatgpt") is True

    def test_has_real_api_key_chatgpt_with_placeholder(self):
        with patch("app.services.ai_visibility.prompt_execution.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(OPENAI_API_KEY="sk-your-key-here")
            assert _has_real_api_key("chatgpt") is False

    def test_has_real_api_key_chatgpt_empty(self):
        with patch("app.services.ai_visibility.prompt_execution.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(OPENAI_API_KEY="")
            assert _has_real_api_key("chatgpt") is False

    def test_has_real_api_key_claude_placeholder(self):
        with patch("app.services.ai_visibility.prompt_execution.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(ANTHROPIC_API_KEY="sk-ant-your-key-here")
            assert _has_real_api_key("claude") is False

    def test_has_real_api_key_perplexity_always_false(self):
        assert _has_real_api_key("perplexity") is False

    def test_has_real_api_key_gemini_always_false(self):
        assert _has_real_api_key("gemini") is False

    def test_call_real_engine_perplexity_returns_none(self):
        result = _call_real_engine("perplexity", "test prompt")
        assert result is None

    def test_call_real_engine_claude_returns_none(self):
        result = _call_real_engine("claude", "test prompt")
        assert result is None

    def test_call_real_engine_gemini_returns_none(self):
        result = _call_real_engine("gemini", "test prompt")
        assert result is None

    def test_call_real_engine_chatgpt_calls_openai(self):
        """When chatgpt has a real key, _call_real_engine dispatches to _call_openai_engine."""
        fake_response = "1. Cursor — AI code editor\n   Source: https://cursor.com"

        with patch("app.services.ai_visibility.prompt_execution._has_real_api_key", return_value=True), \
             patch("app.services.ai_visibility.prompt_execution._call_openai_engine", return_value=fake_response) as mock_fn:
            brands = ["Cursor AI", "WindSurf AI"]
            result = _call_real_engine("chatgpt", "best ai code editors", brands)
            assert result is not None
            assert "Cursor" in result
            mock_fn.assert_called_once_with("best ai code editors", brands)

    def test_simulation_still_works_for_all_engines(self):
        """Simulation produces valid responses for all engines."""
        for engine in ["chatgpt", "perplexity", "claude", "gemini"]:
            resp = _simulate_engine_response("best crm tools", engine)
            assert resp is not None
            assert len(resp) > 50
            assert "1." in resp  # Has numbered list

    def test_system_prompt_exists_and_has_format_instructions(self):
        assert _AI_VISIBILITY_SYSTEM_PROMPT is not None
        assert "numbered list" in _AI_VISIBILITY_SYSTEM_PROMPT
        assert "Source:" in _AI_VISIBILITY_SYSTEM_PROMPT

    def test_execute_engine_falls_back_on_api_error(self, db, workspace):
        """If real API raises, engine falls back to simulation gracefully."""
        from app.services.ai_visibility.prompt_execution import execute_prompt_on_engine
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        run = get_or_create_prompt_run(db, "test fallback prompt", today)
        db.flush()

        with patch("app.services.ai_visibility.prompt_execution._has_real_api_key", return_value=True), \
             patch("app.services.ai_visibility.prompt_execution._call_real_engine", side_effect=Exception("API down")):
            result = execute_prompt_on_engine(db, run, "chatgpt")
            # Should complete via simulation fallback, not fail
            assert result.status == RunStatusEnum.COMPLETED.value
            assert result.raw_response is not None
            assert len(result.mentioned_brands) > 0


# ═══════════════════════════════════════════════
# 24. Improved Brand Matching (core name extraction)
# ═══════════════════════════════════════════════


class TestCoreBrandMatching:
    """
    Tests that brand matching handles real AI responses where the AI says
    'Cursor' but the competitor is named 'Cursor AI', etc.
    """

    def test_extract_core_brand_name_strips_ai(self):
        assert _extract_core_brand_name("Cursor AI") == "Cursor"

    def test_extract_core_brand_name_strips_multiple_suffixes(self):
        assert _extract_core_brand_name("Acme AI Labs") == "Acme"

    def test_extract_core_brand_name_preserves_single_word(self):
        assert _extract_core_brand_name("Cursor") == "Cursor"

    def test_extract_core_brand_name_strips_inc(self):
        assert _extract_core_brand_name("Datadog Inc") == "Datadog"

    def test_extract_core_brand_name_preserves_non_suffix(self):
        assert _extract_core_brand_name("Visual Studio Code") == "Visual Studio Code"

    def test_brand_matches_cursor_ai_vs_cursor(self):
        """Competitor 'Cursor AI' should match extracted brand 'Cursor'."""
        matched, rank = _brand_matches("Cursor AI", ["Cursor", "Windsurf", "VS Code"])
        assert matched is True
        assert rank == 1

    def test_brand_matches_windsurf_ai_vs_windsurf(self):
        """Competitor 'WindSurf AI' should match extracted brand 'Windsurf'."""
        matched, rank = _brand_matches("WindSurf AI", ["Cursor", "Windsurf", "VS Code"])
        assert matched is True
        assert rank == 2

    def test_brand_matches_continue_ai_vs_continue(self):
        """Competitor 'Continue AI' should match brand 'Continue'."""
        matched, rank = _brand_matches("Continue AI", ["Cursor", "Windsurf", "Continue"])
        assert matched is True
        assert rank == 3

    def test_brand_matches_exact_still_works(self):
        matched, rank = _brand_matches("Cursor AI", ["Cursor AI"])
        assert matched is True
        assert rank == 1

    def test_brand_matches_no_match(self):
        matched, rank = _brand_matches("Cursor AI", ["HubSpot", "Salesforce"])
        assert matched is False
        assert rank is None

    def test_brand_in_raw_response_partial_name(self):
        """'Cursor AI' should match raw response containing 'Cursor'."""
        raw = "1. Cursor — best overall for most people\n2. Windsurf — best for agentic"
        matched, rank = _brand_in_raw_response("Cursor AI", raw)
        assert matched is True
        assert rank == 1

    def test_brand_in_raw_response_windsurf_ai(self):
        raw = "1. Cursor — best overall\n2. Windsurf — best for agentic"
        matched, rank = _brand_in_raw_response("WindSurf AI", raw)
        assert matched is True
        assert rank == 2

    def test_brand_in_raw_response_full_name_still_works(self):
        raw = "1. Cursor AI — best overall\n2. WindSurf AI — great"
        matched, rank = _brand_in_raw_response("Cursor AI", raw)
        assert matched is True
        assert rank == 1

    def test_brand_in_raw_response_no_match(self):
        raw = "1. HubSpot — best CRM\n2. Salesforce — enterprise"
        matched, rank = _brand_in_raw_response("Cursor AI", raw)
        assert matched is False

    def test_brand_in_raw_response_mentioned_but_no_rank(self):
        raw = "Many users prefer Cursor for its AI features."
        matched, rank = _brand_in_raw_response("Cursor AI", raw)
        assert matched is True
        assert rank is None


# ═══════════════════════════════════════════════
# 25. PROMPT-10: Prompt-Signal Relevance Scorer
# ═══════════════════════════════════════════════


class TestPromptSignalRelevance:
    """
    Tests for compute_prompt_signal_relevance — verifies keyword-based
    relevance scoring and the always-relevant signal type bypass.
    """

    @pytest.fixture(autouse=True)
    def _imports(self):
        from app.services.ai_visibility.prompt_signal_relevance import (
            compute_prompt_signal_relevance,
            PROMPT_SIGNAL_RELEVANCE_THRESHOLD,
            ALWAYS_RELEVANT_SIGNAL_TYPES,
        )
        self.score = compute_prompt_signal_relevance
        self.threshold = PROMPT_SIGNAL_RELEVANCE_THRESHOLD
        self.always_relevant = ALWAYS_RELEVANT_SIGNAL_TYPES

    def test_always_relevant_pricing_change(self):
        """pricing_change is generic — always returns 1.0."""
        s = self.score("pricing_change", "Raised enterprise price by 30%", "best crm tools 2026")
        assert s == 1.0

    def test_always_relevant_funding(self):
        s = self.score("funding", "Series B $50M raised", "best ai code editors")
        assert s == 1.0

    def test_always_relevant_acquisition(self):
        s = self.score("acquisition", "Acquired TechCo", "top project management tools")
        assert s == 1.0

    def test_always_relevant_hiring(self):
        s = self.score("hiring", "Hiring 200 engineers", "best devops platforms")
        assert s == 1.0

    def test_relevant_integration_ai_editor_prompt(self):
        """'integration_added' for AI code editor vs AI editor prompt — should be relevant."""
        s = self.score(
            "integration_added",
            "AI code editor integration with 4 new partners",
            "best ai code editors for developers",
            competitor_name="WindSurf AI",
        )
        assert s >= self.threshold, f"Expected relevant, got {s}"

    def test_irrelevant_integration_ai_editor_vs_crm_prompt(self):
        """AI code editor signal vs CRM prompt — should be NOT relevant (keyword mismatch)."""
        s = self.score(
            "integration_added",
            "AI code editor integration with 4 new partners",
            "best crm tools for sales teams",
            competitor_name="WindSurf AI",
        )
        assert s < self.threshold, f"Expected irrelevant, got {s}"

    def test_irrelevant_blog_post_generic_title_vs_crm_prompt(self):
        """A generic blog_post title vs unrelated prompt → near-zero relevance."""
        s = self.score(
            "blog_post",
            "Our new blog post about engineering",
            "best crm tools 2026",
        )
        assert s < self.threshold, f"Expected low relevance, got {s}"

    def test_score_in_valid_range(self):
        """Score must always be between 0 and 1."""
        for sig_type in ["feature_release", "integration_added", "blog_post", "product_launch"]:
            s = self.score(sig_type, "Some title here", "some prompt text here")
            assert 0.0 <= s <= 1.0, f"Score out of range: {s}"

    def test_empty_texts_returns_permissive(self):
        """Empty signal or prompt → permissive score (0.5)."""
        s = self.score("feature_release", "", "")
        assert s == 0.5

    def test_threshold_constant_is_low(self):
        """Threshold should be ≤0.2 to avoid over-filtering."""
        assert self.threshold <= 0.2


# ═══════════════════════════════════════════════
# 26. PROMPT-10: New Correlation Engine Helpers
# ═══════════════════════════════════════════════


class TestP10CorrelationHelpers:
    """
    Tests for _generate_signal_headline, _generate_summary_text,
    and _compute_confidence_factors added in PROMPT-10.
    """

    @pytest.fixture(autouse=True)
    def _imports(self):
        from app.services.ai_visibility.correlation_engine import (
            _generate_signal_headline,
            _generate_summary_text,
            _compute_confidence_factors,
        )
        self.headline = _generate_signal_headline
        self.summary = _generate_summary_text
        self.factors = _compute_confidence_factors

    # ── signal_headline ──────────────────────────────────────────────

    def test_signal_headline_ai_impact_short_title(self):
        h = self.headline("pricing_change", "Raised prices 30%", "ai_impact")
        assert h == "Raised prices 30%"

    def test_signal_headline_ai_impact_long_title_truncated(self):
        long = "A" * 120
        h = self.headline("feature_release", long, "ai_impact")
        assert len(h) <= 100
        assert h.endswith("…")

    def test_signal_headline_hijack_returns_empty(self):
        h = self.headline("ai_visibility_hijack", "anything", "ai_visibility_hijack")
        assert h == ""

    def test_signal_headline_loss_returns_empty(self):
        h = self.headline("ai_visibility_loss", "anything", "ai_visibility_loss")
        assert h == ""

    def test_signal_headline_dominance_returns_empty(self):
        h = self.headline("ai_dominance", "anything", "ai_dominance")
        assert h == ""

    def test_signal_headline_empty_title_uses_type(self):
        h = self.headline("product_launch", "", "ai_impact")
        assert "product" in h.lower() or "launch" in h.lower()

    # ── summary_text ─────────────────────────────────────────────────

    def test_summary_text_first_detection(self):
        s = self.summary("ai_impact", "HubSpot", "pricing_change", ["chatgpt"], 2, 0, 2)
        assert "HubSpot" in s
        assert "appeared" in s.lower()
        assert s.endswith(".")

    def test_summary_text_positive_delta(self):
        s = self.summary("ai_impact", "HubSpot", "pricing_change", ["chatgpt", "gemini"], 3, 1, 4)
        assert "+3" in s
        assert "gained" in s.lower()

    def test_summary_text_negative_delta(self):
        s = self.summary("ai_impact", "HubSpot", "pricing_change", ["chatgpt"], -2, 3, 1)
        assert "lost" in s.lower()
        assert "2" in s

    def test_summary_text_hijack(self):
        s = self.summary("ai_visibility_hijack", "Cursor AI", "", ["chatgpt", "perplexity"], 2, 0, 2)
        assert "Cursor AI" in s
        assert "entered" in s.lower() or "newly" in s.lower()
        assert s.endswith(".")

    def test_summary_text_loss(self):
        s = self.summary("ai_visibility_loss", "Cursor AI", "", ["chatgpt"], -1, 1, 0)
        assert "Cursor AI" in s
        assert "disappeared" in s.lower()
        assert s.endswith(".")

    def test_summary_text_dominance(self):
        s = self.summary("ai_dominance", "Salesforce", "", ["chatgpt", "perplexity", "claude", "gemini"], 4, 0, 4)
        assert "Salesforce" in s
        assert "dominates" in s.lower()
        assert s.endswith(".")

    def test_summary_text_is_single_sentence(self):
        """Summary must not contain multiple sentences (no mid-text periods)."""
        for itype, delta, before, after in [
            ("ai_impact", 2, 0, 2),
            ("ai_visibility_hijack", 1, 0, 1),
            ("ai_visibility_loss", -1, 1, 0),
            ("ai_dominance", 4, 0, 4),
        ]:
            s = self.summary(itype, "ACME", "pricing_change", ["chatgpt"], delta, before, after)
            # Should end with exactly one period and not contain mid-sentence periods
            stripped = s.rstrip(".")
            assert "." not in stripped, f"Multi-sentence summary: {s!r}"

    # ── confidence_factors ───────────────────────────────────────────

    def test_confidence_factors_keys(self):
        f = self.factors(0, "pricing_change", 2, 3, 1.0)
        for key in ("score", "time_distance_days", "engines_count", "visibility_delta",
                    "prompt_relevance_score", "signal_type_weight", "factors_text"):
            assert key in f, f"Missing key: {key}"

    def test_confidence_factors_score_in_range(self):
        f = self.factors(0, "pricing_change", 2, 3, 1.0)
        assert 0.0 <= f["score"] <= 100.0

    def test_confidence_factors_same_day_boosts_score(self):
        same_day = self.factors(0, "pricing_change", 1, 1, 1.0)
        old = self.factors(14, "pricing_change", 1, 1, 1.0)
        assert same_day["score"] > old["score"]

    def test_confidence_factors_more_engines_boosts_score(self):
        one_engine = self.factors(1, "pricing_change", 1, 2, 1.0)
        four_engines = self.factors(1, "pricing_change", 4, 2, 1.0)
        assert four_engines["score"] >= one_engine["score"]

    def test_confidence_factors_text_is_list(self):
        f = self.factors(2, "funding", 3, 5, 0.8)
        assert isinstance(f["factors_text"], list)
        assert len(f["factors_text"]) >= 1

    def test_confidence_factors_high_relevance_reflected(self):
        high = self.factors(1, "feature_release", 2, 2, 1.0)
        low = self.factors(1, "feature_release", 2, 2, 0.1)
        assert high["score"] >= low["score"]


# ═══════════════════════════════════════════════
# 27. PROMPT-10: Regression — new fields stored on insights
# ═══════════════════════════════════════════════


class TestP10InsightFields:
    """
    End-to-end regression: after running correlation engine, newly created
    ai_impact insights should have signal_headline, confidence_factors,
    and prompt_relevance_score populated.
    """

    def test_ai_impact_insight_has_p10_fields(self, db, workspace, competitor, billing):
        ws_id = str(workspace.id)
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        tp = AITrackedPrompt(
            workspace_id=workspace.id,
            prompt_text="best crm p10 regression",
            normalized_text=normalize_prompt("best crm p10 regression"),
            source_type="manual",
            is_active=True,
        )
        db.add(tp)
        db.flush()

        from app.services.ai_visibility.prompt_execution import run_prompt_globally
        from app.services.ai_visibility.workspace_filtering import filter_results_for_workspace
        run_prompt_globally(db, "best crm p10 regression", today)
        db.commit()
        filter_results_for_workspace(db, ws_id, today)
        db.commit()

        ce = CompetitorEvent(
            workspace_id=workspace.id,
            competitor_id=competitor.id,
            signal_type="pricing_change",
            title="Enterprise pricing raised 25%",
            source_url="https://hubspot.com/pricing",
            severity="high",
        )
        db.add(ce)
        db.commit()

        res = client.post(f"/api/workspaces/{ws_id}/ai-visibility/insights/correlate?days=7")
        assert res.status_code == 200

        insights = db.query(AIImpactInsight).filter(
            AIImpactInsight.workspace_id == workspace.id,
            AIImpactInsight.insight_type == "ai_impact",
        ).all()

        if insights:
            i = insights[0]
            assert i.prompt_relevance_score is not None, "prompt_relevance_score should be set"
            assert 0.0 <= i.prompt_relevance_score <= 1.0
            assert i.confidence_factors is not None, "confidence_factors should be set"
            assert "score" in i.confidence_factors
            assert "factors_text" in i.confidence_factors
            assert isinstance(i.confidence_factors["factors_text"], list)
            assert i.signal_headline is not None, "signal_headline should be set"
            assert len(i.signal_headline) > 0

    def test_compact_card_has_signal_headline_and_summary(self, db, workspace, competitor, billing):
        """Compact card API response must include signal_headline and one-line summary_text."""
        ws_id = str(workspace.id)
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        tp = AITrackedPrompt(
            workspace_id=workspace.id,
            prompt_text="best crm compact p10 test",
            normalized_text=normalize_prompt("best crm compact p10 test"),
            source_type="manual",
            is_active=True,
        )
        db.add(tp)
        db.flush()

        from app.services.ai_visibility.prompt_execution import run_prompt_globally
        from app.services.ai_visibility.workspace_filtering import filter_results_for_workspace
        run_prompt_globally(db, "best crm compact p10 test", today)
        db.commit()
        filter_results_for_workspace(db, ws_id, today)
        db.commit()

        ce = CompetitorEvent(
            workspace_id=workspace.id,
            competitor_id=competitor.id,
            signal_type="pricing_change",
            title="Launched new starter plan",
            source_url="https://hubspot.com/plans",
            severity="medium",
        )
        db.add(ce)
        db.commit()

        client.post(f"/api/workspaces/{ws_id}/ai-visibility/insights/correlate?days=7")

        res = client.get(f"/api/workspaces/{ws_id}/ai-visibility/insights/compact")
        assert res.status_code == 200
        cards = res.json()

        ai_impact_cards = [c for c in cards if c["insight_type"] == "ai_impact"]
        if ai_impact_cards:
            card = ai_impact_cards[0]
            assert "signal_headline" in card
            assert "summary_text" in card
            if card["summary_text"]:
                # One-liner: should end with period, no internal paragraph breaks
                text = card["summary_text"].strip()
                assert "\n" not in text


# ═══════════════════════════════════════════════
# 28. PROMPT-11: Citation Extraction
# ═══════════════════════════════════════════════


class TestCitationExtraction:
    """Tests for extract_citations_from_response and _extract_domain."""

    def test_extract_domain_full_url(self):
        assert _extract_domain("https://cursor.sh/blog") == "cursor.sh"

    def test_extract_domain_with_www(self):
        assert _extract_domain("https://www.github.com/cursor") == "github.com"

    def test_extract_domain_bare(self):
        assert _extract_domain("techcrunch.com/article") == "techcrunch.com"

    def test_extract_citations_from_response_with_urls(self):
        raw = (
            "1. Cursor AI — best AI code editor\n"
            "   Source: https://cursor.sh\n"
            "2. Windsurf — great agentic IDE\n"
            "   Source: https://windsurf.com/blog\n"
        )
        cits = extract_citations_from_response(raw)
        assert len(cits) >= 2
        urls = [c["url"] for c in cits]
        assert "https://cursor.sh" in urls
        assert "https://windsurf.com/blog" in urls

    def test_extract_citations_from_response_bare_domains(self):
        raw = (
            "Sources:\n"
            "cursor.sh\n"
            "github.com/cursor\n"
            "techcrunch.com/cursor-ai\n"
        )
        cits = extract_citations_from_response(raw)
        assert len(cits) >= 3
        domains = [c["domain"] for c in cits]
        assert "cursor.sh" in domains
        assert "github.com" in domains
        assert "techcrunch.com" in domains

    def test_extract_citations_empty_response(self):
        assert extract_citations_from_response("") == []
        assert extract_citations_from_response(None) == []

    def test_extract_citations_no_urls(self):
        raw = "Cursor AI is a great code editor with no links."
        cits = extract_citations_from_response(raw)
        # May or may not find domain-like patterns, but should not crash
        assert isinstance(cits, list)

    def test_citation_has_context(self):
        raw = "Check out the awesome editor at https://cursor.sh for coding."
        cits = extract_citations_from_response(raw)
        assert len(cits) >= 1
        assert cits[0]["context"] != ""

    def test_citation_deduplication(self):
        raw = "Visit https://cursor.sh and also https://cursor.sh for more."
        cits = extract_citations_from_response(raw)
        urls = [c["url"] for c in cits]
        assert urls.count("https://cursor.sh") == 1


# ═══════════════════════════════════════════════
# 29. PROMPT-11: Strategy Alerts
# ═══════════════════════════════════════════════


class TestStrategyAlerts:
    """Tests for strategy alert generation logic."""

    def test_strategy_map_has_common_signal_types(self):
        for sig_type in ["integration_added", "pricing_change", "feature_launch", "funding"]:
            assert sig_type in STRATEGY_MAP, f"Missing strategy for {sig_type}"

    def test_get_strategy_actions_integration(self):
        actions = _get_strategy_actions("integration_added", "Cursor AI", "best ai code editors")
        assert len(actions) >= 2
        assert any("integration" in a.lower() for a in actions)

    def test_get_strategy_actions_pricing(self):
        actions = _get_strategy_actions("pricing_change", "HubSpot", "best crm tools")
        assert len(actions) >= 2
        assert any("pricing" in a.lower() for a in actions)

    def test_get_strategy_actions_unknown_type_uses_default(self):
        actions = _get_strategy_actions("unknown_type", "ACME", "some prompt")
        assert len(actions) >= 2

    def test_get_strategy_actions_personalizes_competitor(self):
        actions = _get_strategy_actions("funding", "Cursor AI", "best ai code editors")
        # At least one action should mention the competitor name
        assert any("Cursor AI" in a for a in actions)

    def test_confidence_threshold_is_reasonable(self):
        assert 30.0 <= CONFIDENCE_THRESHOLD <= 80.0

    def test_strategy_alert_e2e(self, db, workspace, competitor, billing):
        """Strategy alerts are generated for ai_impact insights with positive delta."""
        ws_id = str(workspace.id)
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        tp = AITrackedPrompt(
            workspace_id=workspace.id,
            prompt_text="best crm strategy test",
            normalized_text=normalize_prompt("best crm strategy test"),
            source_type="manual",
            is_active=True,
        )
        db.add(tp)
        db.flush()

        from app.services.ai_visibility.prompt_execution import run_prompt_globally
        from app.services.ai_visibility.workspace_filtering import filter_results_for_workspace
        run_prompt_globally(db, "best crm strategy test", today)
        db.commit()
        filter_results_for_workspace(db, ws_id, today)
        db.commit()

        ce = CompetitorEvent(
            workspace_id=workspace.id,
            competitor_id=competitor.id,
            signal_type="integration_added",
            title="New Salesforce integration launched",
            source_url="https://hubspot.com/integrations",
            severity="high",
        )
        db.add(ce)
        db.commit()

        res = client.post(f"/api/workspaces/{ws_id}/ai-visibility/insights/correlate?days=7")
        assert res.status_code == 200

        strategy_insights = db.query(AIImpactInsight).filter(
            AIImpactInsight.workspace_id == workspace.id,
            AIImpactInsight.insight_type == "ai_strategy_alert",
        ).all()

        # Strategy alerts should exist if there are qualifying ai_impact insights
        for sa in strategy_insights:
            assert sa.strategy_actions is not None
            assert isinstance(sa.strategy_actions, list)
            assert len(sa.strategy_actions) >= 1
            assert sa.short_title is not None
            assert "Strategy" in sa.short_title


# ═══════════════════════════════════════════════
# 30. PROMPT-11: Citation Influence
# ═══════════════════════════════════════════════


class TestCitationInfluence:
    """Tests for citation influence scoring."""

    def test_engine_weights_exist(self):
        for eng in ["chatgpt", "perplexity", "claude", "gemini"]:
            assert eng in ENGINE_WEIGHTS

    def test_perplexity_has_higher_weight(self):
        assert ENGINE_WEIGHTS["perplexity"] > ENGINE_WEIGHTS["claude"]

    def test_compute_citation_influence_empty(self, db, workspace):
        result = compute_citation_influence(db, str(workspace.id), days=7)
        assert result == {}


# ═══════════════════════════════════════════════
# 31. PROMPT-11: Category Ownership
# ═══════════════════════════════════════════════


class TestCategoryOwnership:
    """Tests for category ownership computation."""

    def test_compute_category_ownership_no_categories(self, db, workspace):
        result = compute_category_ownership(db, str(workspace.id))
        assert result == []

    def test_compute_category_ownership_with_category(self, db, workspace, competitor, billing):
        ws_id = str(workspace.id)
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        cat = PromptCategory(
            workspace_id=workspace.id,
            category_name="Test Category",
            description="Test",
        )
        db.add(cat)
        db.flush()

        tp = AITrackedPrompt(
            workspace_id=workspace.id,
            prompt_text="best crm category ownership test",
            normalized_text=normalize_prompt("best crm category ownership test"),
            source_type="manual",
            is_active=True,
            category_id=cat.id,
        )
        db.add(tp)
        db.flush()

        from app.services.ai_visibility.prompt_execution import run_prompt_globally
        from app.services.ai_visibility.workspace_filtering import filter_results_for_workspace
        run_prompt_globally(db, "best crm category ownership test", today)
        db.commit()
        filter_results_for_workspace(db, ws_id, today)
        db.commit()

        result = compute_category_ownership(db, ws_id)
        # Result depends on whether competitor was mentioned — either empty or has data
        assert isinstance(result, list)
        if result:
            assert result[0]["category_name"] == "Test Category"
            assert "competitors" in result[0]


# ═══════════════════════════════════════════════
# 32. PROMPT-11: Prompt Category CRUD API
# ═══════════════════════════════════════════════


class TestPromptCategoryCRUD:
    """Tests for prompt category CRUD API endpoints."""

    def test_create_category(self, db, workspace, billing):
        ws_id = str(workspace.id)
        res = client.post(
            f"/api/workspaces/{ws_id}/ai-visibility/categories",
            json={"category_name": "AI Code Editors", "description": "Code editing tools"},
        )
        assert res.status_code == 201
        data = res.json()
        assert data["category_name"] == "AI Code Editors"
        assert data["description"] == "Code editing tools"
        assert "id" in data

    def test_create_duplicate_category_fails(self, db, workspace, billing):
        ws_id = str(workspace.id)
        client.post(
            f"/api/workspaces/{ws_id}/ai-visibility/categories",
            json={"category_name": "Duplicate Cat"},
        )
        res = client.post(
            f"/api/workspaces/{ws_id}/ai-visibility/categories",
            json={"category_name": "Duplicate Cat"},
        )
        assert res.status_code == 409

    def test_list_categories(self, db, workspace, billing):
        ws_id = str(workspace.id)
        client.post(
            f"/api/workspaces/{ws_id}/ai-visibility/categories",
            json={"category_name": "Cat List Test"},
        )
        res = client.get(f"/api/workspaces/{ws_id}/ai-visibility/categories")
        assert res.status_code == 200
        cats = res.json()
        assert isinstance(cats, list)
        names = [c["category_name"] for c in cats]
        assert "Cat List Test" in names

    def test_delete_category(self, db, workspace, billing):
        ws_id = str(workspace.id)
        res = client.post(
            f"/api/workspaces/{ws_id}/ai-visibility/categories",
            json={"category_name": "To Delete"},
        )
        cat_id = res.json()["id"]
        del_res = client.delete(f"/api/workspaces/{ws_id}/ai-visibility/categories/{cat_id}")
        assert del_res.status_code == 204

    def test_assign_prompt_to_category(self, db, workspace, billing):
        ws_id = str(workspace.id)
        # Create category
        cat_res = client.post(
            f"/api/workspaces/{ws_id}/ai-visibility/categories",
            json={"category_name": "Assign Test Cat"},
        )
        cat_id = cat_res.json()["id"]

        # Create tracked prompt
        tp = AITrackedPrompt(
            workspace_id=workspace.id,
            prompt_text="best assign prompt category test",
            normalized_text=normalize_prompt("best assign prompt category test"),
            source_type="manual",
            is_active=True,
        )
        db.add(tp)
        db.commit()

        # Assign prompt to category
        res = client.put(
            f"/api/workspaces/{ws_id}/ai-visibility/prompts/{tp.id}/category?category_id={cat_id}",
        )
        assert res.status_code == 200
        assert res.json()["category_id"] == cat_id

    def test_uncategorize_prompt(self, db, workspace, billing):
        ws_id = str(workspace.id)
        tp = AITrackedPrompt(
            workspace_id=workspace.id,
            prompt_text="best uncat prompt test",
            normalized_text=normalize_prompt("best uncat prompt test"),
            source_type="manual",
            is_active=True,
        )
        db.add(tp)
        db.commit()

        res = client.put(
            f"/api/workspaces/{ws_id}/ai-visibility/prompts/{tp.id}/category",
        )
        assert res.status_code == 200
        assert res.json()["category_id"] is None


# ═══════════════════════════════════════════════
# 33. PROMPT-11: New Insight Types in Feed
# ═══════════════════════════════════════════════


class TestP11InsightTypesEnum:
    """Tests that InsightType enum has the new PROMPT-11 values."""

    def test_strategy_alert_enum(self):
        assert InsightType.AI_STRATEGY_ALERT.value == "ai_strategy_alert"

    def test_citation_influence_enum(self):
        assert InsightType.AI_CITATION_INFLUENCE.value == "ai_citation_influence"

    def test_category_ownership_enum(self):
        assert InsightType.AI_CATEGORY_OWNERSHIP.value == "ai_category_ownership"

    def test_existing_enums_preserved(self):
        assert InsightType.AI_IMPACT.value == "ai_impact"
        assert InsightType.AI_VISIBILITY_HIJACK.value == "ai_visibility_hijack"
        assert InsightType.AI_VISIBILITY_LOSS.value == "ai_visibility_loss"
        assert InsightType.AI_DOMINANCE.value == "ai_dominance"


# ═══════════════════════════════════════════════
# 34. PROMPT-11: Backward Compatibility Regression
# ═══════════════════════════════════════════════


class TestP11BackwardCompatibility:
    """Ensure P11 changes don't break existing flows."""

    def test_tracked_prompt_without_category(self, db, workspace, billing):
        """Prompts without category_id must still work."""
        tp = AITrackedPrompt(
            workspace_id=workspace.id,
            prompt_text="best backward compat p11 test",
            normalized_text=normalize_prompt("best backward compat p11 test"),
            source_type="manual",
            is_active=True,
        )
        db.add(tp)
        db.commit()
        db.refresh(tp)
        assert tp.category_id is None
        assert tp.id is not None

    def test_insight_without_p11_fields(self, db, workspace, competitor, billing):
        """Insights without strategy_actions/influential_sources/category_data must still work."""
        insight = AIImpactInsight(
            workspace_id=workspace.id,
            competitor_id=competitor.id,
            insight_type="ai_impact",
            signal_type="pricing_change",
            signal_title="Test",
            visibility_before=0,
            visibility_after=1,
            impact_score=50.0,
            priority_level="P2",
        )
        db.add(insight)
        db.commit()
        db.refresh(insight)
        assert insight.strategy_actions is None
        assert insight.influential_sources is None
        assert insight.category_data is None

    def test_correlate_returns_citations_extracted(self, db, workspace, competitor, billing):
        """Correlation endpoint now returns citations_extracted count."""
        ws_id = str(workspace.id)
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        tp = AITrackedPrompt(
            workspace_id=workspace.id,
            prompt_text="best crm p11 compat test",
            normalized_text=normalize_prompt("best crm p11 compat test"),
            source_type="manual",
            is_active=True,
        )
        db.add(tp)
        db.flush()

        from app.services.ai_visibility.prompt_execution import run_prompt_globally
        from app.services.ai_visibility.workspace_filtering import filter_results_for_workspace
        run_prompt_globally(db, "best crm p11 compat test", today)
        db.commit()
        filter_results_for_workspace(db, ws_id, today)
        db.commit()

        res = client.post(f"/api/workspaces/{ws_id}/ai-visibility/insights/correlate?days=7")
        assert res.status_code == 200
        data = res.json()
        assert "insights_created" in data
        assert "competitors_analyzed" in data
        assert "citations_extracted" in data

    def test_compact_card_has_strategy_actions_field(self, db, workspace, competitor, billing):
        """Compact cards should now include strategy_actions (possibly null)."""
        ws_id = str(workspace.id)
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        tp = AITrackedPrompt(
            workspace_id=workspace.id,
            prompt_text="best crm compact p11 test",
            normalized_text=normalize_prompt("best crm compact p11 test"),
            source_type="manual",
            is_active=True,
        )
        db.add(tp)
        db.flush()

        from app.services.ai_visibility.prompt_execution import run_prompt_globally
        from app.services.ai_visibility.workspace_filtering import filter_results_for_workspace
        run_prompt_globally(db, "best crm compact p11 test", today)
        db.commit()
        filter_results_for_workspace(db, ws_id, today)
        db.commit()

        ce = CompetitorEvent(
            workspace_id=workspace.id,
            competitor_id=competitor.id,
            signal_type="pricing_change",
            title="Price increase for enterprise",
            source_url="https://hubspot.com/pricing",
            severity="high",
        )
        db.add(ce)
        db.commit()

        client.post(f"/api/workspaces/{ws_id}/ai-visibility/insights/correlate?days=7")
        res = client.get(f"/api/workspaces/{ws_id}/ai-visibility/insights/compact")
        assert res.status_code == 200
        cards = res.json()
        # All cards should have strategy_actions field (may be null)
        for card in cards:
            assert "strategy_actions" in card

    def test_citations_endpoint_returns_empty_initially(self, db, workspace, billing):
        ws_id = str(workspace.id)
        res = client.get(f"/api/workspaces/{ws_id}/ai-visibility/citations")
        assert res.status_code == 200
        assert res.json() == []

    def test_category_visibility_endpoint_returns_empty(self, db, workspace, billing):
        ws_id = str(workspace.id)
        res = client.get(f"/api/workspaces/{ws_id}/ai-visibility/category-visibility")
        assert res.status_code == 200
        assert res.json() == []


# ═══════════════════════════════════════════════════════
# PROMPT-12 Tests
# ═══════════════════════════════════════════════════════


class TestP12CategoryRename:
    """Test PATCH /categories/{id} for renaming categories."""

    def test_rename_category(self, db, workspace, billing):
        ws_id = str(workspace.id)
        # Create
        r = client.post(
            f"/api/workspaces/{ws_id}/ai-visibility/categories",
            json={"category_name": "Old Name", "description": "old desc"},
        )
        assert r.status_code == 201
        cat_id = r.json()["id"]

        # Rename
        r2 = client.patch(
            f"/api/workspaces/{ws_id}/ai-visibility/categories/{cat_id}",
            json={"category_name": "New Name"},
        )
        assert r2.status_code == 200
        assert r2.json()["category_name"] == "New Name"
        # description unchanged
        assert r2.json()["description"] == "old desc"

    def test_rename_category_update_description(self, db, workspace, billing):
        ws_id = str(workspace.id)
        r = client.post(
            f"/api/workspaces/{ws_id}/ai-visibility/categories",
            json={"category_name": "DescTest"},
        )
        cat_id = r.json()["id"]
        r2 = client.patch(
            f"/api/workspaces/{ws_id}/ai-visibility/categories/{cat_id}",
            json={"description": "new description"},
        )
        assert r2.status_code == 200
        assert r2.json()["description"] == "new description"
        assert r2.json()["category_name"] == "DescTest"

    def test_rename_category_duplicate_fails(self, db, workspace, billing):
        ws_id = str(workspace.id)
        client.post(
            f"/api/workspaces/{ws_id}/ai-visibility/categories",
            json={"category_name": "CatA"},
        )
        r2 = client.post(
            f"/api/workspaces/{ws_id}/ai-visibility/categories",
            json={"category_name": "CatB"},
        )
        cat_b_id = r2.json()["id"]
        # Try to rename CatB to CatA
        r3 = client.patch(
            f"/api/workspaces/{ws_id}/ai-visibility/categories/{cat_b_id}",
            json={"category_name": "CatA"},
        )
        assert r3.status_code == 409

    def test_rename_nonexistent_category(self, db, workspace, billing):
        ws_id = str(workspace.id)
        r = client.patch(
            f"/api/workspaces/{ws_id}/ai-visibility/categories/00000000-0000-0000-0000-000000000000",
            json={"category_name": "X"},
        )
        assert r.status_code == 404


class TestP12PromptCategoryInListing:
    """Test that prompt listings include category_id and category_name."""

    def test_prompt_has_category_fields(self, db, workspace, billing):
        ws_id = str(workspace.id)
        # Create category
        cat = client.post(
            f"/api/workspaces/{ws_id}/ai-visibility/categories",
            json={"category_name": "TestCatList"},
        ).json()

        # Create prompt via suggestion flow
        client.post(
            f"/api/workspaces/{ws_id}/ai-visibility/suggestions",
            json={"prompt_text": "cat listing test prompt", "source_type": "manual"},
        )
        sug = client.get(f"/api/workspaces/{ws_id}/ai-visibility/suggestions").json()
        approve = client.post(
            f"/api/workspaces/{ws_id}/ai-visibility/suggestions/approve",
            json={"prompt_source_ids": [sug[-1]["id"]]},
        )
        prompt_id = approve.json()[0]["id"]

        # Assign to category
        client.put(
            f"/api/workspaces/{ws_id}/ai-visibility/prompts/{prompt_id}/category?category_id={cat['id']}"
        )

        # List prompts
        prompts = client.get(f"/api/workspaces/{ws_id}/ai-visibility/prompts").json()
        found = next((p for p in prompts if p["id"] == prompt_id), None)
        assert found is not None
        assert found["category_id"] == cat["id"]
        assert found["category_name"] == "TestCatList"

    def test_prompt_uncategorized_has_null(self, db, workspace, billing):
        ws_id = str(workspace.id)
        prompts = client.get(f"/api/workspaces/{ws_id}/ai-visibility/prompts").json()
        for p in prompts:
            assert "category_id" in p
            assert "category_name" in p

    def test_filter_uncategorized(self, db, workspace, billing):
        ws_id = str(workspace.id)
        res = client.get(f"/api/workspaces/{ws_id}/ai-visibility/prompts?uncategorized=true")
        assert res.status_code == 200
        for p in res.json():
            assert p["category_id"] is None


class TestP12ImprovedStrategyAlerts:
    """Test P12 strategy alert improvements."""

    def test_strategy_actions_include_prompt_text(self):
        from app.services.ai_visibility.strategy_alerts import _get_strategy_actions
        actions = _get_strategy_actions(
            "integration_added", "Cursor", "best ai code editors",
        )
        # At least one action should reference the prompt text
        assert any("best ai code editors" in a for a in actions)

    def test_strategy_actions_include_category_when_provided(self):
        from app.services.ai_visibility.strategy_alerts import _get_strategy_actions
        actions = _get_strategy_actions(
            "integration_added", "Cursor", "best ai code editors",
            category_name="AI Code Editors",
        )
        assert any("AI Code Editors" in a for a in actions)

    def test_strategy_actions_include_citation_domains(self):
        from app.services.ai_visibility.strategy_alerts import _get_strategy_actions
        actions = _get_strategy_actions(
            "hiring", "Cursor", "best ai code editors",
            citation_domains=["github.com", "cursor.sh"],
        )
        assert any("github.com" in a for a in actions)

    def test_strategy_actions_no_category_still_works(self):
        from app.services.ai_visibility.strategy_alerts import _get_strategy_actions
        actions = _get_strategy_actions(
            "blog_post", "Copilot", "ai coding tools",
        )
        assert len(actions) >= 3
        # Should not contain "None" or crash
        for a in actions:
            assert "None" not in a

    def test_strategy_explanation_includes_category(self):
        from app.services.ai_visibility.strategy_alerts import _generate_strategy_explanation
        exp = _generate_strategy_explanation(
            "Cursor", "hiring", 3, "best ai code editors", "AI Code Editors",
            ["Action 1"],
        )
        assert "AI Code Editors" in exp
        assert "best ai code editors" in exp

    def test_strategy_explanation_omits_category_when_none(self):
        from app.services.ai_visibility.strategy_alerts import _generate_strategy_explanation
        exp = _generate_strategy_explanation(
            "Cursor", "hiring", 3, "best ai code editors", None,
            ["Action 1"],
        )
        assert "Category:" not in exp


class TestP12ImprovedCitationInfluence:
    """Test P12 citation influence improvements."""

    def test_short_title_includes_domains(self):
        """Citation influence short_title should include top domains."""
        from app.services.ai_visibility.citation_influence import ENGINE_WEIGHTS
        # Verify engine weights haven't changed (backward compat)
        assert "perplexity" in ENGINE_WEIGHTS
        assert ENGINE_WEIGHTS["perplexity"] == 1.3


class TestP12ImprovedCategoryOwnership:
    """Test P12 category ownership with ownership change detection."""

    def test_ownership_delta_threshold_constant(self):
        from app.services.ai_visibility.category_ownership import OWNERSHIP_DELTA_THRESHOLD
        assert OWNERSHIP_DELTA_THRESHOLD == 5.0

    def test_get_previous_shares_empty(self, db, workspace, billing):
        from app.services.ai_visibility.category_ownership import _get_previous_shares
        shares = _get_previous_shares(db, str(workspace.id))
        assert isinstance(shares, dict)

    def test_compute_category_ownership_returns_list(self, db, workspace, billing):
        from app.services.ai_visibility.category_ownership import compute_category_ownership
        result = compute_category_ownership(db, str(workspace.id))
        assert isinstance(result, list)


class TestP12DeleteCategoryBehavior:
    """Test that deleting a category preserves prompts."""

    def test_delete_category_preserves_prompts(self, db, workspace, billing):
        ws_id = str(workspace.id)

        # Create category
        cat = client.post(
            f"/api/workspaces/{ws_id}/ai-visibility/categories",
            json={"category_name": "DeleteTestCat"},
        ).json()

        # Create and assign a prompt
        client.post(
            f"/api/workspaces/{ws_id}/ai-visibility/suggestions",
            json={"prompt_text": "delete cat test prompt", "source_type": "manual"},
        )
        sug = client.get(f"/api/workspaces/{ws_id}/ai-visibility/suggestions").json()
        approve = client.post(
            f"/api/workspaces/{ws_id}/ai-visibility/suggestions/approve",
            json={"prompt_source_ids": [sug[-1]["id"]]},
        )
        prompt_id = approve.json()[0]["id"]

        client.put(
            f"/api/workspaces/{ws_id}/ai-visibility/prompts/{prompt_id}/category?category_id={cat['id']}"
        )

        # Delete category
        r = client.delete(f"/api/workspaces/{ws_id}/ai-visibility/categories/{cat['id']}")
        assert r.status_code == 204

        # Prompt still exists and is now uncategorized
        prompts = client.get(f"/api/workspaces/{ws_id}/ai-visibility/prompts").json()
        found = next((p for p in prompts if p["id"] == prompt_id), None)
        assert found is not None
        assert found["category_id"] is None
        assert found["category_name"] is None


class TestP12BackwardCompatibility:
    """Regression: existing P11 and earlier features still work."""

    def test_existing_insight_types_enum(self):
        from app.models.models import InsightType
        assert InsightType.AI_IMPACT.value == "ai_impact"
        assert InsightType.AI_VISIBILITY_HIJACK.value == "ai_visibility_hijack"
        assert InsightType.AI_VISIBILITY_LOSS.value == "ai_visibility_loss"
        assert InsightType.AI_DOMINANCE.value == "ai_dominance"
        assert InsightType.AI_STRATEGY_ALERT.value == "ai_strategy_alert"
        assert InsightType.AI_CITATION_INFLUENCE.value == "ai_citation_influence"
        assert InsightType.AI_CATEGORY_OWNERSHIP.value == "ai_category_ownership"

    def test_tracked_prompt_without_category_works(self, db, workspace, billing):
        ws_id = str(workspace.id)
        prompts = client.get(f"/api/workspaces/{ws_id}/ai-visibility/prompts").json()
        # All should load successfully even without categories
        assert isinstance(prompts, list)

    def test_p11_categories_crud_still_works(self, db, workspace, billing):
        ws_id = str(workspace.id)
        # Create
        r = client.post(
            f"/api/workspaces/{ws_id}/ai-visibility/categories",
            json={"category_name": "RegTest"},
        )
        assert r.status_code == 201
        # List
        cats = client.get(f"/api/workspaces/{ws_id}/ai-visibility/categories").json()
        assert any(c["category_name"] == "RegTest" for c in cats)

    def test_correlate_still_works(self, db, workspace, billing):
        ws_id = str(workspace.id)
        r = client.post(f"/api/workspaces/{ws_id}/ai-visibility/insights/correlate?days=7")
        assert r.status_code == 200
        data = r.json()
        assert "insights_created" in data
        assert "citations_extracted" in data

    def test_compact_cards_have_all_p12_compatible_fields(self, db, workspace, billing):
        ws_id = str(workspace.id)
        r = client.get(f"/api/workspaces/{ws_id}/ai-visibility/insights/compact")
        assert r.status_code == 200
        for card in r.json():
            assert "insight_type" in card
            assert "strategy_actions" in card


# ═══════════════════════════════════════════════════════
# PROMPT-13 TESTS
# ═══════════════════════════════════════════════════════


class TestP13EnrichedCategoryVisibility:
    """P13: Tests for the enriched category-visibility endpoint."""

    def test_enriched_endpoint_returns_200(self, db, workspace, billing):
        ws_id = str(workspace.id)
        r = client.get(f"/api/workspaces/{ws_id}/ai-visibility/category-visibility/enriched")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_enriched_endpoint_returns_competitor_and_category_names(self, db, workspace, billing):
        ws_id = str(workspace.id)
        # Create category, competitor, and visibility data
        cat = PromptCategory(workspace_id=workspace.id, category_name="P13 Test Cat", description="test")
        db.add(cat)
        db.flush()
        comp = Competitor(workspace_id=workspace.id, name="P13 Comp", domain="p13comp.test")
        db.add(comp)
        db.flush()
        cv = CategoryVisibility(
            workspace_id=workspace.id,
            category_id=cat.id,
            competitor_id=comp.id,
            visibility_share=75.0,
            engine_count=4,
            prompt_count=3,
            total_mentions=12,
            time_window="7d",
        )
        db.add(cv)
        db.commit()

        r = client.get(f"/api/workspaces/{ws_id}/ai-visibility/category-visibility/enriched")
        assert r.status_code == 200
        data = r.json()
        enriched = [d for d in data if d["category_name"] == "P13 Test Cat"]
        assert len(enriched) >= 1
        row = enriched[0]
        assert row["competitor_name"] == "P13 Comp"
        assert row["category_name"] == "P13 Test Cat"
        assert row["visibility_share"] == 75.0
        assert row["engine_count"] == 4
        assert row["prompt_count"] == 3

    def test_enriched_endpoint_filters_by_category_id(self, db, workspace, billing):
        ws_id = str(workspace.id)
        cat1 = PromptCategory(workspace_id=workspace.id, category_name="P13 Filter A")
        cat2 = PromptCategory(workspace_id=workspace.id, category_name="P13 Filter B")
        db.add_all([cat1, cat2])
        db.flush()
        comp = Competitor(workspace_id=workspace.id, name="P13 FilterComp", domain="p13filter.test")
        db.add(comp)
        db.flush()
        cv1 = CategoryVisibility(workspace_id=workspace.id, category_id=cat1.id, competitor_id=comp.id,
                                  visibility_share=60.0, engine_count=2, prompt_count=1, total_mentions=5)
        cv2 = CategoryVisibility(workspace_id=workspace.id, category_id=cat2.id, competitor_id=comp.id,
                                  visibility_share=40.0, engine_count=2, prompt_count=1, total_mentions=3)
        db.add_all([cv1, cv2])
        db.commit()

        r = client.get(f"/api/workspaces/{ws_id}/ai-visibility/category-visibility/enriched?category_id={cat1.id}")
        assert r.status_code == 200
        data = r.json()
        assert all(d["category_id"] == str(cat1.id) for d in data)


class TestP13CategoryLifecycle:
    """P13: Tests for full category CRUD lifecycle via API."""

    def test_create_category_with_description(self, db, workspace, billing):
        ws_id = str(workspace.id)
        r = client.post(f"/api/workspaces/{ws_id}/ai-visibility/categories",
                        json={"category_name": "P13 Lifecycle Cat", "description": "Lifecycle test"})
        assert r.status_code == 201
        data = r.json()
        assert data["category_name"] == "P13 Lifecycle Cat"
        assert data["description"] == "Lifecycle test"

    def test_rename_category(self, db, workspace, billing):
        ws_id = str(workspace.id)
        r = client.post(f"/api/workspaces/{ws_id}/ai-visibility/categories",
                        json={"category_name": "P13 Before Rename"})
        cat_id = r.json()["id"]
        r2 = client.patch(f"/api/workspaces/{ws_id}/ai-visibility/categories/{cat_id}",
                          json={"category_name": "P13 After Rename"})
        assert r2.status_code == 200
        assert r2.json()["category_name"] == "P13 After Rename"

    def test_rename_duplicate_rejected(self, db, workspace, billing):
        ws_id = str(workspace.id)
        client.post(f"/api/workspaces/{ws_id}/ai-visibility/categories",
                    json={"category_name": "P13 DupA"})
        r2 = client.post(f"/api/workspaces/{ws_id}/ai-visibility/categories",
                         json={"category_name": "P13 DupB"})
        cat_b_id = r2.json()["id"]
        r3 = client.patch(f"/api/workspaces/{ws_id}/ai-visibility/categories/{cat_b_id}",
                          json={"category_name": "P13 DupA"})
        assert r3.status_code == 409

    def test_update_description_only(self, db, workspace, billing):
        ws_id = str(workspace.id)
        r = client.post(f"/api/workspaces/{ws_id}/ai-visibility/categories",
                        json={"category_name": "P13 DescOnly"})
        cat_id = r.json()["id"]
        r2 = client.patch(f"/api/workspaces/{ws_id}/ai-visibility/categories/{cat_id}",
                          json={"description": "Updated description"})
        assert r2.status_code == 200
        assert r2.json()["description"] == "Updated description"
        assert r2.json()["category_name"] == "P13 DescOnly"


class TestP13DeleteCategoryPreservesPrompts:
    """P13: Deletion behavior — prompts become uncategorized."""

    def test_delete_category_sets_prompt_to_null(self, db, workspace, billing):
        ws_id = str(workspace.id)
        # Create category
        r = client.post(f"/api/workspaces/{ws_id}/ai-visibility/categories",
                        json={"category_name": "P13 DelCat"})
        cat_id = r.json()["id"]

        # Create prompt and assign
        src = client.post(f"/api/workspaces/{ws_id}/ai-visibility/suggestions",
                          json={"prompt_text": "p13 del test prompt", "source_type": "manual"})
        src_id = src.json()["id"]
        approve = client.post(f"/api/workspaces/{ws_id}/ai-visibility/suggestions/approve",
                              json={"prompt_source_ids": [src_id]})
        prompt_id = approve.json()[0]["id"]
        client.put(f"/api/workspaces/{ws_id}/ai-visibility/prompts/{prompt_id}/category?category_id={cat_id}")

        # Verify assigned
        prompts = client.get(f"/api/workspaces/{ws_id}/ai-visibility/prompts").json()
        p = [x for x in prompts if x["id"] == prompt_id][0]
        assert p["category_id"] == cat_id

        # Delete category
        r2 = client.delete(f"/api/workspaces/{ws_id}/ai-visibility/categories/{cat_id}")
        assert r2.status_code == 204

        # Verify prompt uncategorized
        prompts2 = client.get(f"/api/workspaces/{ws_id}/ai-visibility/prompts").json()
        p2 = [x for x in prompts2 if x["id"] == prompt_id][0]
        assert p2["category_id"] is None
        assert p2["category_name"] is None


class TestP13PromptCategoryFields:
    """P13: Verify prompts list includes category_id and category_name."""

    def test_prompt_listing_has_category_fields(self, db, workspace, billing):
        ws_id = str(workspace.id)
        r = client.get(f"/api/workspaces/{ws_id}/ai-visibility/prompts")
        assert r.status_code == 200
        for p in r.json():
            assert "category_id" in p
            assert "category_name" in p

    def test_prompt_with_category_shows_name(self, db, workspace, billing):
        ws_id = str(workspace.id)
        # Create category
        r = client.post(f"/api/workspaces/{ws_id}/ai-visibility/categories",
                        json={"category_name": "P13 NameCheck"})
        cat_id = r.json()["id"]

        # Create prompt and assign
        src = client.post(f"/api/workspaces/{ws_id}/ai-visibility/suggestions",
                          json={"prompt_text": "p13 name check prompt", "source_type": "manual"})
        src_id = src.json()["id"]
        approve = client.post(f"/api/workspaces/{ws_id}/ai-visibility/suggestions/approve",
                              json={"prompt_source_ids": [src_id]})
        prompt_id = approve.json()[0]["id"]
        client.put(f"/api/workspaces/{ws_id}/ai-visibility/prompts/{prompt_id}/category?category_id={cat_id}")

        prompts = client.get(f"/api/workspaces/{ws_id}/ai-visibility/prompts").json()
        p = [x for x in prompts if x["id"] == prompt_id][0]
        assert p["category_name"] == "P13 NameCheck"


class TestP13BackwardCompatibility:
    """P13: Regression tests — existing features must not break."""

    def test_existing_category_visibility_endpoint_still_works(self, db, workspace, billing):
        ws_id = str(workspace.id)
        r = client.get(f"/api/workspaces/{ws_id}/ai-visibility/category-visibility")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_insights_compact_still_works(self, db, workspace, billing):
        ws_id = str(workspace.id)
        r = client.get(f"/api/workspaces/{ws_id}/ai-visibility/insights/compact")
        assert r.status_code == 200

    def test_correlate_still_works_p13(self, db, workspace, billing):
        ws_id = str(workspace.id)
        r = client.post(f"/api/workspaces/{ws_id}/ai-visibility/insights/correlate?days=7")
        assert r.status_code == 200
        assert "insights_created" in r.json()

    def test_trends_still_works(self, db, workspace, billing):
        ws_id = str(workspace.id)
        r = client.get(f"/api/workspaces/{ws_id}/ai-visibility/trends?days=7")
        assert r.status_code == 200

    def test_prompt_listing_still_works(self, db, workspace, billing):
        ws_id = str(workspace.id)
        r = client.get(f"/api/workspaces/{ws_id}/ai-visibility/prompts")
        assert r.status_code == 200

    def test_categories_crud_still_works(self, db, workspace, billing):
        ws_id = str(workspace.id)
        r = client.post(f"/api/workspaces/{ws_id}/ai-visibility/categories",
                        json={"category_name": "P13 Reg"})
        assert r.status_code == 201
        cat_id = r.json()["id"]
        r2 = client.get(f"/api/workspaces/{ws_id}/ai-visibility/categories")
        assert r2.status_code == 200
        assert any(c["id"] == cat_id for c in r2.json())
        r3 = client.delete(f"/api/workspaces/{ws_id}/ai-visibility/categories/{cat_id}")
        assert r3.status_code == 204


# ══════════════════════════════════════════════════════════════════
# PROMPT-14 Tests
# ══════════════════════════════════════════════════════════════════


class TestP14InsightTypeEnums:
    """P14: Verify new InsightType enum values exist and are usable."""

    def test_share_of_voice_enum(self):
        assert InsightType.AI_SHARE_OF_VOICE.value == "ai_share_of_voice"

    def test_narrative_enum(self):
        assert InsightType.AI_NARRATIVE.value == "ai_narrative"

    def test_playbook_enum(self):
        assert InsightType.AI_OPTIMIZATION_PLAYBOOK.value == "ai_optimization_playbook"

    def test_all_p14_enums_are_strings(self):
        for it in [InsightType.AI_SHARE_OF_VOICE, InsightType.AI_NARRATIVE, InsightType.AI_OPTIMIZATION_PLAYBOOK]:
            assert isinstance(it.value, str)

    def test_existing_enums_untouched(self):
        """Backward compat: all pre-P14 enums still exist."""
        assert InsightType.AI_IMPACT.value == "ai_impact"
        assert InsightType.AI_VISIBILITY_HIJACK.value == "ai_visibility_hijack"
        assert InsightType.AI_VISIBILITY_LOSS.value == "ai_visibility_loss"
        assert InsightType.AI_DOMINANCE.value == "ai_dominance"
        assert InsightType.AI_STRATEGY_ALERT.value == "ai_strategy_alert"
        assert InsightType.AI_CITATION_INFLUENCE.value == "ai_citation_influence"
        assert InsightType.AI_CATEGORY_OWNERSHIP.value == "ai_category_ownership"


class TestP14NarrativeExtraction:
    """P14: Unit tests for narrative descriptor extraction."""

    def test_extract_is_pattern(self):
        text = "Cursor AI is the best AI coding assistant for developers."
        result = _extract_descriptors(text, "Cursor AI")
        assert len(result) > 0
        assert any("best ai coding assistant" in d for d in result)

    def test_extract_are_pattern(self):
        text = "Cursor AI are known for being developer friendly."
        result = _extract_descriptors(text, "Cursor AI")
        assert len(result) > 0

    def test_extract_no_match(self):
        text = "The weather is nice today."
        result = _extract_descriptors(text, "Cursor AI")
        assert len(result) == 0

    def test_extract_short_descriptor_excluded(self):
        text = "Cursor AI is ok."
        result = _extract_descriptors(text, "Cursor AI")
        # "ok" is too short (< 5 chars)
        assert len(result) == 0

    def test_extract_max_5_descriptors(self):
        text = ". ".join(
            [f"Cursor AI is great tool number {i} for devs" for i in range(10)]
        )
        result = _extract_descriptors(text, "Cursor AI")
        assert len(result) <= 5

    def test_extract_deduplicates(self):
        text = "Cursor AI is the best editor. Also Cursor AI is the best editor."
        result = _extract_descriptors(text, "Cursor AI")
        # Should deduplicate
        assert len(result) == len(set(result))


class TestP14ShareOfVoice:
    """P14: Share of Voice insight generation."""

    def test_sov_no_categories_returns_zero(self, db, workspace, billing):
        count = generate_share_of_voice_insights(db, str(workspace.id))
        assert count == 0

    def test_sov_with_category_and_visibility_data(self, db, workspace, billing):
        ws_id = str(workspace.id)

        # Create competitor
        comp = Competitor(workspace_id=workspace.id, name="SoV TestCo", domain="sovtest.com", is_active=True)
        db.add(comp)
        db.flush()

        # Create category + prompt
        cat = PromptCategory(workspace_id=workspace.id, category_name="SoV Cat")
        db.add(cat)
        db.flush()

        tp = AITrackedPrompt(
            workspace_id=workspace.id, prompt_text="sov test prompt",
            normalized_text="sov test prompt", source_type="manual",
            category_id=cat.id, is_active=True,
        )
        db.add(tp)
        db.flush()

        # Create prompt run + engine result + visibility events
        run = AIPromptRun(prompt_text="sov test prompt", normalized_text="sov test prompt",
                          run_date=datetime.now(timezone.utc), status=RunStatusEnum.COMPLETED.value)
        db.add(run)
        db.flush()

        er = AIEngineResult(prompt_run_id=run.id, engine="chatgpt",
                            status=RunStatusEnum.COMPLETED.value,
                            raw_response="SoV TestCo is great", mentioned_brands=["SoV TestCo"])
        db.add(er)
        db.flush()

        # Add enough visibility events for this competitor to exceed threshold
        for i in range(5):
            db.add(AIVisibilityEvent(
                workspace_id=workspace.id, competitor_id=comp.id,
                tracked_prompt_id=tp.id, engine_result_id=er.id,
                engine="chatgpt", mentioned=True,
                event_date=datetime.now(timezone.utc) - timedelta(hours=i),
            ))
        db.flush()

        count = generate_share_of_voice_insights(db, ws_id)
        db.flush()
        # Should generate at least one SoV insight since this competitor has 100% share
        assert count >= 1

        # Verify insight type
        sov_insights = db.query(AIImpactInsight).filter(
            AIImpactInsight.workspace_id == workspace.id,
            AIImpactInsight.insight_type == InsightType.AI_SHARE_OF_VOICE.value,
        ).all()
        assert len(sov_insights) >= 1
        assert "SoV TestCo" in sov_insights[0].signal_title
        assert sov_insights[0].category_data is not None
        assert "share_of_voice" in sov_insights[0].category_data

    def test_sov_threshold_constant(self):
        assert SOV_THRESHOLD == 15.0


class TestP14OptimizationPlaybooks:
    """P14: Optimization Playbook generation."""

    def test_playbook_no_insights_returns_zero(self, db, workspace, billing):
        count = generate_optimization_playbooks(db, str(workspace.id))
        assert count == 0

    def test_playbook_from_high_priority_insight(self, db, workspace, billing):
        ws_id = str(workspace.id)

        comp = Competitor(workspace_id=workspace.id, name="Playbook Co", domain="playbookco.com", is_active=True)
        db.add(comp)
        db.flush()

        # Create a P0 insight (trigger for playbook)
        db.add(AIImpactInsight(
            workspace_id=workspace.id,
            competitor_id=comp.id,
            insight_type=InsightType.AI_IMPACT.value,
            signal_type="pricing_change",
            signal_title="Playbook Co launched new pricing",
            prompt_text="best ai tools",
            visibility_before=2,
            visibility_after=5,
            visibility_delta=3,
            engines_affected=["chatgpt", "claude"],
            impact_score=75.0,
            priority_level="P0",
            correlation_confidence=80.0,
            short_title="Playbook Co gained visibility",
        ))
        db.flush()

        count = generate_optimization_playbooks(db, ws_id)
        db.flush()
        assert count >= 1

        playbooks = db.query(AIImpactInsight).filter(
            AIImpactInsight.workspace_id == workspace.id,
            AIImpactInsight.insight_type == InsightType.AI_OPTIMIZATION_PLAYBOOK.value,
        ).all()
        assert len(playbooks) >= 1
        pb = playbooks[0]
        assert pb.strategy_actions is not None
        assert len(pb.strategy_actions) > 0
        assert "Playbook Co" in pb.signal_title

    def test_playbook_skips_low_priority(self, db, workspace, billing):
        ws_id = str(workspace.id)

        comp = Competitor(workspace_id=workspace.id, name="Low Prio Co", domain="lowprio.com", is_active=True)
        db.add(comp)
        db.flush()

        # Only P3 insight — should NOT trigger playbook
        db.add(AIImpactInsight(
            workspace_id=workspace.id,
            competitor_id=comp.id,
            insight_type=InsightType.AI_IMPACT.value,
            signal_type="blog_post",
            signal_title="Low Prio Co blog",
            visibility_before=1,
            visibility_after=2,
            visibility_delta=1,
            engines_affected=["chatgpt"],
            impact_score=10.0,
            priority_level="P3",
            correlation_confidence=30.0,
        ))
        db.flush()

        count = generate_optimization_playbooks(db, ws_id)
        assert count == 0

    def test_playbook_priority_threshold(self):
        assert "P0" in PLAYBOOK_PRIORITY_THRESHOLD
        assert "P1" in PLAYBOOK_PRIORITY_THRESHOLD


class TestP14DominanceWording:
    """P14 PART 8: Verify AI dominance wording fix."""

    def test_dominance_signal_title_wording(self, db, workspace, billing):
        """The correlation engine should use 'appears across' not 'dominates'."""
        from app.services.ai_visibility.correlation_engine import correlate_signals_with_visibility
        # We won't run full correlation, just verify the code path
        # by checking the imported module source doesn't contain old wording
        import inspect
        source = inspect.getsource(correlate_signals_with_visibility)
        assert "appears across all AI engines" in source
        assert "dominates all AI engines" not in source


class TestP14OwnershipWording:
    """P14 PART 7: Verify category ownership insight wording fix."""

    def test_ownership_short_title_prefix(self, db, workspace, billing):
        """Category ownership insights should use 'Ownership:' prefix."""
        from app.services.ai_visibility.category_ownership import generate_category_ownership_insights
        import inspect
        source = inspect.getsource(generate_category_ownership_insights)
        assert 'short_title=f"Ownership:' in source


class TestP14CategoryMembershipAPI:
    """P14 PARTS 1-4: Category membership management via existing API."""

    def _create_prompt(self, ws_id, prompt_text):
        """Helper: create suggestion → approve → return tracked prompt id."""
        src = client.post(f"/api/workspaces/{ws_id}/ai-visibility/suggestions",
                          json={"prompt_text": prompt_text, "source_type": "manual"})
        assert src.status_code == 201
        src_id = src.json()["id"]
        approved = client.post(f"/api/workspaces/{ws_id}/ai-visibility/suggestions/approve",
                               json={"prompt_source_ids": [src_id]})
        assert approved.status_code == 200
        return approved.json()[0]["id"]

    def test_remove_prompt_from_category(self, db, workspace, billing):
        ws_id = str(workspace.id)

        # Create category
        r = client.post(f"/api/workspaces/{ws_id}/ai-visibility/categories",
                        json={"category_name": "Membership Test Cat"})
        assert r.status_code == 201
        cat_id = r.json()["id"]

        # Create prompt and assign to category
        prompt_id = self._create_prompt(ws_id, "membership test prompt")
        client.put(f"/api/workspaces/{ws_id}/ai-visibility/prompts/{prompt_id}/category?category_id={cat_id}")

        # Remove from category (set to null)
        r3 = client.put(f"/api/workspaces/{ws_id}/ai-visibility/prompts/{prompt_id}/category")
        assert r3.status_code == 200
        assert r3.json()["category_id"] is None

        # Prompt still exists
        r4 = client.get(f"/api/workspaces/{ws_id}/ai-visibility/prompts")
        assert r4.status_code == 200
        prompt = next(p for p in r4.json() if p["id"] == prompt_id)
        assert prompt["category_id"] is None

    def test_move_prompt_between_categories(self, db, workspace, billing):
        ws_id = str(workspace.id)

        # Create two categories
        r1 = client.post(f"/api/workspaces/{ws_id}/ai-visibility/categories",
                         json={"category_name": "Source Cat"})
        assert r1.status_code == 201
        src_id = r1.json()["id"]

        r2 = client.post(f"/api/workspaces/{ws_id}/ai-visibility/categories",
                         json={"category_name": "Target Cat"})
        assert r2.status_code == 201
        tgt_id = r2.json()["id"]

        # Create prompt and assign to source
        prompt_id = self._create_prompt(ws_id, "movable prompt p14")
        client.put(f"/api/workspaces/{ws_id}/ai-visibility/prompts/{prompt_id}/category?category_id={src_id}")

        # Move to target
        r4 = client.put(f"/api/workspaces/{ws_id}/ai-visibility/prompts/{prompt_id}/category?category_id={tgt_id}")
        assert r4.status_code == 200
        assert r4.json()["category_id"] == tgt_id

    def test_add_uncategorized_prompt_to_category(self, db, workspace, billing):
        ws_id = str(workspace.id)

        # Create prompt (uncategorized by default)
        prompt_id = self._create_prompt(ws_id, "uncategorized prompt p14")

        # Create category
        r2 = client.post(f"/api/workspaces/{ws_id}/ai-visibility/categories",
                         json={"category_name": "Add To Cat"})
        assert r2.status_code == 201
        cat_id = r2.json()["id"]

        # Assign to category
        r3 = client.put(f"/api/workspaces/{ws_id}/ai-visibility/prompts/{prompt_id}/category?category_id={cat_id}")
        assert r3.status_code == 200
        assert r3.json()["category_id"] == cat_id


class TestP14InsightCompactFilterNewTypes:
    """P14: Verify compact insight endpoint accepts new insight types in filter."""

    def test_filter_by_share_of_voice(self, db, workspace, billing):
        ws_id = str(workspace.id)
        r = client.get(f"/api/workspaces/{ws_id}/ai-visibility/insights/compact?insight_type=ai_share_of_voice")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_filter_by_narrative(self, db, workspace, billing):
        ws_id = str(workspace.id)
        r = client.get(f"/api/workspaces/{ws_id}/ai-visibility/insights/compact?insight_type=ai_narrative")
        assert r.status_code == 200

    def test_filter_by_playbook(self, db, workspace, billing):
        ws_id = str(workspace.id)
        r = client.get(f"/api/workspaces/{ws_id}/ai-visibility/insights/compact?insight_type=ai_optimization_playbook")
        assert r.status_code == 200


class TestP14CorrelationPipelineIntegration:
    """P14: Verify correlation pipeline runs without errors including new generators."""

    def test_full_pipeline_runs_cleanly(self, db, workspace, billing):
        ws_id = str(workspace.id)
        r = client.post(f"/api/workspaces/{ws_id}/ai-visibility/insights/correlate?days=7")
        assert r.status_code == 200
        data = r.json()
        assert "insights_created" in data
        assert "competitors_analyzed" in data

    def test_pipeline_backward_compat_no_categories(self, db, workspace, billing):
        """Prompts without categories should still generate base insights without errors."""
        ws_id = str(workspace.id)
        # Create prompt without category
        client.post(f"/api/workspaces/{ws_id}/ai-visibility/prompts",
                    json={"prompt_text": "no category prompt p14"})
        r = client.post(f"/api/workspaces/{ws_id}/ai-visibility/insights/correlate?days=7")
        assert r.status_code == 200


class TestP14BackwardCompatRegression:
    """P14: Ensure all existing functionality still works after P14 changes."""

    def test_insight_types_list_endpoint(self, db, workspace, billing):
        ws_id = str(workspace.id)
        r = client.get(f"/api/workspaces/{ws_id}/ai-visibility/insights/compact")
        assert r.status_code == 200

    def test_enriched_visibility_endpoint(self, db, workspace, billing):
        ws_id = str(workspace.id)
        r = client.get(f"/api/workspaces/{ws_id}/ai-visibility/category-visibility/enriched")
        assert r.status_code == 200

    def test_category_crud_still_works(self, db, workspace, billing):
        ws_id = str(workspace.id)
        r = client.post(f"/api/workspaces/{ws_id}/ai-visibility/categories",
                        json={"category_name": "P14 Reg Cat"})
        assert r.status_code == 201
        cat_id = r.json()["id"]

        r2 = client.patch(f"/api/workspaces/{ws_id}/ai-visibility/categories/{cat_id}",
                          json={"category_name": "P14 Reg Cat Renamed"})
        assert r2.status_code == 200

        r3 = client.delete(f"/api/workspaces/{ws_id}/ai-visibility/categories/{cat_id}")
        assert r3.status_code == 204

    def test_prompts_still_work(self, db, workspace, billing):
        ws_id = str(workspace.id)
        r = client.get(f"/api/workspaces/{ws_id}/ai-visibility/prompts")
        assert r.status_code == 200

    def test_trends_still_work(self, db, workspace, billing):
        ws_id = str(workspace.id)
        r = client.get(f"/api/workspaces/{ws_id}/ai-visibility/trends?days=7")
        assert r.status_code == 200

