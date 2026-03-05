"""
Plan enforcement dependencies for FastAPI.

Provides reusable Depends() callables that check billing state
and plan limits before allowing resource creation.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.billing import (
    ACTIVE_STATUSES,
    GRACE_PERIOD_DAYS,
    GRACE_STATUSES,
    get_plan_limits,
    is_billing_active,
)
from app.models.models import (
    Competitor,
    TrackedPage,
    Workspace,
    WorkspaceBilling,
)


def get_workspace_billing(workspace_id: uuid.UUID, db: Session) -> WorkspaceBilling:
    """Get or auto-create billing record for a workspace."""
    billing = (
        db.query(WorkspaceBilling)
        .filter(WorkspaceBilling.workspace_id == workspace_id)
        .first()
    )
    if not billing:
        billing = WorkspaceBilling(
            workspace_id=workspace_id,
            plan_type="starter",
            subscription_status="trialing",
            trial_ends_at=datetime.now(timezone.utc) + timedelta(days=14),
        )
        db.add(billing)
        db.commit()
        db.refresh(billing)
    return billing


def enforce_billing_active(workspace_id: uuid.UUID, db: Session) -> WorkspaceBilling:
    """Raise 402 if workspace billing is not active."""
    billing = get_workspace_billing(workspace_id, db)
    if not is_billing_active(billing.subscription_status, billing.grace_period_ends_at):
        raise HTTPException(
            status_code=402,
            detail=f"Workspace billing is {billing.subscription_status}. Please update your payment method.",
        )
    return billing


def enforce_competitor_limit(workspace_id: uuid.UUID, db: Session) -> None:
    """Raise 403 if workspace has reached competitor limit for its plan."""
    billing = enforce_billing_active(workspace_id, db)
    limits = get_plan_limits(billing.plan_type)
    current_count = (
        db.query(Competitor)
        .filter(Competitor.workspace_id == workspace_id)
        .count()
    )
    if current_count >= limits["max_competitors"]:
        raise HTTPException(
            status_code=403,
            detail=f"Competitor limit reached ({limits['max_competitors']}). "
            f"Upgrade your plan to add more.",
        )


def enforce_tracked_page_limit(workspace_id: uuid.UUID, db: Session) -> None:
    """Raise 403 if workspace has reached tracked page limit for its plan."""
    billing = enforce_billing_active(workspace_id, db)
    limits = get_plan_limits(billing.plan_type)
    # Count all tracked pages across all competitors in this workspace
    current_count = (
        db.query(TrackedPage)
        .join(Competitor, TrackedPage.competitor_id == Competitor.id)
        .filter(Competitor.workspace_id == workspace_id)
        .count()
    )
    if current_count >= limits["max_tracked_pages"]:
        raise HTTPException(
            status_code=403,
            detail=f"Tracked page limit reached ({limits['max_tracked_pages']}). "
            f"Upgrade your plan to add more.",
        )


def can_capture(workspace_id: uuid.UUID, db: Session) -> bool:
    """Check if capture jobs are allowed for this workspace."""
    billing = get_workspace_billing(workspace_id, db)
    return is_billing_active(billing.subscription_status, billing.grace_period_ends_at)
