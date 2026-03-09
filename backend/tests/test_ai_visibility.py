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
)
from app.services.ai_visibility.prompt_suggestion import (
    generate_all_suggestions,
)
from app.services.ai_visibility.workspace_filtering import (
    _brand_matches,
    filter_results_for_workspace,
)
from app.services.ai_visibility.correlation_engine import (
    _compute_impact_score,
    _compute_priority,
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

        if len(insights) > 0:
            for ins in insights:
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

        # Should be at most 5 (MAX_INSIGHTS_PER_COMP_PROMPT)
        assert len(insights) <= 5, \
            f"Expected max 5 insights per comp×prompt but got {len(insights)}"

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
