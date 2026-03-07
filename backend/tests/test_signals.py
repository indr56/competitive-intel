"""
Tests for multi-signal competitive intelligence engine:
- SignalType enum
- CompetitorEvent model
- Events API (CRUD, filtering, activity feed)
- Collector base class (dedup, upsert)
- Individual collectors (blog, hiring, funding, review)
- Regression tests for existing endpoints
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.core.database import Base, get_db
from app.main import app
from app.models.models import (
    Account,
    Competitor,
    CompetitorEvent,
    SignalType,
    Workspace,
)

# ── Test DB setup ──

DATABASE_URL = "postgresql://compintel:compintel@localhost:5432/compintel_test"

from sqlalchemy import create_engine as _ce, text as _text
_tmp = _ce("postgresql://compintel:compintel@localhost:5432/compintel", isolation_level="AUTOCOMMIT")
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
    account = Account(name="Signal Test Account", slug="signal-test", plan="free")
    db.add(account)
    db.flush()
    ws = Workspace(account_id=account.id, name="Signal WS", slug="signal-ws")
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


# ═══════════════════════════════════════════════
# 1. SignalType enum tests
# ═══════════════════════════════════════════════


class TestSignalType:
    def test_all_signal_types_exist(self):
        expected = {
            "website_change", "pricing_change", "product_change",
            "blog_post", "hiring", "funding", "review", "marketing",
            "positioning_change", "integration_added", "integration_removed",
            "landing_page_created",
        }
        actual = {t.value for t in SignalType}
        assert actual == expected

    def test_signal_type_values(self):
        assert SignalType.BLOG_POST.value == "blog_post"
        assert SignalType.HIRING.value == "hiring"
        assert SignalType.FUNDING.value == "funding"
        assert SignalType.REVIEW.value == "review"
        assert SignalType.MARKETING.value == "marketing"


# ═══════════════════════════════════════════════
# 2. CompetitorEvent model tests
# ═══════════════════════════════════════════════


class TestCompetitorEventModel:
    def test_create_event(self, db, workspace, competitor):
        event = CompetitorEvent(
            workspace_id=workspace.id,
            competitor_id=competitor.id,
            signal_type=SignalType.BLOG_POST.value,
            title="New blog post: AI features launch",
            description="Competitor announced new AI features",
            source_url="https://testcomp.com/blog/ai-launch",
            severity="medium",
        )
        db.add(event)
        db.commit()
        db.refresh(event)

        assert event.id is not None
        assert event.signal_type == "blog_post"
        assert event.title == "New blog post: AI features launch"
        assert event.severity == "medium"

    def test_dedup_constraint(self, db, workspace, competitor):
        """Same competitor + signal_type + source_url + title should fail."""
        event1 = CompetitorEvent(
            workspace_id=workspace.id,
            competitor_id=competitor.id,
            signal_type=SignalType.BLOG_POST.value,
            title="Same title",
            source_url="https://testcomp.com/blog/same",
        )
        db.add(event1)
        db.commit()

        event2 = CompetitorEvent(
            workspace_id=workspace.id,
            competitor_id=competitor.id,
            signal_type=SignalType.BLOG_POST.value,
            title="Same title",
            source_url="https://testcomp.com/blog/same",
        )
        db.add(event2)
        with pytest.raises(Exception):
            db.commit()
        db.rollback()

    def test_different_signal_types_allowed(self, db, workspace, competitor):
        """Same title but different signal_type should be allowed."""
        for st in [SignalType.BLOG_POST, SignalType.FUNDING]:
            event = CompetitorEvent(
                workspace_id=workspace.id,
                competitor_id=competitor.id,
                signal_type=st.value,
                title="Company announcement",
                source_url="https://testcomp.com/news",
            )
            db.add(event)
        db.commit()

        count = db.query(CompetitorEvent).filter(
            CompetitorEvent.competitor_id == competitor.id
        ).count()
        assert count == 2

    def test_cascade_delete_with_competitor(self, db, workspace, competitor):
        """Events should be deleted when competitor is deleted."""
        event = CompetitorEvent(
            workspace_id=workspace.id,
            competitor_id=competitor.id,
            signal_type=SignalType.HIRING.value,
            title="Hiring engineers",
        )
        db.add(event)
        db.commit()

        db.delete(competitor)
        db.commit()

        count = db.query(CompetitorEvent).count()
        assert count == 0


# ═══════════════════════════════════════════════
# 3. Events API tests
# ═══════════════════════════════════════════════


class TestEventsAPI:
    def test_create_event(self, workspace, competitor):
        resp = client.post(
            f"/api/workspaces/{workspace.id}/competitors/{competitor.id}/events",
            json={
                "signal_type": "blog_post",
                "title": "New product launch",
                "description": "Competitor launched a new product",
                "source_url": "https://testcomp.com/blog/launch",
                "severity": "high",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["signal_type"] == "blog_post"
        assert data["title"] == "New product launch"
        assert data["severity"] == "high"
        assert data["competitor_id"] == str(competitor.id)

    def test_create_event_invalid_signal_type(self, workspace, competitor):
        resp = client.post(
            f"/api/workspaces/{workspace.id}/competitors/{competitor.id}/events",
            json={
                "signal_type": "invalid_type",
                "title": "Test",
            },
        )
        assert resp.status_code == 400
        assert "Invalid signal_type" in resp.json()["detail"]

    def test_list_workspace_events(self, workspace, competitor, db):
        for i in range(3):
            db.add(CompetitorEvent(
                workspace_id=workspace.id,
                competitor_id=competitor.id,
                signal_type=SignalType.BLOG_POST.value,
                title=f"Blog post {i}",
                source_url=f"https://testcomp.com/blog/{i}",
            ))
        db.commit()

        resp = client.get(f"/api/workspaces/{workspace.id}/events")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 3

    def test_filter_by_signal_type(self, workspace, competitor, db):
        db.add(CompetitorEvent(
            workspace_id=workspace.id,
            competitor_id=competitor.id,
            signal_type=SignalType.BLOG_POST.value,
            title="Blog",
        ))
        db.add(CompetitorEvent(
            workspace_id=workspace.id,
            competitor_id=competitor.id,
            signal_type=SignalType.HIRING.value,
            title="Hiring",
            source_url="https://testcomp.com/careers",
        ))
        db.commit()

        resp = client.get(f"/api/workspaces/{workspace.id}/events?signal_type=hiring")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["signal_type"] == "hiring"

    def test_filter_by_severity(self, workspace, competitor, db):
        db.add(CompetitorEvent(
            workspace_id=workspace.id,
            competitor_id=competitor.id,
            signal_type=SignalType.FUNDING.value,
            title="Series B",
            severity="critical",
        ))
        db.add(CompetitorEvent(
            workspace_id=workspace.id,
            competitor_id=competitor.id,
            signal_type=SignalType.BLOG_POST.value,
            title="Blog",
            severity="low",
        ))
        db.commit()

        resp = client.get(f"/api/workspaces/{workspace.id}/events?severity=critical")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["severity"] == "critical"

    def test_list_competitor_events(self, workspace, competitor, db):
        db.add(CompetitorEvent(
            workspace_id=workspace.id,
            competitor_id=competitor.id,
            signal_type=SignalType.REVIEW.value,
            title="G2: Rating changed",
        ))
        db.commit()

        resp = client.get(f"/api/competitors/{competitor.id}/events")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1

    def test_get_event(self, workspace, competitor, db):
        event = CompetitorEvent(
            workspace_id=workspace.id,
            competitor_id=competitor.id,
            signal_type=SignalType.FUNDING.value,
            title="Series C: $100M",
        )
        db.add(event)
        db.commit()
        db.refresh(event)

        resp = client.get(f"/api/events/{event.id}")
        assert resp.status_code == 200
        assert resp.json()["title"] == "Series C: $100M"

    def test_get_event_not_found(self):
        fake_id = uuid.uuid4()
        resp = client.get(f"/api/events/{fake_id}")
        assert resp.status_code == 404

    def test_signal_types_endpoint(self):
        resp = client.get("/api/events/signal-types")
        assert resp.status_code == 200
        types = resp.json()
        assert "blog_post" in types
        assert "hiring" in types
        assert "funding" in types
        assert "review" in types
        assert len(types) == 12


# ═══════════════════════════════════════════════
# 4. Activity feed tests
# ═══════════════════════════════════════════════


class TestActivityFeed:
    def test_empty_feed(self, workspace):
        resp = client.get(f"/api/workspaces/{workspace.id}/activity")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_feed_with_competitor_events(self, workspace, competitor, db):
        db.add(CompetitorEvent(
            workspace_id=workspace.id,
            competitor_id=competitor.id,
            signal_type=SignalType.BLOG_POST.value,
            title="New blog post",
            severity="low",
        ))
        db.add(CompetitorEvent(
            workspace_id=workspace.id,
            competitor_id=competitor.id,
            signal_type=SignalType.FUNDING.value,
            title="Series B funding",
            severity="critical",
            source_url="https://testcomp.com/funding",
        ))
        db.commit()

        resp = client.get(f"/api/workspaces/{workspace.id}/activity")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        # Check feed item structure
        item = data[0]
        assert "id" in item
        assert "source" in item
        assert "signal_type" in item
        assert "title" in item
        assert "competitor_name" in item
        assert item["source"] == "competitor_event"

    def test_feed_filter_by_signal_type(self, workspace, competitor, db):
        db.add(CompetitorEvent(
            workspace_id=workspace.id,
            competitor_id=competitor.id,
            signal_type=SignalType.HIRING.value,
            title="Hiring",
            source_url="https://testcomp.com/careers",
        ))
        db.add(CompetitorEvent(
            workspace_id=workspace.id,
            competitor_id=competitor.id,
            signal_type=SignalType.BLOG_POST.value,
            title="Blog",
        ))
        db.commit()

        resp = client.get(f"/api/workspaces/{workspace.id}/activity?signal_type=hiring")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["signal_type"] == "hiring"

    def test_feed_includes_competitor_name(self, workspace, competitor, db):
        db.add(CompetitorEvent(
            workspace_id=workspace.id,
            competitor_id=competitor.id,
            signal_type=SignalType.BLOG_POST.value,
            title="Blog",
        ))
        db.commit()

        resp = client.get(f"/api/workspaces/{workspace.id}/activity")
        assert resp.status_code == 200
        data = resp.json()
        assert data[0]["competitor_name"] == "TestComp"


# ═══════════════════════════════════════════════
# 5. Base collector tests
# ═══════════════════════════════════════════════


class TestBaseCollector:
    def test_upsert_creates_event(self, db, workspace, competitor):
        from app.services.collectors.base import BaseCollector
        from app.models.models import SignalType

        class DummyCollector(BaseCollector):
            signal_type = SignalType.BLOG_POST
            def collect_for_competitor(self, competitor):
                return [{"title": "Test post", "source_url": "https://x.com/test"}]

        collector = DummyCollector(db)
        result = collector.run_for_competitor(competitor)

        assert result.events_found == 1
        assert result.events_created == 1
        assert result.events_skipped_dedup == 0

    def test_upsert_dedup(self, db, workspace, competitor):
        from app.services.collectors.base import BaseCollector

        class DummyCollector(BaseCollector):
            signal_type = SignalType.BLOG_POST
            def collect_for_competitor(self, competitor):
                return [{"title": "Same post", "source_url": "https://x.com/same"}]

        collector = DummyCollector(db)

        # First run creates
        r1 = collector.run_for_competitor(competitor)
        assert r1.events_created == 1

        # Second run deduplicates
        r2 = collector.run_for_competitor(competitor)
        assert r2.events_created == 0
        assert r2.events_skipped_dedup == 1

    def test_run_for_workspace(self, db, workspace, competitor):
        from app.services.collectors.base import BaseCollector

        class DummyCollector(BaseCollector):
            signal_type = SignalType.BLOG_POST
            def collect_for_competitor(self, competitor):
                return [{"title": f"Post for {competitor.name}"}]

        collector = DummyCollector(db)
        result = collector.run_for_workspace(str(workspace.id))

        assert result["competitors_processed"] == 1
        assert result["events_created"] == 1
        assert result["signal_type"] == "blog_post"

    def test_collector_handles_errors(self, db, workspace, competitor):
        from app.services.collectors.base import BaseCollector

        class FailingCollector(BaseCollector):
            signal_type = SignalType.BLOG_POST
            def collect_for_competitor(self, competitor):
                raise RuntimeError("Network error")

        collector = FailingCollector(db)
        result = collector.run_for_competitor(competitor)

        assert result.events_found == 0
        assert result.events_created == 0
        assert len(result.errors) == 1
        assert "Network error" in result.errors[0]


# ═══════════════════════════════════════════════
# 6. Blog collector tests
# ═══════════════════════════════════════════════


class TestBlogCollector:
    def test_parse_rss(self, db, workspace, competitor):
        from app.services.collectors.blog_collector import BlogCollector

        rss_xml = """<?xml version="1.0"?>
        <rss version="2.0">
          <channel>
            <title>TestComp Blog</title>
            <item>
              <title>New Feature Launch</title>
              <link>https://testcomp.com/blog/feature</link>
              <description>We launched a new feature</description>
              <pubDate>Thu, 01 Jan 2026 12:00:00 GMT</pubDate>
            </item>
            <item>
              <title>Company Update</title>
              <link>https://testcomp.com/blog/update</link>
              <description>Quarterly update</description>
            </item>
          </channel>
        </rss>"""

        collector = BlogCollector(db)

        import xml.etree.ElementTree as ET
        root = ET.fromstring(rss_xml)
        entries = collector._parse_rss(root)

        assert len(entries) == 2
        assert entries[0]["title"] == "New Feature Launch"
        assert entries[0]["source_url"] == "https://testcomp.com/blog/feature"
        assert entries[1]["title"] == "Company Update"

    def test_parse_atom(self, db, workspace, competitor):
        from app.services.collectors.blog_collector import BlogCollector

        atom_xml = """<?xml version="1.0"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
          <title>TestComp Blog</title>
          <entry>
            <title>Atom Post</title>
            <link href="https://testcomp.com/blog/atom"/>
            <summary>Atom summary</summary>
            <updated>2026-01-15T10:00:00Z</updated>
          </entry>
        </feed>"""

        collector = BlogCollector(db)

        import xml.etree.ElementTree as ET
        root = ET.fromstring(atom_xml)
        entries = collector._parse_atom(root)

        assert len(entries) == 1
        assert entries[0]["title"] == "Atom Post"
        assert entries[0]["source_url"] == "https://testcomp.com/blog/atom"

    def test_collect_with_mock(self, db, workspace, competitor):
        from app.services.collectors.blog_collector import BlogCollector

        rss_response = """<?xml version="1.0"?>
        <rss version="2.0"><channel>
          <item><title>Mock Post</title><link>https://testcomp.com/blog/mock</link></item>
        </channel></rss>"""

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = rss_response
        mock_resp.headers = {"content-type": "application/xml"}
        mock_resp.raise_for_status = MagicMock()

        with patch("app.services.collectors.blog_collector.httpx.Client") as mock_client:
            mock_instance = MagicMock()
            mock_instance.__enter__ = MagicMock(return_value=mock_instance)
            mock_instance.__exit__ = MagicMock(return_value=False)
            mock_instance.get.return_value = mock_resp
            mock_client.return_value = mock_instance

            collector = BlogCollector(db)
            result = collector.run_for_competitor(competitor)

        assert result.events_found >= 1
        assert result.events_created >= 1


# ═══════════════════════════════════════════════
# 7. Hiring collector tests
# ═══════════════════════════════════════════════


class TestHiringCollector:
    def test_extract_ai_jobs(self, db, workspace, competitor):
        from app.services.collectors.hiring_collector import HiringCollector

        html = """
        <html><body>
        <h1>Careers</h1>
        <div>Machine Learning Engineer - Remote</div>
        <div>AI Engineer - San Francisco</div>
        <div>Deep Learning Researcher</div>
        <div>Software Engineer - Backend</div>
        <div>Product Manager</div>
        </body></html>
        """

        collector = HiringCollector(db)
        jobs = collector._extract_jobs(html, "https://testcomp.com/careers", competitor)

        ai_jobs = [j for j in jobs if j["metadata_json"]["category"] == "ai_ml"]
        assert len(ai_jobs) == 1
        assert ai_jobs[0]["metadata_json"]["role_count"] >= 3

    def test_extract_no_jobs(self, db, workspace, competitor):
        from app.services.collectors.hiring_collector import HiringCollector

        html = "<html><body><h1>About Us</h1><p>We are a company.</p></body></html>"

        collector = HiringCollector(db)
        jobs = collector._extract_jobs(html, "https://testcomp.com/about", competitor)
        assert len(jobs) == 0


# ═══════════════════════════════════════════════
# 8. Funding collector tests
# ═══════════════════════════════════════════════


class TestFundingCollector:
    def test_detect_funding_amount(self, db, workspace, competitor):
        from app.services.collectors.funding_collector import FundingCollector

        html = """
        <html><body>
        <h1>Press Release</h1>
        <p>TestComp raised $50 million in Series B funding led by Acme Ventures.</p>
        </body></html>
        """

        collector = FundingCollector(db)
        events = collector._detect_funding(html, "https://testcomp.com/press", competitor)

        assert len(events) >= 1
        assert "$50" in events[0]["title"] or "50" in events[0]["title"]
        assert events[0]["severity"] in ("high", "critical")

    def test_detect_acquisition(self, db, workspace, competitor):
        from app.services.collectors.funding_collector import FundingCollector

        html = """
        <html><body>
        <h1>News</h1>
        <p>BigCorp has acquired TestComp for an undisclosed sum.</p>
        </body></html>
        """

        collector = FundingCollector(db)
        events = collector._detect_funding(html, "https://testcomp.com/news", competitor)

        assert len(events) >= 1
        assert events[0]["severity"] == "critical"

    def test_no_funding_signal(self, db, workspace, competitor):
        from app.services.collectors.funding_collector import FundingCollector

        html = "<html><body><p>We love building great products.</p></body></html>"

        collector = FundingCollector(db)
        events = collector._detect_funding(html, "https://testcomp.com/about", competitor)
        assert len(events) == 0


# ═══════════════════════════════════════════════
# 9. Review collector tests
# ═══════════════════════════════════════════════


class TestReviewCollector:
    def test_extract_rating(self, db):
        from app.services.collectors.review_collector import ReviewCollector

        collector = ReviewCollector(db)

        assert collector._extract_rating("Rated 4.5 out of 5 stars") == 4.5
        assert collector._extract_rating("4.7/5 based on reviews") == 4.7
        assert collector._extract_rating("No rating here") is None

    def test_extract_review_count(self, db):
        from app.services.collectors.review_collector import ReviewCollector

        collector = ReviewCollector(db)

        assert collector._extract_review_count("Based on 1,234 reviews") == 1234
        assert collector._extract_review_count("500 ratings") == 500
        assert collector._extract_review_count("No count here") is None

    def test_build_review_event_new(self, db, workspace, competitor):
        from app.services.collectors.review_collector import ReviewCollector

        collector = ReviewCollector(db)
        events = collector._build_review_event(
            competitor, "g2", "https://g2.com/test", 4.5, 200
        )

        assert len(events) == 1
        assert "4.5" in events[0]["title"]
        assert events[0]["metadata_json"]["platform"] == "g2"
        assert events[0]["metadata_json"]["rating"] == 4.5
        assert events[0]["metadata_json"]["review_count"] == 200


# ═══════════════════════════════════════════════
# 10. Regression tests
# ═══════════════════════════════════════════════


class TestRegression:
    def test_health_check(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_list_workspaces(self):
        resp = client.get("/api/workspaces")
        assert resp.status_code == 200

    def test_billing_plans(self):
        resp = client.get("/api/billing/plans")
        assert resp.status_code == 200
        assert len(resp.json()) == 3

    def test_changes_list(self, workspace):
        resp = client.get(f"/api/changes?workspace_id={workspace.id}")
        assert resp.status_code == 200

    def test_digests_list(self, workspace):
        resp = client.get(f"/api/workspaces/{workspace.id}/digests")
        assert resp.status_code == 200

    def test_competitor_crud(self, workspace):
        # Create
        resp = client.post(
            f"/api/workspaces/{workspace.id}/competitors",
            json={"name": "Regression Test", "domain": "regtest.com"},
        )
        assert resp.status_code == 201
        comp_id = resp.json()["id"]

        # List
        resp = client.get(f"/api/workspaces/{workspace.id}/competitors")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

        # Delete
        resp = client.delete(f"/api/competitors/{comp_id}")
        assert resp.status_code == 204

    def test_events_and_activity_endpoints_exist(self, workspace, competitor):
        """Verify new endpoints don't break existing routes."""
        resp = client.get(f"/api/workspaces/{workspace.id}/events")
        assert resp.status_code == 200

        resp = client.get(f"/api/workspaces/{workspace.id}/activity")
        assert resp.status_code == 200

        resp = client.get("/api/events/signal-types")
        assert resp.status_code == 200
