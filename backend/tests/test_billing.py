"""
Tests for billing: plan enforcement, Razorpay billing API, webhook idempotency, and regression.
"""

import hashlib
import hmac
import json
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
    RAZORPAY_STATUS_MAP,
    get_plan_limits,
    get_plan_info,
    is_billing_active,
    map_razorpay_status,
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
# 2b. Razorpay status mapping tests
# ═══════════════════════════════════════════════


class TestRazorpayStatusMapping:
    def test_active_maps_to_active(self):
        assert map_razorpay_status("active") == "active"

    def test_created_maps_to_incomplete(self):
        assert map_razorpay_status("created") == "incomplete"

    def test_authenticated_maps_to_trialing(self):
        assert map_razorpay_status("authenticated") == "trialing"

    def test_paused_maps_to_past_due(self):
        assert map_razorpay_status("paused") == "past_due"

    def test_cancelled_maps_to_canceled(self):
        assert map_razorpay_status("cancelled") == "canceled"

    def test_completed_maps_to_canceled(self):
        assert map_razorpay_status("completed") == "canceled"

    def test_halted_maps_to_past_due(self):
        assert map_razorpay_status("halted") == "past_due"

    def test_unknown_maps_to_incomplete(self):
        assert map_razorpay_status("unknown_state") == "incomplete"


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
        get_workspace_billing(workspace.id, db)

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
        for i in range(2):
            comp = Competitor(
                workspace_id=workspace.id,
                name=f"Comp {i}",
                domain=f"comp{i}.com",
            )
            db.add(comp)
        db.commit()

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
# 4. Billing API tests (Razorpay)
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
        # Verify razorpay fields are present
        assert "razorpay_customer_id" in data["billing"]
        assert "razorpay_subscription_id" in data["billing"]

    def test_billing_overview_not_found(self):
        fake_id = uuid.uuid4()
        resp = client.get(f"/api/workspaces/{fake_id}/billing")
        assert resp.status_code == 404

    def test_checkout_no_razorpay_key(self, workspace):
        with patch("app.api.billing.get_settings") as mock_settings:
            mock_settings.return_value.RAZORPAY_KEY_ID = ""
            resp = client.post(
                f"/api/workspaces/{workspace.id}/billing/checkout",
                json={"plan_type": "pro"},
            )
            # Should return 503 if Razorpay is not configured
            assert resp.status_code == 503

    def test_checkout_invalid_plan(self, workspace):
        with patch("app.api.billing.get_settings") as mock_settings:
            mock_settings.return_value.RAZORPAY_KEY_ID = "rzp_test_xxx"
            resp = client.post(
                f"/api/workspaces/{workspace.id}/billing/checkout",
                json={"plan_type": "nonexistent"},
            )
            assert resp.status_code == 400

    def test_checkout_creates_subscription(self, workspace):
        """Test full checkout flow with mocked Razorpay."""
        mock_subscription = {
            "subscription_id": "sub_razorpay_456",
            "short_url": "https://rzp.io/i/test",
            "status": "created",
        }
        with patch("app.api.billing.get_settings") as mock_settings, \
             patch("app.api.billing.create_razorpay_customer", return_value="cust_razorpay_123"), \
             patch("app.api.billing.create_razorpay_subscription", return_value=mock_subscription):
            mock_settings.return_value.RAZORPAY_KEY_ID = "rzp_test_xxx"
            resp = client.post(
                f"/api/workspaces/{workspace.id}/billing/checkout",
                json={"plan_type": "pro"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["subscription_id"] == "sub_razorpay_456"
            assert data["razorpay_key_id"] == "rzp_test_xxx"
            assert data["plan_type"] == "pro"

    def test_verify_payment_success(self, workspace, db):
        """Test payment verification with mocked signature check."""
        billing = get_workspace_billing(workspace.id, db)
        billing.razorpay_subscription_id = "sub_test_123"
        db.commit()

        with patch("app.api.billing.verify_payment_signature", return_value=True):
            resp = client.post(
                f"/api/workspaces/{workspace.id}/billing/verify",
                json={
                    "razorpay_subscription_id": "sub_test_123",
                    "razorpay_payment_id": "pay_test_456",
                    "razorpay_signature": "valid_sig",
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["verified"] is True
            assert data["subscription_status"] == "active"

    def test_verify_payment_invalid_signature(self, workspace, db):
        """Test payment verification fails with invalid signature."""
        billing = get_workspace_billing(workspace.id, db)
        billing.razorpay_subscription_id = "sub_test_123"
        db.commit()

        with patch("app.api.billing.verify_payment_signature", return_value=False):
            resp = client.post(
                f"/api/workspaces/{workspace.id}/billing/verify",
                json={
                    "razorpay_subscription_id": "sub_test_123",
                    "razorpay_payment_id": "pay_test_456",
                    "razorpay_signature": "bad_sig",
                },
            )
            assert resp.status_code == 400

    def test_cancel_subscription(self, workspace, db):
        """Test subscription cancellation."""
        billing = get_workspace_billing(workspace.id, db)
        billing.razorpay_subscription_id = "sub_test_789"
        billing.subscription_status = "active"
        db.commit()

        with patch("app.api.billing.cancel_razorpay_subscription") as mock_cancel:
            resp = client.post(
                f"/api/workspaces/{workspace.id}/billing/cancel",
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "cancel_scheduled"
            assert data["cancel_at_period_end"] is True
            mock_cancel.assert_called_once_with("sub_test_789", cancel_at_cycle_end=True)

    def test_cancel_no_subscription(self, workspace):
        """Test cancel fails when no subscription exists."""
        resp = client.post(
            f"/api/workspaces/{workspace.id}/billing/cancel",
        )
        assert resp.status_code == 400

    def test_sync_subscription(self, workspace, db):
        """Test subscription sync from Razorpay."""
        billing = get_workspace_billing(workspace.id, db)
        billing.razorpay_subscription_id = "sub_sync_test"
        db.commit()

        mock_sub = {
            "id": "sub_sync_test",
            "status": "active",
            "current_end": int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp()),
        }
        with patch("app.api.billing.fetch_razorpay_subscription", return_value=mock_sub):
            resp = client.post(
                f"/api/workspaces/{workspace.id}/billing/sync",
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "active"
            assert data["razorpay_status"] == "active"


# ═══════════════════════════════════════════════
# 5. Webhook idempotency tests (Razorpay)
# ═══════════════════════════════════════════════


class TestWebhookIdempotency:
    def test_duplicate_event_not_reprocessed(self, db, workspace):
        event_id = "subscription.activated_sub_test_123"
        wh = WebhookEvent(
            razorpay_event_id=event_id,
            event_type="subscription.activated",
            payload={"event": "subscription.activated"},
            processed=True,
        )
        db.add(wh)
        db.commit()

        existing = (
            db.query(WebhookEvent)
            .filter(WebhookEvent.razorpay_event_id == event_id)
            .first()
        )
        assert existing is not None
        assert existing.processed is True


# ═══════════════════════════════════════════════
# 5b. Webhook processing tests (Razorpay)
# ═══════════════════════════════════════════════


class TestWebhookProcessing:
    def _make_webhook_payload(self, event_type: str, entity: dict, entity_key: str = "subscription") -> dict:
        return {
            "event": event_type,
            "payload": {
                entity_key: {
                    "entity": entity,
                },
            },
        }

    def _post_webhook(self, payload: dict, secret: str = "") -> object:
        body = json.dumps(payload).encode()
        if secret:
            sig = hmac.new(
                key=secret.encode(),
                msg=body,
                digestmod=hashlib.sha256,
            ).hexdigest()
        else:
            sig = ""
        return client.post(
            "/api/webhooks/razorpay",
            content=body,
            headers={
                "content-type": "application/json",
                "x-razorpay-signature": sig,
            },
        )

    def test_subscription_activated_updates_billing(self, workspace, db):
        billing = get_workspace_billing(workspace.id, db)
        billing.razorpay_subscription_id = "sub_wh_test"
        billing.subscription_status = "incomplete"
        db.commit()

        payload = self._make_webhook_payload(
            "subscription.activated",
            {"id": "sub_wh_test", "status": "active", "notes": {"workspace_id": str(workspace.id), "plan_type": "pro"}},
        )

        with patch("app.api.billing.verify_webhook_signature"):
            resp = self._post_webhook(payload)
            assert resp.status_code == 200

        db.refresh(billing)
        assert billing.subscription_status == "active"
        assert billing.plan_type == "pro"

    def test_subscription_cancelled_updates_billing(self, workspace, db):
        billing = get_workspace_billing(workspace.id, db)
        billing.razorpay_subscription_id = "sub_cancel_test"
        billing.subscription_status = "active"
        db.commit()

        payload = self._make_webhook_payload(
            "subscription.cancelled",
            {"id": "sub_cancel_test", "status": "cancelled"},
        )

        with patch("app.api.billing.verify_webhook_signature"):
            resp = self._post_webhook(payload)
            assert resp.status_code == 200

        db.refresh(billing)
        assert billing.subscription_status == "canceled"

    def test_subscription_paused_sets_grace_period(self, workspace, db):
        billing = get_workspace_billing(workspace.id, db)
        billing.razorpay_subscription_id = "sub_pause_test"
        billing.subscription_status = "active"
        db.commit()

        payload = self._make_webhook_payload(
            "subscription.paused",
            {"id": "sub_pause_test", "status": "paused"},
        )

        with patch("app.api.billing.verify_webhook_signature"):
            resp = self._post_webhook(payload)
            assert resp.status_code == 200

        db.refresh(billing)
        assert billing.subscription_status == "past_due"
        assert billing.grace_period_ends_at is not None

    def test_payment_captured_activates_billing(self, workspace, db):
        billing = get_workspace_billing(workspace.id, db)
        billing.razorpay_customer_id = "cust_pay_test"
        billing.subscription_status = "incomplete"
        db.commit()

        payload = self._make_webhook_payload(
            "payment.captured",
            {"id": "pay_123", "customer_id": "cust_pay_test", "notes": {}},
            entity_key="payment",
        )

        with patch("app.api.billing.verify_webhook_signature"):
            resp = self._post_webhook(payload)
            assert resp.status_code == 200

        db.refresh(billing)
        assert billing.subscription_status == "active"


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
        resp = client.post(
            "/api/workspaces",
            json={"name": "Regression WS", "slug": "regression-ws"},
        )
        assert resp.status_code == 201
        ws_id = resp.json()["id"]

        resp = client.get("/api/workspaces")
        assert resp.status_code == 200
        assert any(w["id"] == ws_id for w in resp.json())

    def test_competitor_crud_for_active_workspace(self, workspace):
        resp = client.post(
            f"/api/workspaces/{workspace.id}/competitors",
            json={"name": "Regression Comp", "domain": "regression.com"},
        )
        assert resp.status_code == 201
        comp_id = resp.json()["id"]

        resp = client.get(f"/api/workspaces/{workspace.id}/competitors")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

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

        resp = client.post(
            f"/api/competitors/{comp.id}/pages",
            json={"url": "https://rc.com/pricing", "page_type": "pricing"},
        )
        assert resp.status_code == 201

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
