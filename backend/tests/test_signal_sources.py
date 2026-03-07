"""
Tests for Signal Sources, Test Source, Scan Signals, and collector source priority.
"""

import uuid
from datetime import datetime, timezone
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
    SignalSource,
    SignalType,
    SourceKind,
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
    account = Account(name="Source Test Account", slug="source-test", plan="free")
    db.add(account)
    db.flush()
    ws = Workspace(account_id=account.id, name="Source WS", slug="source-ws")
    db.add(ws)
    db.commit()
    db.refresh(ws)
    return ws


@pytest.fixture
def competitor(db: Session, workspace):
    comp = Competitor(
        workspace_id=workspace.id,
        name="SourceComp",
        domain="sourcecomp.com",
    )
    db.add(comp)
    db.commit()
    db.refresh(comp)
    return comp


# ═══════════════════════════════════════════════
# 1. SignalSource model tests
# ═══════════════════════════════════════════════


class TestSignalSourceModel:
    def test_create_source(self, db, workspace, competitor):
        source = SignalSource(
            workspace_id=workspace.id,
            competitor_id=competitor.id,
            signal_type=SignalType.BLOG_POST.value,
            source_url="https://sourcecomp.com/blog/feed",
            source_label="Main Blog",
            source_kind=SourceKind.MANUAL.value,
        )
        db.add(source)
        db.commit()
        db.refresh(source)

        assert source.id is not None
        assert source.signal_type == "blog_post"
        assert source.is_active is True
        assert source.poll_interval_hours == 12
        assert source.source_kind == "manual"

    def test_dedup_constraint(self, db, workspace, competitor):
        s1 = SignalSource(
            workspace_id=workspace.id,
            competitor_id=competitor.id,
            signal_type="blog_post",
            source_url="https://sourcecomp.com/feed",
        )
        db.add(s1)
        db.commit()

        s2 = SignalSource(
            workspace_id=workspace.id,
            competitor_id=competitor.id,
            signal_type="blog_post",
            source_url="https://sourcecomp.com/feed",
        )
        db.add(s2)
        with pytest.raises(Exception):
            db.commit()
        db.rollback()

    def test_different_types_allowed(self, db, workspace, competitor):
        for st in ["blog_post", "hiring"]:
            db.add(SignalSource(
                workspace_id=workspace.id,
                competitor_id=competitor.id,
                signal_type=st,
                source_url="https://sourcecomp.com/page",
            ))
        db.commit()
        count = db.query(SignalSource).filter(SignalSource.competitor_id == competitor.id).count()
        assert count == 2

    def test_cascade_delete(self, db, workspace, competitor):
        db.add(SignalSource(
            workspace_id=workspace.id,
            competitor_id=competitor.id,
            signal_type="hiring",
            source_url="https://sourcecomp.com/careers",
        ))
        db.commit()
        db.delete(competitor)
        db.commit()
        assert db.query(SignalSource).count() == 0


# ═══════════════════════════════════════════════
# 2. Signal Sources API CRUD
# ═══════════════════════════════════════════════


