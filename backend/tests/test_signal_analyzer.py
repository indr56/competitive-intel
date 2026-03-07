"""
Tests for signal analyzer (AI analysis generation for CompetitorEvents)
and the /api/events/{id}/analyze endpoint.
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
    account = Account(name="Analyzer Test Account", slug="analyzer-test", plan="free")
    db.add(account)
    db.flush()
    ws = Workspace(account_id=account.id, name="Analyzer WS", slug="analyzer-ws")
    db.add(ws)
    db.commit()
    db.refresh(ws)
    return ws


@pytest.fixture
def competitor(db: Session, workspace):
    comp = Competitor(
        workspace_id=workspace.id,
        name="TestComp",
        domain="testcomp.com",
    )
    db.add(comp)
    db.commit()
    db.refresh(comp)
    return comp


@pytest.fixture
def event(db: Session, workspace, competitor):
    ev = CompetitorEvent(
        workspace_id=workspace.id,
        competitor_id=competitor.id,
        signal_type="hiring",
        title="TestComp hiring 5 engineers",
        description="TestComp posted 5 new engineering roles on their careers page.",
        severity="medium",
        source_url="https://testcomp.com/careers",
        metadata_json={"roles_count": 5, "departments": ["engineering"]},
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return ev


# ═══════════════════════════════════════════════
# 1. Signal analyzer unit tests
# ═══════════════════════════════════════════════


class TestSignalAnalyzer:
    """Test the generate_signal_analysis function directly."""

    @patch("app.core.llm_client.get_llm_client")
    def test_generates_analysis_with_llm(self, mock_get_llm, db, event, competitor):
        """When LLM is available, ai_summary and ai_implications should be populated."""
        mock_llm = MagicMock()
        mock_llm.chat_json.return_value = {
            "summary": "TestComp is expanding their engineering team with 5 new roles.",
            "implications": "1. Monitor for product launches. 2. Review our hiring pipeline.",
        }
        mock_get_llm.return_value = mock_llm

        from app.services.signal_analyzer import generate_signal_analysis
        result = generate_signal_analysis(event, db, competitor_name="TestComp")

        assert result is True
        db.refresh(event)
        assert event.ai_summary is not None
        assert "TestComp" in event.ai_summary
        assert event.ai_implications is not None
        assert event.is_processed is True

    @patch("app.core.llm_client.get_llm_client")
    def test_fallback_when_llm_fails(self, mock_get_llm, db, event, competitor):
        """When LLM fails, should generate rule-based fallback analysis."""
        mock_get_llm.side_effect = Exception("LLM unavailable")

        from app.services.signal_analyzer import generate_signal_analysis
        result = generate_signal_analysis(event, db, competitor_name="TestComp")

        assert result is True
        db.refresh(event)
        assert event.ai_summary is not None
        assert "TestComp" in event.ai_summary
        assert event.ai_implications is not None
        assert "hiring" in event.ai_implications.lower() or "team" in event.ai_implications.lower()
        assert event.is_processed is True

    @patch("app.core.llm_client.get_llm_client")
    def test_skips_if_already_analyzed(self, mock_get_llm, db, event):
        """Should skip analysis if ai_summary AND ai_implications already set."""
        event.ai_summary = "Existing summary"
        event.ai_implications = "Existing implications"
        db.commit()

        from app.services.signal_analyzer import generate_signal_analysis
        result = generate_signal_analysis(event, db)

        assert result is False
        mock_get_llm.assert_not_called()

    @patch("app.core.llm_client.get_llm_client")
    def test_fallback_for_blog_signal(self, mock_get_llm, db, workspace, competitor):
        """Fallback implications should be signal-type-specific."""
        mock_get_llm.side_effect = Exception("LLM unavailable")

        ev = CompetitorEvent(
            workspace_id=workspace.id,
            competitor_id=competitor.id,
            signal_type="blog_post",
            title="TestComp published new blog",
            severity="low",
        )
        db.add(ev)
        db.commit()
        db.refresh(ev)

        from app.services.signal_analyzer import generate_signal_analysis
        generate_signal_analysis(ev, db, competitor_name="TestComp")

        db.refresh(ev)
        assert "content" in ev.ai_implications.lower() or "blog" in ev.ai_implications.lower()

    @patch("app.core.llm_client.get_llm_client")
    def test_fallback_for_funding_signal(self, mock_get_llm, db, workspace, competitor):
        """Fallback implications for funding signals."""
        mock_get_llm.side_effect = Exception("LLM unavailable")

        ev = CompetitorEvent(
            workspace_id=workspace.id,
            competitor_id=competitor.id,
            signal_type="funding",
            title="TestComp raises Series B",
            severity="high",
        )
        db.add(ev)
        db.commit()
        db.refresh(ev)

        from app.services.signal_analyzer import generate_signal_analysis
        generate_signal_analysis(ev, db, competitor_name="TestComp")

        db.refresh(ev)
        assert "funding" in ev.ai_implications.lower() or "financial" in ev.ai_implications.lower()


# ═══════════════════════════════════════════════
# 2. Analyze endpoint API tests
# ═══════════════════════════════════════════════


class TestAnalyzeEndpoint:
    """Test POST /api/events/{event_id}/analyze."""

    @patch("app.core.llm_client.get_llm_client")
    def test_analyze_event_success(self, mock_get_llm, event):
        """POST /api/events/{id}/analyze should populate AI fields."""
        mock_llm = MagicMock()
        mock_llm.chat_json.return_value = {
            "summary": "AI-generated summary for hiring signal.",
            "implications": "1. Expand our team. 2. Counter-position.",
        }
        mock_get_llm.return_value = mock_llm

        resp = client.post(f"/api/events/{event.id}/analyze")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ai_summary"] is not None
        assert data["ai_implications"] is not None

    def test_analyze_event_not_found(self):
        """POST /api/events/{bad_id}/analyze should return 404."""
        fake_id = str(uuid.uuid4())
        resp = client.post(f"/api/events/{fake_id}/analyze")
        assert resp.status_code == 404

    @patch("app.core.llm_client.get_llm_client")
    def test_analyze_regenerates(self, mock_get_llm, db, event):
        """Should regenerate even if event already has analysis."""
        event.ai_summary = "Old summary"
        event.ai_implications = "Old implications"
        db.commit()

        mock_llm = MagicMock()
        mock_llm.chat_json.return_value = {
            "summary": "New regenerated summary.",
            "implications": "New regenerated implications.",
        }
        mock_get_llm.return_value = mock_llm

        resp = client.post(f"/api/events/{event.id}/analyze")
        assert resp.status_code == 200
        data = resp.json()
        assert "New regenerated" in data["ai_summary"]


# ═══════════════════════════════════════════════
# 3. Create event with AI analysis
# ═══════════════════════════════════════════════


class TestCreateEventWithAnalysis:
    """Test that POST create event now includes AI analysis."""

    @patch("app.core.llm_client.get_llm_client")
    def test_create_event_gets_analysis(self, mock_get_llm, workspace, competitor):
        """Manually created event should have AI analysis populated."""
        mock_llm = MagicMock()
        mock_llm.chat_json.return_value = {
            "summary": "Auto-generated summary on create.",
            "implications": "Auto-generated implications on create.",
        }
        mock_get_llm.return_value = mock_llm

        resp = client.post(
            f"/api/workspaces/{workspace.id}/competitors/{competitor.id}/events",
            json={
                "signal_type": "hiring",
                "title": "New hire event via API",
                "description": "Testing AI analysis on create",
                "severity": "medium",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["ai_summary"] is not None
        assert "Auto-generated" in data["ai_summary"]
        assert data["ai_implications"] is not None


# ═══════════════════════════════════════════════
# 4. Collector _upsert_event with AI analysis
# ═══════════════════════════════════════════════


class TestCollectorWithAnalysis:
    """Test that collector _upsert_event triggers AI analysis."""

    @patch("app.core.llm_client.get_llm_client")
    def test_upsert_triggers_analysis(self, mock_get_llm, db, workspace, competitor):
        """Collector _upsert_event should call generate_signal_analysis."""
        mock_llm = MagicMock()
        mock_llm.chat_json.return_value = {
            "summary": "Collector-generated summary.",
            "implications": "Collector-generated implications.",
        }
        mock_get_llm.return_value = mock_llm

        from app.services.collectors.hiring_collector import HiringCollector
        collector = HiringCollector(db)

        event_data = {
            "title": "TestComp hiring 3 ML engineers",
            "description": "3 ML roles posted",
            "source_url": "https://testcomp.com/careers",
            "severity": "medium",
            "metadata_json": {"roles": 3},
        }
        created = collector._upsert_event(competitor, event_data)
        assert created is True

        # Verify AI analysis was generated
        ev = db.query(CompetitorEvent).filter(
            CompetitorEvent.competitor_id == competitor.id,
            CompetitorEvent.title == "TestComp hiring 3 ML engineers",
        ).first()
        assert ev is not None
        assert ev.ai_summary is not None
        assert ev.ai_implications is not None


# ═══════════════════════════════════════════════
# 5. Regression: existing endpoints still work
# ═══════════════════════════════════════════════


class TestRegression:
    """Ensure existing endpoints still work after changes."""

    def test_health_check(self):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_signal_types(self):
        resp = client.get("/api/events/signal-types")
        assert resp.status_code == 200
        assert len(resp.json()) == 12

    def test_get_event(self, event):
        resp = client.get(f"/api/events/{event.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "TestComp hiring 5 engineers"

    def test_list_events(self, workspace, event):
        resp = client.get(f"/api/workspaces/{workspace.id}/events")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    def test_activity_feed(self, workspace, event):
        resp = client.get(f"/api/workspaces/{workspace.id}/activity")
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) >= 1
        assert any(i["source"] == "competitor_event" for i in items)

    def test_changes_list(self, workspace):
        resp = client.get(f"/api/changes?workspace_id={workspace.id}")
        assert resp.status_code == 200
