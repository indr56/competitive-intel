"""
Plan definitions and Razorpay integration service.

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

import hashlib
import hmac
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import razorpay

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# ── Plan Definitions (configurable, not hardcoded) ──

PLAN_DEFINITIONS: dict[str, dict[str, Any]] = {
    "starter": {
        "name": "Starter",
        "price_monthly_cents": 4900,  # $49/mo
        "pricing": {
            "USD": 4900,   # $49/mo in cents
            "INR": 199900, # ₹1999/mo in paise
        },
        "limits": {
            "max_competitors": 3,
            "max_tracked_pages": 15,
            "min_check_interval_hours": 24,
            "white_label": False,
            "max_workspaces": 1,
            "max_tracked_prompts": 10,
        },
    },
    "pro": {
        "name": "Pro",
        "price_monthly_cents": 14900,  # $149/mo
        "pricing": {
            "USD": 14900,   # $149/mo in cents
            "INR": 599900,  # ₹5999/mo in paise
        },
        "limits": {
            "max_competitors": 10,
            "max_tracked_pages": 50,
            "min_check_interval_hours": 6,
            "white_label": False,
            "max_workspaces": 3,
            "max_tracked_prompts": 25,
        },
    },
    "agency": {
        "name": "Agency",
        "price_monthly_cents": 39900,  # $399/mo
        "pricing": {
            "USD": 39900,    # $399/mo in cents
            "INR": 1499900,  # ₹14999/mo in paise
        },
        "limits": {
            "max_competitors": 50,
            "max_tracked_pages": 200,
            "min_check_interval_hours": 1,
            "white_label": True,
            "max_workspaces": 20,
            "max_tracked_prompts": 100,
        },
    },
}

SUPPORTED_CURRENCIES = {"USD", "INR"}
SUPPORTED_INTERVALS = {"month", "year"}

TRIAL_DAYS = 14
GRACE_PERIOD_DAYS = 7

# Subscription statuses that allow full access
ACTIVE_STATUSES = {"trialing", "active"}
# Statuses that allow read-only (grace period)
GRACE_STATUSES = {"past_due"}

# Razorpay subscription states → our internal status mapping
RAZORPAY_STATUS_MAP: dict[str, str] = {
    "created": "incomplete",
    "authenticated": "trialing",
    "active": "active",
    "paused": "past_due",
    "cancelled": "canceled",
    "completed": "canceled",
    "halted": "past_due",
    "pending": "incomplete",
}


def get_plan_limits(plan_type: str) -> dict[str, Any]:
    """Get limits for a plan type. Falls back to starter."""
    plan = PLAN_DEFINITIONS.get(plan_type, PLAN_DEFINITIONS["starter"])
    return plan["limits"]


def _get_annual_discount() -> float:
    """Get annual discount from settings, default 0.25."""
    try:
        settings = get_settings()
        return settings.ANNUAL_DISCOUNT_PCT
    except Exception:
        return 0.25


def _compute_annual_price(monthly_price: int) -> int:
    """Compute annual price from monthly with discount."""
    discount = _get_annual_discount()
    return round(monthly_price * 12 * (1 - discount))


def get_plan_info(plan_type: str) -> dict[str, Any]:
    """Get full plan info dict with monthly + annual pricing for all currencies."""
    plan = PLAN_DEFINITIONS.get(plan_type, PLAN_DEFINITIONS["starter"])
    monthly_pricing = plan.get("pricing", {"USD": plan["price_monthly_cents"]})
    pricing = {}
    for currency, monthly_amount in monthly_pricing.items():
        pricing[currency] = {
            "month": monthly_amount,
            "year": _compute_annual_price(monthly_amount),
        }
    return {
        "plan_type": plan_type,
        "name": plan["name"],
        "price_monthly_cents": plan["price_monthly_cents"],
        "pricing": pricing,
        "annual_discount_pct": _get_annual_discount(),
        "limits": plan["limits"],
    }


def get_plan_price(plan_type: str, currency: str, interval: str = "month") -> int:
    """Get plan price in smallest currency unit for the given currency and interval."""
    plan = PLAN_DEFINITIONS.get(plan_type, PLAN_DEFINITIONS["starter"])
    pricing = plan.get("pricing", {})
    monthly_price = pricing.get(currency.upper())
    if monthly_price is None:
        raise ValueError(f"No {currency} pricing for plan: {plan_type}")
    if interval == "year":
        return _compute_annual_price(monthly_price)
    return monthly_price


def is_billing_active(status: str, grace_period_ends_at: datetime | None = None) -> bool:
    """Check if workspace has active billing (can create resources, run captures)."""
    if status in ACTIVE_STATUSES:
        return True
    if status in GRACE_STATUSES and grace_period_ends_at:
        return datetime.now(timezone.utc) < grace_period_ends_at
    return False


def get_razorpay_plan_id(plan_type: str) -> str:
    """Map plan type to Razorpay Plan ID."""
    settings = get_settings()
    mapping = {
        "starter": settings.RAZORPAY_STARTER_PLAN_ID,
        "pro": settings.RAZORPAY_PRO_PLAN_ID,
        "agency": settings.RAZORPAY_AGENCY_PLAN_ID,
    }
    plan_id = mapping.get(plan_type)
    if not plan_id:
        raise ValueError(f"No Razorpay plan ID configured for plan: {plan_type}")
    return plan_id


def map_razorpay_status(razorpay_status: str) -> str:
    """Map Razorpay subscription status to our internal status."""
    return RAZORPAY_STATUS_MAP.get(razorpay_status, "incomplete")


# ── Razorpay Service ──


def _get_razorpay_client() -> razorpay.Client:
    settings = get_settings()
    client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
    return client


def create_razorpay_customer(
    workspace_id: str, workspace_name: str, email: str | None = None
) -> str:
    """Create a Razorpay customer for a workspace. Returns razorpay_customer_id."""
    client = _get_razorpay_client()
    data: dict[str, Any] = {
        "name": workspace_name,
        "notes": {"workspace_id": workspace_id},
    }
    if email:
        data["email"] = email
    customer = client.customer.create(data)
    return customer["id"]


def create_razorpay_subscription(
    razorpay_customer_id: str,
    plan_type: str,
    workspace_id: str,
    currency: str = "USD",
    interval: str = "month",
) -> dict[str, Any]:
    """
    Create a Razorpay Subscription.
    Returns {subscription_id, short_url} — short_url is a payment link fallback.
    The frontend uses the subscription_id to open Razorpay Checkout.
    """
    client = _get_razorpay_client()
    razorpay_plan_id = get_razorpay_plan_id(plan_type)

    total_count = 10 if interval == "year" else 120  # 10 years

    subscription_data: dict[str, Any] = {
        "plan_id": razorpay_plan_id,
        "customer_id": razorpay_customer_id,
        "total_count": total_count,
        "notes": {
            "workspace_id": workspace_id,
            "plan_type": plan_type,
            "currency": currency,
            "interval": interval,
        },
    }

    subscription = client.subscription.create(subscription_data)

    return {
        "subscription_id": subscription["id"],
        "short_url": subscription.get("short_url", ""),
        "status": subscription.get("status", "created"),
    }


def fetch_razorpay_subscription(subscription_id: str) -> dict[str, Any]:
    """Fetch current subscription state from Razorpay."""
    client = _get_razorpay_client()
    return client.subscription.fetch(subscription_id)


def cancel_razorpay_subscription(subscription_id: str, cancel_at_cycle_end: bool = True) -> dict[str, Any]:
    """Cancel a Razorpay subscription."""
    client = _get_razorpay_client()
    return client.subscription.cancel(subscription_id, {"cancel_at_cycle_end": cancel_at_cycle_end})


def verify_webhook_signature(payload: bytes, signature: str) -> bool:
    """
    Verify Razorpay webhook signature.
    Returns True if valid, raises ValueError if invalid.
    """
    settings = get_settings()
    secret = settings.RAZORPAY_WEBHOOK_SECRET
    if not secret:
        logger.warning("RAZORPAY_WEBHOOK_SECRET not set — skipping signature verification")
        return True

    expected_signature = hmac.new(
        key=secret.encode("utf-8"),
        msg=payload,
        digestmod=hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected_signature, signature):
        raise ValueError("Invalid Razorpay webhook signature")
    return True


def verify_payment_signature(payment_data: dict[str, str]) -> bool:
    """
    Verify Razorpay payment signature after checkout completion.
    payment_data must contain: razorpay_subscription_id, razorpay_payment_id, razorpay_signature
    """
    client = _get_razorpay_client()
    try:
        client.utility.verify_payment_signature(payment_data)
        return True
    except razorpay.errors.SignatureVerificationError:
        return False
