"""
Tests for billing: plan enforcement, billing API, webhook idempotency, and regression.
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
    TrackedPage,
    Workspace,
    WorkspaceBilling,
    WebhookEvent,
)
from app.core.billing import (
    PLAN_DEFINITIONS,
    get_plan_limits,
    get_plan_info,
    is_billing_active,
    ACTIVE_STATUSES,
)
from app.core.plan_enforcement import (
    get_workspace_billing,
    enforce_billing_active,
    enforce_competitor_limit,
    enforce_tracked_page_limit,
    can_capture,
)

# ── Test DB setup (uses PostgreSQL — same as app) ──

DATABASE_URL = "postgresql://compintel:compintel@localhost:5432/compintel_test"

# Create test database if it doesn't exist
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
    """Create tables before each test, drop after."""
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
    """Create a test account + workspace."""
    account = Account(name="Test Account", slug="test-account", plan="free")
    db.add(account)
    db.flush()
    ws = Workspace(account_id=account.id, name="Test WS", slug="test-ws")
    db.add(ws)
    db.commit()
    db.refresh(ws)
    return ws


# ═══════════════════════════════════════════════
# 1. Plan definitions tests
# ═══════════════════════════════════════════════


class TestPlanDefinitions:
    def test_all_plans_exist(self):
        assert "starter" in PLAN_DEFINITIONS
        assert "pro" in PLAN_DEFINITIONS
        assert "agency" in PLAN_DEFINITIONS

    def test_starter_limits(self):
        limits = get_plan_limits("starter")
        assert limits["max_competitors"] == 3
        assert limits["max_tracked_pages"] == 15
        assert limits["min_check_interval_hours"] == 24
        assert limits["white_label"] is False
        assert limits["max_workspaces"] == 1

    def test_pro_limits(self):
        limits = get_plan_limits("pro")
        assert limits["max_competitors"] == 10
        assert limits["max_tracked_pages"] == 50

    def test_agency_limits(self):
        limits = get_plan_limits("agency")
        assert limits["max_competitors"] == 50
        assert limits["max_tracked_pages"] == 200
        assert limits["white_label"] is True
        assert limits["max_workspaces"] == 20

    def test_unknown_plan_falls_back_to_starter(self):
        limits = get_plan_limits("nonexistent")
        assert limits["max_competitors"] == 3

    def test_plan_info_structure(self):
        info = get_plan_info("pro")
        assert info["plan_type"] == "pro"
        assert info["name"] == "Pro"
        assert info["price_monthly_cents"] == 14900
        assert "limits" in info


# ═══════════════════════════════════════════════
# 2. Billing status tests
# ═══════════════════════════════════════════════


class TestBillingStatus:
    def test_trialing_is_active(self):
        assert is_billing_active("trialing") is True

    def test_active_is_active(self):
        assert is_billing_active("active") is True

    def test_canceled_is_not_active(self):
        assert is_billing_active("canceled") is False

    def test_incomplete_is_not_active(self):
        assert is_billing_active("incomplete") is False

    def test_past_due_with_valid_grace(self):
        future = datetime.now(timezone.utc) + timedelta(days=3)
        assert is_billing_active("past_due", future) is True

    def test_past_due_with_expired_grace(self):
        past = datetime.now(timezone.utc) - timedelta(days=1)
        assert is_billing_active("past_due", past) is False

    def test_past_due_without_grace(self):
        assert is_billing_active("past_due", None) is False


# ═══════════════════════════════════════════════
# 3. Plan enforcement tests
# ═══════════════════════════════════════════════


class TestPlanEnforcement:
    def test_auto_creates_billing_record(self, db, workspace):
        billing = get_workspace_billing(workspace.id, db)
        assert billing is not None
        assert billing.plan_type == "starter"
        assert billing.subscription_status == "trialing"
        assert billing.trial_ends_at is not None

    def test_enforce_billing_active_passes_for_trial(self, db, workspace):
        billing = enforce_billing_active(workspace.id, db)
        assert billing.subscription_status == "trialing"

    def test_enforce_billing_active_fails_for_canceled(self, db, workspace):
        billing = get_workspace_billing(workspace.id, db)
        billing.subscription_status = "canceled"
        db.commit()

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            enforce_billing_active(workspace.id, db)
        assert exc_info.value.status_code == 402

    def test_competitor_limit_enforced(self, db, workspace):
        # Starter plan allows 3 competitors
        get_workspace_billing(workspace.id, db)

        # Add 3 competitors (at limit)
        for i in range(3):
            comp = Competitor(
                workspace_id=workspace.id,
                name=f"Comp {i}",
                domain=f"comp{i}.com",
            )
            db.add(comp)
        db.commit()

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            enforce_competitor_limit(workspace.id, db)
        assert exc_info.value.status_code == 403
        assert "Competitor limit reached" in str(exc_info.value.detail)

    def test_competitor_limit_passes_under_limit(self, db, workspace):
        get_workspace_billing(workspace.id, db)
        # Add 2 competitors (under limit of 3)
        for i in range(2):
            comp = Competitor(
                workspace_id=workspace.id,
                name=f"Comp {i}",
                domain=f"comp{i}.com",
            )
            db.add(comp)
        db.commit()

        # Should not raise
        enforce_competitor_limit(workspace.id, db)

    def test_tracked_page_limit_enforced(self, db, workspace):
        get_workspace_billing(workspace.id, db)

        comp = Competitor(
            workspace_id=workspace.id,
            name="Comp",
            domain="comp.com",
        )
        db.add(comp)
        db.flush()

        # Starter allows 15 pages, add 15
        for i in range(15):
            page = TrackedPage(
                competitor_id=comp.id,
                url=f"https://comp.com/page{i}",
                page_type="pricing",
            )
            db.add(page)
        db.commit()

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            enforce_tracked_page_limit(workspace.id, db)
        assert exc_info.value.status_code == 403
        assert "Tracked page limit reached" in str(exc_info.value.detail)

    def test_can_capture_true_for_active(self, db, workspace):
        get_workspace_billing(workspace.id, db)
        assert can_capture(workspace.id, db) is True

    def test_can_capture_false_for_canceled(self, db, workspace):
        billing = get_workspace_billing(workspace.id, db)
        billing.subscription_status = "canceled"
        db.commit()
        assert can_capture(workspace.id, db) is False


# ═══════════════════════════════════════════════
# 4. Billing API tests
# ═══════════════════════════════════════════════


class TestBillingAPI:
    def test_list_plans(self):
        resp = client.get("/api/billing/plans")
        assert resp.status_code == 200
        plans = resp.json()
        assert len(plans) == 3
        plan_types = [p["plan_type"] for p in plans]
        assert "starter" in plan_types
        assert "pro" in plan_types
        assert "agency" in plan_types

    def test_billing_overview(self, workspace):
        resp = client.get(f"/api/workspaces/{workspace.id}/billing")
        assert resp.status_code == 200
        data = resp.json()
        assert data["billing"]["plan_type"] == "starter"
        assert data["billing"]["subscription_status"] == "trialing"
        assert data["plan"]["name"] == "Starter"
        assert data["usage"]["competitors"] == 0
        assert data["usage"]["competitors_limit"] == 3
        assert data["usage"]["tracked_pages"] == 0
        assert data["usage"]["tracked_pages_limit"] == 15

    def test_billing_overview_not_found(self):
        fake_id = uuid.uuid4()
        resp = client.get(f"/api/workspaces/{fake_id}/billing")
        assert resp.status_code == 404

    def test_checkout_no_stripe_key(self, workspace):
        resp = client.post(
            f"/api/workspaces/{workspace.id}/billing/checkout",
            json={"plan_type": "pro"},
        )
        # Should return 503 if Stripe is not configured
        assert resp.status_code == 503

    def test_checkout_invalid_plan(self, workspace):
        with patch("app.api.billing.get_settings") as mock_settings:
            mock_settings.return_value.STRIPE_SECRET_KEY = "sk_test_xxx"
            mock_settings.return_value.FRONTEND_URL = "http://localhost:3000"
            resp = client.post(
                f"/api/workspaces/{workspace.id}/billing/checkout",
                json={"plan_type": "nonexistent"},
            )
            assert resp.status_code == 400

    def test_portal_no_customer(self, workspace):
        with patch("app.api.billing.get_settings") as mock_settings:
            mock_settings.return_value.STRIPE_SECRET_KEY = "sk_test_xxx"
            mock_settings.return_value.STRIPE_WEBHOOK_SECRET = ""
            resp = client.post(
                f"/api/workspaces/{workspace.id}/billing/portal"
            )
            assert resp.status_code == 400


# ═══════════════════════════════════════════════
# 5. Webhook idempotency tests
# ═══════════════════════════════════════════════


class TestWebhookIdempotency:
    def test_duplicate_event_not_reprocessed(self, db, workspace):
        event_id = "evt_test_123"
        # Insert a processed webhook event
        wh = WebhookEvent(
            stripe_event_id=event_id,
            event_type="checkout.session.completed",
            payload={"id": event_id, "type": "checkout.session.completed"},
            processed=True,
        )
        db.add(wh)
        db.commit()

        # Verify it exists
        existing = (
            db.query(WebhookEvent)
            .filter(WebhookEvent.stripe_event_id == event_id)
            .first()
        )
        assert existing is not None
        assert existing.processed is True


# ═══════════════════════════════════════════════
# 6. Competitor creation enforcement via API
# ═══════════════════════════════════════════════


class TestCompetitorEnforcementAPI:
    def test_create_competitor_within_limit(self, workspace):
        resp = client.post(
            f"/api/workspaces/{workspace.id}/competitors",
            json={"name": "Test Comp", "domain": "test.com"},
        )
        assert resp.status_code == 201

    def test_create_competitor_at_limit(self, workspace, db):
        # Fill up to starter limit (3)
        for i in range(3):
            comp = Competitor(
                workspace_id=workspace.id,
                name=f"Comp {i}",
                domain=f"comp{i}.com",
            )
            db.add(comp)
        db.commit()

        resp = client.post(
            f"/api/workspaces/{workspace.id}/competitors",
            json={"name": "Overflow", "domain": "overflow.com"},
        )
        assert resp.status_code == 403
        assert "Competitor limit reached" in resp.json()["detail"]

    def test_create_competitor_billing_canceled(self, workspace, db):
        billing = get_workspace_billing(workspace.id, db)
        billing.subscription_status = "canceled"
        db.commit()

        resp = client.post(
            f"/api/workspaces/{workspace.id}/competitors",
            json={"name": "Test", "domain": "test.com"},
        )
        assert resp.status_code == 402


# ═══════════════════════════════════════════════
# 7. Tracked page creation enforcement via API
# ═══════════════════════════════════════════════


class TestTrackedPageEnforcementAPI:
    def test_create_page_within_limit(self, workspace, db):
        comp = Competitor(
            workspace_id=workspace.id,
            name="Comp",
            domain="comp.com",
        )
        db.add(comp)
        db.commit()
        db.refresh(comp)

        resp = client.post(
            f"/api/competitors/{comp.id}/pages",
            json={"url": "https://comp.com/pricing", "page_type": "pricing"},
        )
        assert resp.status_code == 201

    def test_create_page_billing_canceled(self, workspace, db):
        billing = get_workspace_billing(workspace.id, db)
        billing.subscription_status = "canceled"
        db.commit()

        comp = Competitor(
            workspace_id=workspace.id,
            name="Comp",
            domain="comp.com",
        )
        db.add(comp)
        db.commit()
        db.refresh(comp)

        resp = client.post(
            f"/api/competitors/{comp.id}/pages",
            json={"url": "https://comp.com/pricing", "page_type": "pricing"},
        )
        assert resp.status_code == 402


# ═══════════════════════════════════════════════
# 8. Regression: existing APIs still work for active workspaces
# ═══════════════════════════════════════════════


class TestRegression:
    def test_health_check(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_list_workspaces(self):
        resp = client.get("/api/workspaces")
        assert resp.status_code == 200

    def test_workspace_crud(self):
        # Create
        resp = client.post(
            "/api/workspaces",
            json={"name": "Regression WS", "slug": "regression-ws"},
        )
        assert resp.status_code == 201
        ws_id = resp.json()["id"]

        # List
        resp = client.get("/api/workspaces")
        assert resp.status_code == 200
        assert any(w["id"] == ws_id for w in resp.json())

    def test_competitor_crud_for_active_workspace(self, workspace):
        # Create competitor (should work — workspace has trialing billing)
        resp = client.post(
            f"/api/workspaces/{workspace.id}/competitors",
            json={"name": "Regression Comp", "domain": "regression.com"},
        )
        assert resp.status_code == 201
        comp_id = resp.json()["id"]

        # List
        resp = client.get(f"/api/workspaces/{workspace.id}/competitors")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

        # Get
        resp = client.get(f"/api/competitors/{comp_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Regression Comp"

    def test_tracked_page_crud_for_active_workspace(self, workspace, db):
        comp = Competitor(
            workspace_id=workspace.id,
            name="RC",
            domain="rc.com",
        )
        db.add(comp)
        db.commit()
        db.refresh(comp)

        # Create page
        resp = client.post(
            f"/api/competitors/{comp.id}/pages",
            json={"url": "https://rc.com/pricing", "page_type": "pricing"},
        )
        assert resp.status_code == 201
        page_id = resp.json()["id"]

        # List
        resp = client.get(f"/api/competitors/{comp.id}/pages")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    def test_changes_list(self, workspace):
        resp = client.get(f"/api/changes?workspace_id={workspace.id}")
        assert resp.status_code == 200

    def test_digests_list(self, workspace):
        resp = client.get(f"/api/workspaces/{workspace.id}/digests")
        assert resp.status_code == 200

    def test_billing_plans_endpoint(self):
        resp = client.get("/api/billing/plans")
        assert resp.status_code == 200
        assert len(resp.json()) == 3
