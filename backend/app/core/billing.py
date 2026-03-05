"""
Plan definitions and Stripe integration service.

Competitor pricing analysis summary (informing our model):
─────────────────────────────────────────────────────────
• Visualping: Usage-based (page checks/month). Free→Starter→Business.
• Peec AI: 3 tiers (Starter/Pro/Advanced) + Enterprise. Limits on prompts, projects, models.
  Annual discount. Daily tracking across tiers.
• Parano AI: Simple per-competitor/month. No tiers. "No hidden fees."
• AIclicks: 3 tiers ($59/$189/$499) + Agency custom. 3-day trial. Annual = 2 months free.
  Limits: tracked prompts, AI answers analyzed, blogs generated.
• Amadora AI: 3 tiers (Starter $49 / Professional $87 / Agency $399).
  Agency = multi-workspace + branding. 20% annual discount. "Start for free."
• Lucid Engine: Single plan + add-ons. 1 brand, 60 prompts, weekly scans.
  Agency = "building something" (coming soon).

Patterns adopted for our product:
─────────────────────────────────
1. 3-tier model (Starter/Pro/Agency) — dominant pattern across competitors
2. Limits on: competitors, tracked pages, check frequency — matches Visualping/Peec
3. Agency tier = multiple workspaces + white-label — matches Amadora
4. 14-day free trial on all plans — balances AIclicks 3-day and Amadora free start
5. Annual discount (20%) — matches Amadora, Peec patterns
6. Configurable limits (not hardcoded) — stored in PLAN_DEFINITIONS dict
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import stripe

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# ── Plan Definitions (configurable, not hardcoded) ──

PLAN_DEFINITIONS: dict[str, dict[str, Any]] = {
    "starter": {
        "name": "Starter",
        "price_monthly_cents": 4900,  # $49/mo
        "limits": {
            "max_competitors": 3,
            "max_tracked_pages": 15,
            "min_check_interval_hours": 24,
            "white_label": False,
            "max_workspaces": 1,
        },
    },
    "pro": {
        "name": "Pro",
        "price_monthly_cents": 14900,  # $149/mo
        "limits": {
            "max_competitors": 10,
            "max_tracked_pages": 50,
            "min_check_interval_hours": 6,
            "white_label": False,
            "max_workspaces": 3,
        },
    },
    "agency": {
        "name": "Agency",
        "price_monthly_cents": 39900,  # $399/mo
        "limits": {
            "max_competitors": 50,
            "max_tracked_pages": 200,
            "min_check_interval_hours": 1,
            "white_label": True,
            "max_workspaces": 20,
        },
    },
}

TRIAL_DAYS = 14
GRACE_PERIOD_DAYS = 7

# Subscription statuses that allow full access
ACTIVE_STATUSES = {"trialing", "active"}
# Statuses that allow read-only (grace period)
GRACE_STATUSES = {"past_due"}


def get_plan_limits(plan_type: str) -> dict[str, Any]:
    """Get limits for a plan type. Falls back to starter."""
    plan = PLAN_DEFINITIONS.get(plan_type, PLAN_DEFINITIONS["starter"])
    return plan["limits"]


def get_plan_info(plan_type: str) -> dict[str, Any]:
    """Get full plan info dict."""
    plan = PLAN_DEFINITIONS.get(plan_type, PLAN_DEFINITIONS["starter"])
    return {
        "plan_type": plan_type,
        "name": plan["name"],
        "price_monthly_cents": plan["price_monthly_cents"],
        "limits": plan["limits"],
    }


def is_billing_active(status: str, grace_period_ends_at: datetime | None = None) -> bool:
    """Check if workspace has active billing (can create resources, run captures)."""
    if status in ACTIVE_STATUSES:
        return True
    if status in GRACE_STATUSES and grace_period_ends_at:
        return datetime.now(timezone.utc) < grace_period_ends_at
    return False


def get_stripe_price_id(plan_type: str) -> str:
    """Map plan type to Stripe Price ID."""
    settings = get_settings()
    mapping = {
        "starter": settings.STRIPE_STARTER_PRICE_ID,
        "pro": settings.STRIPE_PRO_PRICE_ID,
        "agency": settings.STRIPE_AGENCY_PRICE_ID,
    }
    price_id = mapping.get(plan_type)
    if not price_id:
        raise ValueError(f"No Stripe price ID configured for plan: {plan_type}")
    return price_id


# ── Stripe Service ──


def _init_stripe() -> None:
    settings = get_settings()
    if settings.STRIPE_SECRET_KEY:
        stripe.api_key = settings.STRIPE_SECRET_KEY


def create_stripe_customer(workspace_id: str, workspace_name: str, email: str | None = None) -> str:
    """Create a Stripe customer for a workspace. Returns stripe_customer_id."""
    _init_stripe()
    customer = stripe.Customer.create(
        name=workspace_name,
        email=email,
        metadata={"workspace_id": workspace_id},
    )
    return customer.id


def create_checkout_session(
    stripe_customer_id: str,
    plan_type: str,
    workspace_id: str,
    success_url: str,
    cancel_url: str,
) -> dict[str, str]:
    """Create a Stripe Checkout Session. Returns {checkout_url, session_id}."""
    _init_stripe()
    price_id = get_stripe_price_id(plan_type)

    session = stripe.checkout.Session.create(
        customer=stripe_customer_id,
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=success_url,
        cancel_url=cancel_url,
        subscription_data={
            "trial_period_days": TRIAL_DAYS,
            "metadata": {"workspace_id": workspace_id, "plan_type": plan_type},
        },
        metadata={"workspace_id": workspace_id, "plan_type": plan_type},
    )
    return {"checkout_url": session.url, "session_id": session.id}


def create_portal_session(stripe_customer_id: str, return_url: str) -> str:
    """Create a Stripe Customer Portal session. Returns portal URL."""
    _init_stripe()
    session = stripe.billing_portal.Session.create(
        customer=stripe_customer_id,
        return_url=return_url,
    )
    return session.url


def verify_webhook_signature(payload: bytes, sig_header: str) -> dict:
    """Verify Stripe webhook signature. Returns parsed event."""
    settings = get_settings()
    event = stripe.Webhook.construct_event(
        payload, sig_header, settings.STRIPE_WEBHOOK_SECRET,
    )
    return event
