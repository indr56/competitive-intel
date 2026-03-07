"""
Tests for signal classification enhancements and prompt clustering.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text as _text
from sqlalchemy.orm import sessionmaker, Session

from app.core.database import Base, get_db
from app.main import app
from app.models.models import (
    Account,
    Competitor,
    CompetitorEvent,
    MonitoredPrompt,
    PromptCluster,
    Workspace,
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
    account = Account(name="Enhance Test", slug="enhance-test", plan="free")
    db.add(account)
    db.flush()
    ws = Workspace(account_id=account.id, name="Enhance WS", slug="enhance-ws")
    db.add(ws)
    db.commit()
    db.refresh(ws)
    return ws


@pytest.fixture
def competitor(db: Session, workspace):
    comp = Competitor(
        workspace_id=workspace.id,
        name="EnhComp",
        domain="enhcomp.com",
    )
    db.add(comp)
    db.commit()
    db.refresh(comp)
    return comp


# ═══════════════════════════════════════════════
# 1. Enhanced Signal Types
# ═══════════════════════════════════════════════


class TestSignalTypes:
    """Test that new signal types are available."""

    def test_signal_types_include_new(self):
        """GET /api/events/signal-types should include the 4 new types."""
        resp = client.get("/api/events/signal-types")
        assert resp.status_code == 200
        types = resp.json()
        assert "positioning_change" in types
        assert "integration_added" in types
        assert "integration_removed" in types
        assert "landing_page_created" in types
        assert len(types) == 12  # 8 original + 4 new

    def test_create_event_new_signal_type(self, workspace, competitor):
        """Should be able to create events with new signal types."""
        for st in ["positioning_change", "integration_added", "integration_removed", "landing_page_created"]:
            resp = client.post(
                f"/api/workspaces/{workspace.id}/competitors/{competitor.id}/events",
                json={
                    "signal_type": st,
                    "title": f"Test {st} event",
                    "severity": "medium",
                },
            )
            assert resp.status_code == 201, f"Failed for signal_type={st}: {resp.text}"
            assert resp.json()["signal_type"] == st


# ═══════════════════════════════════════════════
# 2. Classifier Enhancements
# ═══════════════════════════════════════════════


class TestClassifierEnhancements:
    """Test new keyword rules and signal type derivation."""

    def test_positioning_change_keywords(self):
        """Positioning keywords should trigger POSITIONING_CHANGE category."""
        from app.services.classifier import classify_with_rules
        from app.services.differ import DiffResult
        from app.models.models import PageType

        diff = DiffResult(
            raw_diff_lines=[],
            additions=["AI-powered workflow automation platform"],
            removals=["Automate workflows between apps"],
            is_meaningful=True,
            changed_char_count=100,
        )
        cats = classify_with_rules(diff, PageType.HOME_HERO)
        cat_values = [c.value for c in cats]
        assert "positioning_change" in cat_values

    def test_integration_added_keywords(self):
        """Integration keywords should trigger INTEGRATION_ADDED."""
        from app.services.classifier import classify_with_rules
        from app.services.differ import DiffResult
        from app.models.models import PageType

        diff = DiffResult(
            raw_diff_lines=[],
            additions=["New integration with Salesforce", "Now works with Slack"],
            removals=[],
            is_meaningful=True,
            changed_char_count=80,
        )
        cats = classify_with_rules(diff, PageType.INTEGRATIONS)
        cat_values = [c.value for c in cats]
        assert "integration_added" in cat_values

    def test_integration_removed_keywords(self):
        """Removal keywords should trigger INTEGRATION_REMOVED."""
        from app.services.classifier import classify_with_rules
        from app.services.differ import DiffResult
        from app.models.models import PageType

        diff = DiffResult(
            raw_diff_lines=[],
            additions=[],
            removals=["Discontinued integration with legacy API"],
            is_meaningful=True,
            changed_char_count=60,
        )
        cats = classify_with_rules(diff, PageType.INTEGRATIONS)
        cat_values = [c.value for c in cats]
        assert "integration_removed" in cat_values

    def test_landing_page_keywords(self):
        """Landing page URL keywords should trigger LANDING_PAGE_CREATED."""
        from app.services.classifier import classify_with_rules
        from app.services.differ import DiffResult
        from app.models.models import PageType

        diff = DiffResult(
            raw_diff_lines=[],
            additions=["/ai-automation new page detected", "/enterprise signup"],
            removals=[],
            is_meaningful=True,
            changed_char_count=50,
        )
        cats = classify_with_rules(diff, PageType.LANDING)
        cat_values = [c.value for c in cats]
        assert "positioning_change" in cat_values or "landing_page_created" in cat_values

    def test_derive_signal_type_positioning(self):
        """derive_signal_type should return positioning_change for positioning categories."""
        from app.services.classifier import derive_signal_type
        assert derive_signal_type(["positioning_change", "other"]) == "positioning_change"

    def test_derive_signal_type_integration(self):
        from app.services.classifier import derive_signal_type
        assert derive_signal_type(["integration_added"]) == "integration_added"
        assert derive_signal_type(["integration_removed"]) == "integration_removed"

    def test_derive_signal_type_landing(self):
        from app.services.classifier import derive_signal_type
        assert derive_signal_type(["landing_page_created"]) == "landing_page_created"

    def test_derive_signal_type_pricing(self):
        from app.services.classifier import derive_signal_type
        assert derive_signal_type(["pricing_change", "plan_restructure"]) == "pricing_change"

    def test_derive_signal_type_default(self):
        from app.services.classifier import derive_signal_type
        assert derive_signal_type(["other"]) == "website_change"
        assert derive_signal_type([]) == "website_change"

    def test_integrations_page_heuristic(self):
        """Integrations page type should auto-add integration categories."""
        from app.services.classifier import classify_with_rules
        from app.services.differ import DiffResult
        from app.models.models import PageType

        diff = DiffResult(
            raw_diff_lines=[],
            additions=["OpenAI", "Salesforce"],
            removals=["Legacy API"],
            is_meaningful=True,
            changed_char_count=40,
        )
        cats = classify_with_rules(diff, PageType.INTEGRATIONS)
        cat_values = [c.value for c in cats]
        assert "integration_added" in cat_values
        assert "integration_removed" in cat_values

    def test_category_weights_updated(self):
        """New categories should have impact weights."""
        from app.services.differ import CATEGORY_WEIGHTS
        assert "positioning_change" in CATEGORY_WEIGHTS
        assert "integration_added" in CATEGORY_WEIGHTS
        assert "integration_removed" in CATEGORY_WEIGHTS
        assert "landing_page_created" in CATEGORY_WEIGHTS


# ═══════════════════════════════════════════════
# 3. Prompt Normalization
# ═══════════════════════════════════════════════


class TestPromptNormalization:
    """Test prompt normalization logic."""

    def test_normalize_basic(self):
        from app.services.prompt_clustering import normalize_prompt
        result = normalize_prompt("best CRM tools")
        assert "crm" in result

    def test_normalize_removes_stopwords(self):
        from app.services.prompt_clustering import normalize_prompt
        result = normalize_prompt("the best tool for the job")
        assert "the" not in result.split()
        assert "for" not in result.split()

    def test_normalize_lowercases(self):
        from app.services.prompt_clustering import normalize_prompt
        result = normalize_prompt("BEST CRM TOOLS")
        assert result == result.lower()

    def test_normalize_removes_punctuation(self):
        from app.services.prompt_clustering import normalize_prompt
        result = normalize_prompt("best CRM tools!!")
        assert "!" not in result

    def test_normalize_similar_prompts(self):
        """Similar prompts should normalize to similar tokens."""
        from app.services.prompt_clustering import normalize_prompt
        n1 = normalize_prompt("best CRM")
        n2 = normalize_prompt("top CRM")
        # Both should contain 'crm'
        assert "crm" in n1
        assert "crm" in n2


# ═══════════════════════════════════════════════
# 4. Prompt Similarity
# ═══════════════════════════════════════════════


class TestPromptSimilarity:
    """Test embedding and similarity computation."""

    def test_cosine_similarity_identical(self):
        from app.services.prompt_clustering import compute_embedding, cosine_similarity
        emb = compute_embedding("crm tool")
        sim = cosine_similarity(emb, emb)
        assert sim == 1.0 or abs(sim - 1.0) < 0.001

    def test_cosine_similarity_related(self):
        from app.services.prompt_clustering import compute_embedding, cosine_similarity
        emb_a = compute_embedding("crm tool")
        emb_b = compute_embedding("crm software")
        sim = cosine_similarity(emb_a, emb_b)
        assert sim > 0.2  # Related terms share char n-grams

    def test_cosine_similarity_unrelated(self):
        from app.services.prompt_clustering import compute_embedding, cosine_similarity
        emb_a = compute_embedding("crm")
        emb_b = compute_embedding("quantum physics research")
        sim = cosine_similarity(emb_a, emb_b)
        assert sim < 0.5  # Unrelated terms should have low similarity

    def test_empty_embeddings(self):
        from app.services.prompt_clustering import cosine_similarity
        assert cosine_similarity({}, {}) == 0.0
        assert cosine_similarity({"a": 1.0}, {}) == 0.0


# ═══════════════════════════════════════════════
# 5. Prompt Clustering API
# ═══════════════════════════════════════════════


class TestPromptClusteringAPI:
    """Test prompt clustering API endpoints."""

    def test_create_prompt(self, workspace):
        resp = client.post(
            f"/api/workspaces/{workspace.id}/prompts",
            json={"raw_text": "best CRM tools"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["raw_text"] == "best CRM tools"
        assert data["normalized_text"]  # should be non-empty
        assert data["workspace_id"] == str(workspace.id)

    def test_create_duplicate_prompt(self, workspace):
        """Duplicate prompt should return 409."""
        client.post(
            f"/api/workspaces/{workspace.id}/prompts",
            json={"raw_text": "best CRM tools"},
        )
        resp = client.post(
            f"/api/workspaces/{workspace.id}/prompts",
            json={"raw_text": "best CRM tools"},
        )
        assert resp.status_code == 409

    def test_list_prompts(self, workspace):
        client.post(f"/api/workspaces/{workspace.id}/prompts", json={"raw_text": "CRM tools"})
        client.post(f"/api/workspaces/{workspace.id}/prompts", json={"raw_text": "ERP software"})

        resp = client.get(f"/api/workspaces/{workspace.id}/prompts")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_delete_prompt(self, workspace):
        resp = client.post(
            f"/api/workspaces/{workspace.id}/prompts",
            json={"raw_text": "delete me"},
        )
        pid = resp.json()["id"]
        del_resp = client.delete(f"/api/prompts/{pid}")
        assert del_resp.status_code == 204

    def test_run_clustering(self, workspace):
        """Run clustering on a set of similar prompts."""
        prompts = [
            "best CRM tools",
            "top CRM software",
            "CRM platforms 2024",
            "workflow automation tools",
            "workflow automation software",
        ]
        for p in prompts:
            client.post(f"/api/workspaces/{workspace.id}/prompts", json={"raw_text": p})

        resp = client.post(f"/api/workspaces/{workspace.id}/prompt-clusters/run")
        assert resp.status_code == 200
        data = resp.json()
        assert "clusters_created" in data
        assert "prompts_clustered" in data
        assert data["clusters_created"] + data["prompts_unclustered"] > 0

    def test_list_clusters(self, workspace):
        # Create prompts and cluster them
        for p in ["CRM tools", "CRM software", "CRM platforms"]:
            client.post(f"/api/workspaces/{workspace.id}/prompts", json={"raw_text": p})
        client.post(f"/api/workspaces/{workspace.id}/prompt-clusters/run")

        resp = client.get(f"/api/workspaces/{workspace.id}/prompt-clusters")
        assert resp.status_code == 200
        clusters = resp.json()
        assert isinstance(clusters, list)

    def test_get_cluster(self, workspace):
        for p in ["CRM tools", "CRM software", "CRM platforms"]:
            client.post(f"/api/workspaces/{workspace.id}/prompts", json={"raw_text": p})
        client.post(f"/api/workspaces/{workspace.id}/prompt-clusters/run")

        clusters = client.get(f"/api/workspaces/{workspace.id}/prompt-clusters").json()
        if clusters:
            cid = clusters[0]["id"]
            resp = client.get(f"/api/prompt-clusters/{cid}")
            assert resp.status_code == 200
            assert resp.json()["id"] == cid
            assert "prompts" in resp.json()

    def test_delete_cluster(self, workspace):
        for p in ["CRM tools", "CRM software", "CRM platforms"]:
            client.post(f"/api/workspaces/{workspace.id}/prompts", json={"raw_text": p})
        client.post(f"/api/workspaces/{workspace.id}/prompt-clusters/run")

        clusters = client.get(f"/api/workspaces/{workspace.id}/prompt-clusters").json()
        if clusters:
            cid = clusters[0]["id"]
            resp = client.delete(f"/api/prompt-clusters/{cid}")
            assert resp.status_code == 204

    def test_cluster_not_found(self):
        fake_id = str(uuid.uuid4())
        resp = client.get(f"/api/prompt-clusters/{fake_id}")
        assert resp.status_code == 404

    def test_prompt_not_found(self):
        fake_id = str(uuid.uuid4())
        resp = client.delete(f"/api/prompts/{fake_id}")
        assert resp.status_code == 404


# ═══════════════════════════════════════════════
# 6. Clustering Service (unit tests)
# ═══════════════════════════════════════════════


class TestClusteringService:
    """Test the clustering service directly."""

    def test_cluster_similar_prompts(self, db, workspace):
        from app.services.prompt_clustering import add_prompt_to_workspace, cluster_prompts

        for text in ["best CRM", "top CRM", "CRM software", "CRM tools"]:
            add_prompt_to_workspace(db, str(workspace.id), text)

        result = cluster_prompts(db, str(workspace.id))
        assert result["clusters_created"] >= 1
        assert result["prompts_clustered"] >= 2

    def test_cluster_dissimilar_prompts(self, db, workspace):
        from app.services.prompt_clustering import add_prompt_to_workspace, cluster_prompts

        add_prompt_to_workspace(db, str(workspace.id), "CRM tools")
        add_prompt_to_workspace(db, str(workspace.id), "quantum physics experiments")

        result = cluster_prompts(db, str(workspace.id))
        # Dissimilar prompts should not cluster together
        assert result["prompts_unclustered"] >= 1

    def test_empty_workspace_clustering(self, db, workspace):
        from app.services.prompt_clustering import cluster_prompts
        result = cluster_prompts(db, str(workspace.id))
        assert result["clusters_created"] == 0
        assert result["prompts_clustered"] == 0


# ═══════════════════════════════════════════════
# 7. Regression Tests
# ═══════════════════════════════════════════════


# ═══════════════════════════════════════════════
# 8. New Collectors Tests
# ═══════════════════════════════════════════════


class TestPositioningCollector:
    """Test the positioning change collector."""

    def test_extract_positioning_with_keywords(self):
        from app.services.collectors.positioning_collector import PositioningCollector, _strip_html
        from unittest.mock import MagicMock

        db_mock = MagicMock()
        collector = PositioningCollector(db_mock)
        comp = MagicMock()
        comp.name = "TestComp"

        html = """
        <html><body>
        <div class="hero">
            <h1>AI-powered workflow automation platform</h1>
            <h2>Built for modern teams. Transform your business.</h2>
        </div>
        </body></html>
        """
        events = collector._extract_positioning(html, "https://test.com", comp)
        assert len(events) >= 1
        assert "positioning" in events[0]["title"].lower() or "Positioning" in events[0]["title"]

    def test_no_positioning_on_empty_page(self):
        from app.services.collectors.positioning_collector import PositioningCollector
        from unittest.mock import MagicMock

        db_mock = MagicMock()
        collector = PositioningCollector(db_mock)
        comp = MagicMock()
        comp.name = "TestComp"

        html = "<html><body><p>Nothing interesting here</p></body></html>"
        events = collector._extract_positioning(html, "https://test.com", comp)
        assert len(events) == 0


class TestIntegrationCollectors:
    """Test integration added/removed collectors."""

    def test_detect_known_integrations(self):
        from app.services.collectors.integration_collector import IntegrationAddedCollector
        from unittest.mock import MagicMock

        db_mock = MagicMock()
        collector = IntegrationAddedCollector(db_mock)
        comp = MagicMock()
        comp.name = "TestComp"

        html = """
        <html><body>
        <div class="integrations">
            <div>Salesforce</div>
            <div>Slack</div>
            <div>HubSpot</div>
            <div>Zapier</div>
            <div>GitHub</div>
        </div>
        </body></html>
        """
        events = collector._extract_integrations(html, "https://test.com/integrations", comp)
        assert len(events) >= 1
        assert "integrations" in events[0]["title"].lower()
        meta = events[0]["metadata_json"]
        assert meta["count"] >= 5

    def test_no_integrations_on_empty_page(self):
        from app.services.collectors.integration_collector import IntegrationAddedCollector
        from unittest.mock import MagicMock

        db_mock = MagicMock()
        collector = IntegrationAddedCollector(db_mock)
        comp = MagicMock()
        comp.name = "TestComp"

        html = "<html><body><p>No integrations here</p></body></html>"
        events = collector._extract_integrations(html, "https://test.com", comp)
        assert len(events) == 0

    def test_detect_removal_keywords(self):
        from app.services.collectors.integration_collector import IntegrationRemovedCollector
        from unittest.mock import MagicMock

        db_mock = MagicMock()
        collector = IntegrationRemovedCollector(db_mock)
        comp = MagicMock()
        comp.name = "TestComp"

        html = """
        <html><body>
        <div class="notice">
            The legacy API integration has been deprecated and will be removed.
            Migration required for all users.
        </div>
        </body></html>
        """
        events = collector._extract_removals(html, "https://test.com/integrations", comp)
        assert len(events) >= 1
        assert "deprecation" in events[0]["title"].lower()


class TestLandingPageCollector:
    """Test landing page discovery collector."""

    def test_detect_strategic_landing_page(self):
        from app.services.collectors.landing_page_collector import LandingPageCollector
        from unittest.mock import MagicMock

        db_mock = MagicMock()
        collector = LandingPageCollector(db_mock)
        comp = MagicMock()
        comp.name = "TestComp"

        html = """
        <html><head><title>AI Automation - TestComp</title></head>
        <body>
        <h1>Supercharge your workflows with AI</h1>
        <p>Our platform helps teams automate repetitive tasks.</p>
        <a href="/signup">Get Started Free</a>
        <a href="/demo">Book a Demo</a>
        """ + ("x" * 500) + """
        </body></html>
        """
        events = collector._analyze_page(html, "https://test.com/ai-automation", comp)
        assert len(events) >= 1
        assert "landing page" in events[0]["title"].lower()

    def test_ignore_blog_path(self):
        from app.services.collectors.landing_page_collector import LandingPageCollector
        from unittest.mock import MagicMock

        db_mock = MagicMock()
        collector = LandingPageCollector(db_mock)
        comp = MagicMock()
        comp.name = "TestComp"

        html = "<html><body><h1>Blog Post</h1><a>Get Started</a>" + ("x" * 600) + "</body></html>"
        events = collector._analyze_page(html, "https://test.com/blog/some-post", comp)
        assert len(events) == 0

    def test_ignore_root_path(self):
        from app.services.collectors.landing_page_collector import LandingPageCollector
        from unittest.mock import MagicMock

        db_mock = MagicMock()
        collector = LandingPageCollector(db_mock)
        comp = MagicMock()
        comp.name = "TestComp"

        html = "<html><body><h1>Home</h1><a>Get Started</a>" + ("x" * 600) + "</body></html>"
        events = collector._analyze_page(html, "https://test.com/", comp)
        assert len(events) == 0


class TestScanServiceNewTypes:
    """Test that scan service now includes the new signal types."""

    def test_collector_map_has_new_types(self):
        from app.services.scan_service import COLLECTOR_MAP, SCANNABLE_TYPES
        assert "positioning_change" in SCANNABLE_TYPES
        assert "integration_added" in SCANNABLE_TYPES
        assert "integration_removed" in SCANNABLE_TYPES
        assert "landing_page_created" in SCANNABLE_TYPES
        assert len(COLLECTOR_MAP) == 8  # 4 original + 4 new

    def test_scan_competitor_includes_new_types(self, workspace, competitor):
        """Scan should now include all 8 scannable types."""
        resp = client.post(f"/api/competitors/{competitor.id}/scan")
        assert resp.status_code == 200
        data = resp.json()
        scanned_types = [r["signal_type"] for r in data["results"]]
        # All 8 should be scanned
        for st in ["review", "blog_post", "hiring", "funding",
                    "positioning_change", "integration_added",
                    "integration_removed", "landing_page_created"]:
            assert st in scanned_types, f"{st} missing from scan results"
        assert data["sources_scanned"] == 8


class TestRegression:
    """Ensure existing endpoints still work."""

    def test_health(self):
        assert client.get("/health").status_code == 200

    def test_signal_types_still_has_originals(self):
        types = client.get("/api/events/signal-types").json()
        for orig in ["website_change", "pricing_change", "product_change",
                     "blog_post", "hiring", "funding", "review", "marketing"]:
            assert orig in types

    def test_changes_list(self, workspace):
        resp = client.get(f"/api/changes?workspace_id={workspace.id}")
        assert resp.status_code == 200

    def test_activity_feed(self, workspace):
        resp = client.get(f"/api/workspaces/{workspace.id}/activity")
        assert resp.status_code == 200

    def test_events_list(self, workspace):
        resp = client.get(f"/api/workspaces/{workspace.id}/events")
        assert resp.status_code == 200

    def test_competitor_crud(self, workspace):
        # Create
        resp = client.post(
            f"/api/workspaces/{workspace.id}/competitors",
            json={"name": "RegTest", "domain": "regtest.com"},
        )
        assert resp.status_code == 201
        cid = resp.json()["id"]
        # Read
        assert client.get(f"/api/competitors/{cid}").status_code == 200
        # Delete
        assert client.delete(f"/api/competitors/{cid}").status_code == 204