class TestSignalSourcesAPI:
    def test_create_source(self, workspace, competitor):
        resp = client.post(
            f"/api/competitors/{competitor.id}/sources",
            json={
                "signal_type": "blog_post",
                "source_url": "https://sourcecomp.com/blog/rss",
                "source_label": "Blog RSS",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["signal_type"] == "blog_post"
        assert data["source_url"] == "https://sourcecomp.com/blog/rss"
        assert data["source_label"] == "Blog RSS"
        assert data["is_active"] is True
        assert data["source_kind"] == "manual"

    def test_create_invalid_signal_type(self, workspace, competitor):
        resp = client.post(
            f"/api/competitors/{competitor.id}/sources",
            json={"signal_type": "website_change", "source_url": "https://x.com"},
        )
        assert resp.status_code == 400
        assert "Invalid signal_type" in resp.json()["detail"]

    def test_create_for_missing_competitor(self):
        fake_id = uuid.uuid4()
        resp = client.post(
            f"/api/competitors/{fake_id}/sources",
            json={"signal_type": "blog_post", "source_url": "https://x.com"},
        )
        assert resp.status_code == 404

    def test_list_sources(self, workspace, competitor, db):
        for i, st in enumerate(["blog_post", "hiring", "funding"]):
            db.add(SignalSource(
                workspace_id=workspace.id,
                competitor_id=competitor.id,
                signal_type=st,
                source_url=f"https://sourcecomp.com/{st}/{i}",
            ))
        db.commit()

        resp = client.get(f"/api/competitors/{competitor.id}/sources")
        assert resp.status_code == 200
        assert len(resp.json()) == 3

    def test_list_filter_by_type(self, workspace, competitor, db):
        db.add(SignalSource(workspace_id=workspace.id, competitor_id=competitor.id,
                            signal_type="blog_post", source_url="https://x.com/blog"))
        db.add(SignalSource(workspace_id=workspace.id, competitor_id=competitor.id,
                            signal_type="hiring", source_url="https://x.com/careers"))
        db.commit()

        resp = client.get(f"/api/competitors/{competitor.id}/sources?signal_type=hiring")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["signal_type"] == "hiring"

    def test_get_source(self, workspace, competitor, db):
        source = SignalSource(
            workspace_id=workspace.id,
            competitor_id=competitor.id,
            signal_type="blog_post",
            source_url="https://x.com/feed",
        )
        db.add(source)
        db.commit()
        db.refresh(source)

        resp = client.get(f"/api/sources/{source.id}")
        assert resp.status_code == 200
        assert resp.json()["source_url"] == "https://x.com/feed"

    def test_get_source_not_found(self):
        resp = client.get(f"/api/sources/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_update_source(self, workspace, competitor, db):
        source = SignalSource(
            workspace_id=workspace.id,
            competitor_id=competitor.id,
            signal_type="blog_post",
            source_url="https://x.com/feed",
            source_label="Old Label",
        )
        db.add(source)
        db.commit()
        db.refresh(source)

        resp = client.patch(
            f"/api/sources/{source.id}",
            json={"source_label": "New Label", "poll_interval_hours": 6, "is_active": False},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["source_label"] == "New Label"
        assert data["poll_interval_hours"] == 6
        assert data["is_active"] is False

    def test_delete_source(self, workspace, competitor, db):
        source = SignalSource(
            workspace_id=workspace.id,
            competitor_id=competitor.id,
            signal_type="blog_post",
            source_url="https://x.com/feed",
        )
        db.add(source)
        db.commit()
        db.refresh(source)

        resp = client.delete(f"/api/sources/{source.id}")
        assert resp.status_code == 204

        resp = client.get(f"/api/sources/{source.id}")
        assert resp.status_code == 404


# ═══════════════════════════════════════════════
# 3. Test Source endpoint
# ═══════════════════════════════════════════════


class TestTestSource:
    def test_test_existing_source(self, workspace, competitor, db):
        source = SignalSource(
            workspace_id=workspace.id,
            competitor_id=competitor.id,
            signal_type="hiring",
            source_url="https://httpbin.org/html",
        )
        db.add(source)
        db.commit()
        db.refresh(source)

        resp = client.post(f"/api/sources/{source.id}/test")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("valid", "unreachable", "no_items_found", "unexpected_content")
        assert "message" in data

    def test_test_url_adhoc(self):
        resp = client.post(
            "/api/sources/test-url?signal_type=hiring&source_url=https%3A%2F%2Fhttpbin.org%2Fhtml"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("valid", "unreachable", "no_items_found", "unexpected_content")

    def test_test_url_invalid_type(self):
        resp = client.post(
            "/api/sources/test-url?signal_type=invalid_type&source_url=https%3A%2F%2Fx.com"
        )
        assert resp.status_code == 400

    def test_test_unreachable(self, workspace, competitor, db):
        source = SignalSource(
            workspace_id=workspace.id,
            competitor_id=competitor.id,
            signal_type="blog_post",
            source_url="https://this-domain-does-not-exist-xyz-123.com/feed",
        )
        db.add(source)
        db.commit()
        db.refresh(source)

        resp = client.post(f"/api/sources/{source.id}/test")
        assert resp.status_code == 200
        assert resp.json()["status"] == "unreachable"


# ═══════════════════════════════════════════════
# 4. Scan Signals endpoint
# ═══════════════════════════════════════════════


class TestScanSignals:
    def test_scan_with_auto_discovery(self, workspace, competitor):
        """Scan with no configured sources triggers auto-discovery."""
        resp = client.post(f"/api/competitors/{competitor.id}/scan")
        assert resp.status_code == 200
        data = resp.json()
        assert data["competitor_id"] == str(competitor.id)
        assert data["competitor_name"] == "SourceComp"
        assert "results" in data
        assert data["sources_scanned"] >= 1

    def test_scan_with_configured_source(self, workspace, competitor, db):
        """Scan uses configured manual source."""
        db.add(SignalSource(
            workspace_id=workspace.id,
            competitor_id=competitor.id,
            signal_type="hiring",
            source_url="https://httpbin.org/html",
        ))
        db.commit()

        resp = client.post(f"/api/competitors/{competitor.id}/scan?signal_types=hiring")
        assert resp.status_code == 200
        data = resp.json()
        hiring_results = [r for r in data["results"] if r["signal_type"] == "hiring"]
        assert len(hiring_results) >= 1
        assert hiring_results[0]["source_url"] == "https://httpbin.org/html"

    def test_scan_filter_by_type(self, workspace, competitor):
        resp = client.post(f"/api/competitors/{competitor.id}/scan?signal_types=blog_post")
        assert resp.status_code == 200
        data = resp.json()
        types = {r["signal_type"] for r in data["results"]}
        assert "blog_post" in types
        assert "hiring" not in types

    def test_scan_missing_competitor(self):
        resp = client.post(f"/api/competitors/{uuid.uuid4()}/scan")
        assert resp.status_code == 404


# ═══════════════════════════════════════════════
# 5. Collector source priority tests
# ═══════════════════════════════════════════════


class TestCollectorPriority:
    def test_manual_source_takes_priority(self, db, workspace, competitor):
        """When a manual source exists, scan_service uses collect_for_url."""
        from app.services.scan_service import scan_competitor

        db.add(SignalSource(
            workspace_id=workspace.id,
            competitor_id=competitor.id,
            signal_type="hiring",
            source_url="https://httpbin.org/html",
            source_kind="manual",
        ))
        db.commit()

        result = scan_competitor(db, competitor, signal_types=["hiring"])

        hiring = [r for r in result.results if r.signal_type == "hiring"]
        assert len(hiring) == 1
        assert hiring[0].source_url == "https://httpbin.org/html"

    def test_auto_discovery_when_no_source(self, db, workspace, competitor):
        """When no source is configured, auto-discovery is used."""
        from app.services.scan_service import scan_competitor

        result = scan_competitor(db, competitor, signal_types=["blog_post"])

        blog = [r for r in result.results if r.signal_type == "blog_post"]
        assert len(blog) == 1
        assert blog[0].source_url is None  # auto-discovery, no specific URL

    def test_inactive_source_skipped(self, db, workspace, competitor):
        """Inactive sources are not used; falls back to auto-discovery."""
        from app.services.scan_service import scan_competitor

        db.add(SignalSource(
            workspace_id=workspace.id,
            competitor_id=competitor.id,
            signal_type="hiring",
            source_url="https://httpbin.org/html",
            is_active=False,
        ))
        db.commit()

        result = scan_competitor(db, competitor, signal_types=["hiring"])
        hiring = [r for r in result.results if r.signal_type == "hiring"]
        assert len(hiring) == 1
        assert hiring[0].source_url is None  # fell back to auto-discovery


# ═══════════════════════════════════════════════
# 6. Test source validation logic
# ═══════════════════════════════════════════════


class TestSourceValidation:
    def test_blog_rss_validation(self):
        from app.services.scan_service import _test_blog_source

        rss = """<?xml version="1.0"?><rss><channel>
        <item><title>Post 1</title></item>
        <item><title>Post 2</title></item>
        </channel></rss>"""

        result = _test_blog_source(rss, "application/xml", "https://x.com/feed")
        assert result.status == "valid"
        assert result.items_found == 2

    def test_blog_atom_validation(self):
        from app.services.scan_service import _test_blog_source

        atom = """<?xml version="1.0"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
        <entry><title>A</title></entry>
        <entry><title>B</title></entry>
        <entry><title>C</title></entry>
        </feed>"""

        result = _test_blog_source(atom, "application/atom+xml", "https://x.com/feed")
        assert result.status == "valid"
        assert result.items_found == 3

    def test_blog_no_feed(self):
        from app.services.scan_service import _test_blog_source
        result = _test_blog_source("<html><body>Hello</body></html>", "text/html", "https://x.com")
        assert result.status == "unexpected_content"

    def test_hiring_validation(self):
        from app.services.scan_service import _test_hiring_source
        html = "<html><body>Careers: We're hiring engineers, managers, designers. Open positions. Join our team.</body></html>"
        result = _test_hiring_source(html, "https://x.com/careers")
        assert result.status == "valid"

    def test_hiring_no_jobs(self):
        from app.services.scan_service import _test_hiring_source
        result = _test_hiring_source("<html><body>About us</body></html>", "https://x.com/about")
        assert result.status == "no_items_found"

    def test_funding_validation(self):
        from app.services.scan_service import _test_funding_source
        html = "<html><body>Series B funding announcement. We raised investment capital.</body></html>"
        result = _test_funding_source(html, "https://x.com/press")
        assert result.status == "valid"

    def test_review_validation(self):
        from app.services.scan_service import _test_review_source
        html = "<html><body>4.5 out of 5 stars based on 1,234 reviews</body></html>"
        result = _test_review_source(html, "https://g2.com/products/x")
        assert result.status == "valid"
        assert result.items_found == 1

    def test_marketing_validation(self):
        from app.services.scan_service import _test_marketing_source
        html = "<html><body>Switch from Competitor. Free trial. Get started today.</body></html>"
        result = _test_marketing_source(html, "https://x.com/vs-competitor")
        assert result.status == "valid"


# ═══════════════════════════════════════════════
# 7. Regression tests
# ═══════════════════════════════════════════════


class TestRegression:
    def test_health_check(self):
        resp = client.get("/health")
        assert resp.status_code == 200

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

    def test_activity_feed(self, workspace):
        resp = client.get(f"/api/workspaces/{workspace.id}/activity")
        assert resp.status_code == 200

    def test_events_list(self, workspace):
        resp = client.get(f"/api/workspaces/{workspace.id}/events")
        assert resp.status_code == 200

    def test_signal_types(self):
        resp = client.get("/api/events/signal-types")
        assert resp.status_code == 200
        assert len(resp.json()) == 12

    def test_competitor_crud(self, workspace):
        resp = client.post(
            f"/api/workspaces/{workspace.id}/competitors",
            json={"name": "RegTest", "domain": "regtest.com"},
        )
        assert resp.status_code == 201
        comp_id = resp.json()["id"]

        resp = client.get(f"/api/workspaces/{workspace.id}/competitors")
        assert resp.status_code == 200

        resp = client.delete(f"/api/competitors/{comp_id}")
        assert resp.status_code == 204
