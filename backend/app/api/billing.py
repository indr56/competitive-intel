"""
Billing API endpoints:
- GET  /api/workspaces/{id}/billing          — billing overview
- POST /api/workspaces/{id}/billing/checkout  — create Stripe checkout session
- POST /api/workspaces/{id}/billing/portal    — create Stripe customer portal session
- GET  /api/billing/plans                     — list available plans
- POST /api/webhooks/stripe                   — Stripe webhook handler
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.billing import (
    GRACE_PERIOD_DAYS,
    PLAN_DEFINITIONS,
    create_checkout_session,
    create_portal_session,
    create_stripe_customer,
    get_plan_info,
    get_plan_limits,
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
    PlanInfo,
    PortalSessionResponse,
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


# ── Checkout ──


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
    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Stripe is not configured")

    ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")

    if payload.plan_type not in PLAN_DEFINITIONS:
        raise HTTPException(status_code=400, detail=f"Invalid plan: {payload.plan_type}")

    billing = get_workspace_billing(workspace_id, db)

    # Create Stripe customer if not exists
    if not billing.stripe_customer_id:
        cust_id = create_stripe_customer(str(workspace_id), ws.name)
        billing.stripe_customer_id = cust_id
        db.commit()
        db.refresh(billing)

    success_url = payload.success_url or f"{settings.FRONTEND_URL}/dashboard/billing?success=true"
    cancel_url = payload.cancel_url or f"{settings.FRONTEND_URL}/dashboard/billing?canceled=true"

    result = create_checkout_session(
        stripe_customer_id=billing.stripe_customer_id,
        plan_type=payload.plan_type,
        workspace_id=str(workspace_id),
        success_url=success_url,
        cancel_url=cancel_url,
    )
    return CheckoutSessionResponse(**result)


# ── Customer Portal ──


@router.post(
    "/api/workspaces/{workspace_id}/billing/portal",
    response_model=PortalSessionResponse,
)
def create_portal(workspace_id: uuid.UUID, db: Session = Depends(get_db)):
    settings = get_settings()
    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Stripe is not configured")

    billing = get_workspace_billing(workspace_id, db)
    if not billing.stripe_customer_id:
        raise HTTPException(status_code=400, detail="No Stripe customer. Subscribe to a plan first.")

    return_url = f"{settings.FRONTEND_URL}/dashboard/billing"
    url = create_portal_session(billing.stripe_customer_id, return_url)
    return PortalSessionResponse(portal_url=url)


# ── Stripe Webhook ──


@router.post("/api/webhooks/stripe", status_code=200)
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    settings = get_settings()
    if not settings.STRIPE_WEBHOOK_SECRET:
        raise HTTPException(status_code=503, detail="Webhook secret not configured")

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = verify_webhook_signature(payload, sig_header)
    except Exception as e:
        logger.warning("Webhook signature verification failed: %s", e)
        raise HTTPException(status_code=400, detail="Invalid signature")

    event_id = event["id"]
    event_type = event["type"]

    # Idempotency check
    existing = (
        db.query(WebhookEvent)
        .filter(WebhookEvent.stripe_event_id == event_id)
        .first()
    )
    if existing and existing.processed:
        return {"status": "already_processed"}

    # Record the event
    if not existing:
        wh_event = WebhookEvent(
            stripe_event_id=event_id,
            event_type=event_type,
            payload=event,
        )
        db.add(wh_event)
        db.flush()
    else:
        wh_event = existing

    try:
        _process_webhook_event(event_type, event["data"]["object"], db)
        wh_event.processed = True
        db.commit()
    except Exception as e:
        logger.error("Webhook processing error for %s: %s", event_id, e)
        wh_event.error_message = str(e)
        db.commit()
        raise HTTPException(status_code=500, detail="Webhook processing failed")

    return {"status": "processed"}


def _process_webhook_event(event_type: str, obj: dict, db: Session) -> None:
    """Route webhook events to handlers."""
    handlers = {
        "checkout.session.completed": _handle_checkout_completed,
        "invoice.payment_succeeded": _handle_payment_succeeded,
        "invoice.payment_failed": _handle_payment_failed,
        "customer.subscription.updated": _handle_subscription_updated,
        "customer.subscription.deleted": _handle_subscription_deleted,
    }
    handler = handlers.get(event_type)
    if handler:
        handler(obj, db)
    else:
        logger.info("Unhandled webhook event type: %s", event_type)


def _find_billing_by_customer(customer_id: str, db: Session) -> WorkspaceBilling | None:
    return (
        db.query(WorkspaceBilling)
        .filter(WorkspaceBilling.stripe_customer_id == customer_id)
        .first()
    )


def _find_billing_by_subscription(sub_id: str, db: Session) -> WorkspaceBilling | None:
    return (
        db.query(WorkspaceBilling)
        .filter(WorkspaceBilling.stripe_subscription_id == sub_id)
        .first()
    )


def _handle_checkout_completed(obj: dict, db: Session) -> None:
    """Handle checkout.session.completed — link subscription to workspace."""
    customer_id = obj.get("customer")
    subscription_id = obj.get("subscription")
    metadata = obj.get("metadata", {})
    workspace_id = metadata.get("workspace_id")
    plan_type = metadata.get("plan_type", "starter")

    if not customer_id:
        return

    billing = _find_billing_by_customer(customer_id, db)
    if not billing and workspace_id:
        billing = get_workspace_billing(uuid.UUID(workspace_id), db)
        billing.stripe_customer_id = customer_id

    if billing:
        billing.stripe_subscription_id = subscription_id
        billing.plan_type = plan_type
        billing.subscription_status = "active"
        db.flush()


def _handle_payment_succeeded(obj: dict, db: Session) -> None:
    """Handle invoice.payment_succeeded — mark subscription active."""
    sub_id = obj.get("subscription")
    if not sub_id:
        return
    billing = _find_billing_by_subscription(sub_id, db)
    if billing:
        billing.subscription_status = "active"
        billing.grace_period_ends_at = None
        # Update period end
        period_end = obj.get("lines", {}).get("data", [{}])[0].get("period", {}).get("end")
        if period_end:
            billing.current_period_end = datetime.fromtimestamp(period_end, tz=timezone.utc)
        db.flush()


def _handle_payment_failed(obj: dict, db: Session) -> None:
    """Handle invoice.payment_failed — set past_due + grace period."""
    sub_id = obj.get("subscription")
    if not sub_id:
        return
    billing = _find_billing_by_subscription(sub_id, db)
    if billing:
        billing.subscription_status = "past_due"
        if not billing.grace_period_ends_at:
            billing.grace_period_ends_at = datetime.now(timezone.utc) + timedelta(days=GRACE_PERIOD_DAYS)
        db.flush()


def _handle_subscription_updated(obj: dict, db: Session) -> None:
    """Handle customer.subscription.updated — sync status, plan, period."""
    sub_id = obj.get("id")
    if not sub_id:
        return
    billing = _find_billing_by_subscription(sub_id, db)
    if not billing:
        # Try by customer
        customer_id = obj.get("customer")
        if customer_id:
            billing = _find_billing_by_customer(customer_id, db)
    if not billing:
        return

    billing.stripe_subscription_id = sub_id
    billing.subscription_status = obj.get("status", billing.subscription_status)
    billing.cancel_at_period_end = obj.get("cancel_at_period_end", False)

    # Update plan from items
    items = obj.get("items", {}).get("data", [])
    if items:
        price_id = items[0].get("price", {}).get("id", "")
        settings = get_settings()
        price_to_plan = {
            settings.STRIPE_STARTER_PRICE_ID: "starter",
            settings.STRIPE_PRO_PRICE_ID: "pro",
            settings.STRIPE_AGENCY_PRICE_ID: "agency",
        }
        new_plan = price_to_plan.get(price_id)
        if new_plan:
            billing.plan_type = new_plan

    period_end = obj.get("current_period_end")
    if period_end:
        billing.current_period_end = datetime.fromtimestamp(period_end, tz=timezone.utc)

    # Clear grace period if back to active
    if billing.subscription_status == "active":
        billing.grace_period_ends_at = None

    db.flush()


def _handle_subscription_deleted(obj: dict, db: Session) -> None:
    """Handle customer.subscription.deleted — mark canceled."""
    sub_id = obj.get("id")
    if not sub_id:
        return
    billing = _find_billing_by_subscription(sub_id, db)
    if billing:
        billing.subscription_status = "canceled"
        db.flush()
