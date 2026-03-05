"""
Billing API endpoints:
- GET  /api/workspaces/{id}/billing              — billing overview
- POST /api/workspaces/{id}/billing/checkout      — create Razorpay subscription for checkout
- POST /api/workspaces/{id}/billing/verify        — verify Razorpay payment signature
- POST /api/workspaces/{id}/billing/cancel        — cancel subscription
- GET  /api/billing/plans                          — list available plans
- POST /api/webhooks/razorpay                      — Razorpay webhook handler
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.billing import (
    GRACE_PERIOD_DAYS,
    PLAN_DEFINITIONS,
    SUPPORTED_CURRENCIES,
    create_razorpay_customer,
    create_razorpay_subscription,
    cancel_razorpay_subscription,
    fetch_razorpay_subscription,
    get_plan_info,
    get_plan_limits,
    get_plan_price,
    map_razorpay_status,
    verify_payment_signature,
    verify_webhook_signature,
)
from app.core.config import get_settings
from app.core.plan_enforcement import get_workspace_billing
from app.models.models import (
    Competitor,
    TrackedPage,
    WebhookEvent,
    Workspace,
    WorkspaceBilling,
)
from app.schemas.schemas import (
    BillingOverview,
    CheckoutSessionRequest,
    CheckoutSessionResponse,
    PaymentVerifyRequest,
    PaymentVerifyResponse,
    PlanInfo,
    WorkspaceBillingRead,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["billing"])


# ── Plan listing ──


@router.get("/api/billing/plans", response_model=list[PlanInfo])
def list_plans():
    """List all available plans with their limits and pricing."""
    return [get_plan_info(pt) for pt in PLAN_DEFINITIONS]


# ── Workspace billing ──


@router.get(
    "/api/workspaces/{workspace_id}/billing",
    response_model=BillingOverview,
)
def get_billing_overview(workspace_id: uuid.UUID, db: Session = Depends(get_db)):
    ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")

    billing = get_workspace_billing(workspace_id, db)
    plan = get_plan_info(billing.plan_type)

    # Compute current usage
    competitor_count = (
        db.query(Competitor)
        .filter(Competitor.workspace_id == workspace_id)
        .count()
    )
    page_count = (
        db.query(TrackedPage)
        .join(Competitor, TrackedPage.competitor_id == Competitor.id)
        .filter(Competitor.workspace_id == workspace_id)
        .count()
    )
    limits = get_plan_limits(billing.plan_type)

    usage = {
        "competitors": competitor_count,
        "competitors_limit": limits["max_competitors"],
        "tracked_pages": page_count,
        "tracked_pages_limit": limits["max_tracked_pages"],
    }

    return BillingOverview(
        billing=WorkspaceBillingRead.model_validate(billing),
        plan=plan,
        usage=usage,
    )


# ── Razorpay Checkout ──


@router.post(
    "/api/workspaces/{workspace_id}/billing/checkout",
    response_model=CheckoutSessionResponse,
)
def create_checkout(
    workspace_id: uuid.UUID,
    payload: CheckoutSessionRequest,
    db: Session = Depends(get_db),
):
    settings = get_settings()
    if not settings.RAZORPAY_KEY_ID:
        raise HTTPException(status_code=503, detail="Razorpay is not configured")

    ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")

    if payload.plan_type not in PLAN_DEFINITIONS:
        raise HTTPException(status_code=400, detail=f"Invalid plan: {payload.plan_type}")

    currency = payload.currency.upper()
    if currency not in SUPPORTED_CURRENCIES:
        raise HTTPException(status_code=400, detail=f"Unsupported currency: {currency}. Supported: {', '.join(SUPPORTED_CURRENCIES)}")

    plan_price = get_plan_price(payload.plan_type, currency)

    billing = get_workspace_billing(workspace_id, db)

    # Create Razorpay customer if not exists
    if not billing.razorpay_customer_id:
        cust_id = create_razorpay_customer(str(workspace_id), ws.name)
        billing.razorpay_customer_id = cust_id
        db.commit()
        db.refresh(billing)

    # Create Razorpay subscription
    result = create_razorpay_subscription(
        razorpay_customer_id=billing.razorpay_customer_id,
        plan_type=payload.plan_type,
        workspace_id=str(workspace_id),
        currency=currency,
    )

    # Store subscription ID, currency, and price immediately
    billing.razorpay_subscription_id = result["subscription_id"]
    billing.plan_type = payload.plan_type
    billing.currency = currency
    billing.plan_price = plan_price
    db.commit()

    return CheckoutSessionResponse(
        subscription_id=result["subscription_id"],
        razorpay_key_id=settings.RAZORPAY_KEY_ID,
        short_url=result.get("short_url"),
        workspace_id=str(workspace_id),
        plan_type=payload.plan_type,
        currency=currency,
        plan_price=plan_price,
    )


# ── Payment Verification (called after frontend checkout completes) ──


@router.post(
    "/api/workspaces/{workspace_id}/billing/verify",
    response_model=PaymentVerifyResponse,
)
def verify_payment(
    workspace_id: uuid.UUID,
    payload: PaymentVerifyRequest,
    db: Session = Depends(get_db),
):
    billing = get_workspace_billing(workspace_id, db)

    # Verify the payment signature
    verified = verify_payment_signature({
        "razorpay_subscription_id": payload.razorpay_subscription_id,
        "razorpay_payment_id": payload.razorpay_payment_id,
        "razorpay_signature": payload.razorpay_signature,
    })

    if not verified:
        raise HTTPException(status_code=400, detail="Payment signature verification failed")

    # Update billing status
    billing.razorpay_subscription_id = payload.razorpay_subscription_id
    billing.subscription_status = "active"
    billing.grace_period_ends_at = None
    db.commit()
    db.refresh(billing)

    return PaymentVerifyResponse(
        verified=True,
        subscription_status=billing.subscription_status,
    )


# ── Cancel Subscription ──


@router.post("/api/workspaces/{workspace_id}/billing/cancel", status_code=200)
def cancel_subscription(workspace_id: uuid.UUID, db: Session = Depends(get_db)):
    billing = get_workspace_billing(workspace_id, db)
    if not billing.razorpay_subscription_id:
        raise HTTPException(status_code=400, detail="No active subscription to cancel")

    try:
        cancel_razorpay_subscription(billing.razorpay_subscription_id, cancel_at_cycle_end=True)
    except Exception as e:
        logger.error("Razorpay cancel failed: %s", e)
        raise HTTPException(status_code=502, detail="Failed to cancel subscription with Razorpay")

    billing.cancel_at_period_end = True
    db.commit()

    return {"status": "cancel_scheduled", "cancel_at_period_end": True}


# ── Sync Subscription (manual refresh from Razorpay) ──


@router.post("/api/workspaces/{workspace_id}/billing/sync", status_code=200)
def sync_subscription(workspace_id: uuid.UUID, db: Session = Depends(get_db)):
    billing = get_workspace_billing(workspace_id, db)
    if not billing.razorpay_subscription_id:
        return {"status": "no_subscription"}

    try:
        sub = fetch_razorpay_subscription(billing.razorpay_subscription_id)
    except Exception as e:
        logger.error("Razorpay fetch failed: %s", e)
        raise HTTPException(status_code=502, detail="Failed to fetch subscription from Razorpay")

    billing.subscription_status = map_razorpay_status(sub.get("status", ""))
    if sub.get("current_end"):
        billing.current_period_end = datetime.fromtimestamp(sub["current_end"], tz=timezone.utc)
    if billing.subscription_status == "active":
        billing.grace_period_ends_at = None
    db.commit()
    db.refresh(billing)

    return {
        "status": billing.subscription_status,
        "razorpay_status": sub.get("status"),
        "current_period_end": billing.current_period_end.isoformat() if billing.current_period_end else None,
    }


# ── Razorpay Webhook ──


@router.post("/api/webhooks/razorpay", status_code=200)
async def razorpay_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    signature = request.headers.get("x-razorpay-signature", "")

    try:
        verify_webhook_signature(payload, signature)
    except ValueError as e:
        logger.warning("Razorpay webhook signature verification failed: %s", e)
        raise HTTPException(status_code=400, detail="Invalid signature")

    event = json.loads(payload)
    event_id = event.get("event", "") + "_" + event.get("payload", {}).get("payment", {}).get("entity", {}).get("id", event.get("payload", {}).get("subscription", {}).get("entity", {}).get("id", str(uuid.uuid4())))
    event_type = event.get("event", "")

    # Idempotency check
    existing = (
        db.query(WebhookEvent)
        .filter(WebhookEvent.razorpay_event_id == event_id)
        .first()
    )
    if existing and existing.processed:
        return {"status": "already_processed"}

    # Record the event
    if not existing:
        wh_event = WebhookEvent(
            razorpay_event_id=event_id,
            event_type=event_type,
            payload=event,
        )
        db.add(wh_event)
        db.flush()
    else:
        wh_event = existing

    try:
        _process_razorpay_event(event_type, event.get("payload", {}), db)
        wh_event.processed = True
        db.commit()
    except Exception as e:
        logger.error("Razorpay webhook processing error for %s: %s", event_id, e)
        wh_event.error_message = str(e)
        db.commit()
        raise HTTPException(status_code=500, detail="Webhook processing failed")

    return {"status": "processed"}


def _process_razorpay_event(event_type: str, payload: dict, db: Session) -> None:
    """Route Razorpay webhook events to handlers."""
    handlers = {
        "payment.captured": _handle_payment_captured,
        "subscription.activated": _handle_subscription_activated,
        "subscription.charged": _handle_subscription_charged,
        "subscription.cancelled": _handle_subscription_cancelled,
        "subscription.paused": _handle_subscription_paused,
        "subscription.halted": _handle_subscription_halted,
    }
    handler = handlers.get(event_type)
    if handler:
        handler(payload, db)
    else:
        logger.info("Unhandled Razorpay webhook event: %s", event_type)


def _find_billing_by_subscription(sub_id: str, db: Session) -> WorkspaceBilling | None:
    return (
        db.query(WorkspaceBilling)
        .filter(WorkspaceBilling.razorpay_subscription_id == sub_id)
        .first()
    )


def _find_billing_by_customer(customer_id: str, db: Session) -> WorkspaceBilling | None:
    return (
        db.query(WorkspaceBilling)
        .filter(WorkspaceBilling.razorpay_customer_id == customer_id)
        .first()
    )


def _extract_subscription_entity(payload: dict) -> dict:
    """Extract subscription entity from Razorpay webhook payload."""
    return payload.get("subscription", {}).get("entity", {})


def _extract_payment_entity(payload: dict) -> dict:
    """Extract payment entity from Razorpay webhook payload."""
    return payload.get("payment", {}).get("entity", {})


def _handle_payment_captured(payload: dict, db: Session) -> None:
    """Handle payment.captured — mark subscription active, clear grace period."""
    payment = _extract_payment_entity(payload)
    notes = payment.get("notes", {})
    workspace_id = notes.get("workspace_id")

    # Try to find by subscription ID in payment's invoice
    # Payment might not have subscription info directly — use notes or customer
    customer_id = payment.get("customer_id")

    billing = None
    if customer_id:
        billing = _find_billing_by_customer(customer_id, db)
    if not billing and workspace_id:
        billing = get_workspace_billing(uuid.UUID(workspace_id), db)

    if billing:
        billing.subscription_status = "active"
        billing.grace_period_ends_at = None
        db.flush()


def _handle_subscription_activated(payload: dict, db: Session) -> None:
    """Handle subscription.activated — subscription is now active."""
    sub = _extract_subscription_entity(payload)
    sub_id = sub.get("id")
    if not sub_id:
        return

    billing = _find_billing_by_subscription(sub_id, db)
    if not billing:
        # Try from notes
        notes = sub.get("notes", {})
        workspace_id = notes.get("workspace_id")
        if workspace_id:
            billing = get_workspace_billing(uuid.UUID(workspace_id), db)
            billing.razorpay_subscription_id = sub_id

    if billing:
        billing.subscription_status = "active"
        billing.grace_period_ends_at = None

        # Update plan from notes
        plan_type = sub.get("notes", {}).get("plan_type")
        if plan_type and plan_type in PLAN_DEFINITIONS:
            billing.plan_type = plan_type

        # Update period end
        current_end = sub.get("current_end")
        if current_end:
            billing.current_period_end = datetime.fromtimestamp(current_end, tz=timezone.utc)

        db.flush()


def _handle_subscription_charged(payload: dict, db: Session) -> None:
    """Handle subscription.charged — recurring payment succeeded."""
    sub = _extract_subscription_entity(payload)
    sub_id = sub.get("id")
    if not sub_id:
        return

    billing = _find_billing_by_subscription(sub_id, db)
    if billing:
        billing.subscription_status = "active"
        billing.grace_period_ends_at = None

        current_end = sub.get("current_end")
        if current_end:
            billing.current_period_end = datetime.fromtimestamp(current_end, tz=timezone.utc)

        db.flush()


def _handle_subscription_cancelled(payload: dict, db: Session) -> None:
    """Handle subscription.cancelled — mark as canceled."""
    sub = _extract_subscription_entity(payload)
    sub_id = sub.get("id")
    if not sub_id:
        return

    billing = _find_billing_by_subscription(sub_id, db)
    if billing:
        billing.subscription_status = "canceled"
        db.flush()


def _handle_subscription_paused(payload: dict, db: Session) -> None:
    """Handle subscription.paused — mark as past_due with grace period."""
    sub = _extract_subscription_entity(payload)
    sub_id = sub.get("id")
    if not sub_id:
        return

    billing = _find_billing_by_subscription(sub_id, db)
    if billing:
        billing.subscription_status = "past_due"
        if not billing.grace_period_ends_at:
            billing.grace_period_ends_at = datetime.now(timezone.utc) + timedelta(days=GRACE_PERIOD_DAYS)
        db.flush()


def _handle_subscription_halted(payload: dict, db: Session) -> None:
    """Handle subscription.halted — payment retries exhausted, set past_due."""
    sub = _extract_subscription_entity(payload)
    sub_id = sub.get("id")
    if not sub_id:
        return

    billing = _find_billing_by_subscription(sub_id, db)
    if billing:
        billing.subscription_status = "past_due"
        if not billing.grace_period_ends_at:
            billing.grace_period_ends_at = datetime.now(timezone.utc) + timedelta(days=GRACE_PERIOD_DAYS)
        db.flush()
