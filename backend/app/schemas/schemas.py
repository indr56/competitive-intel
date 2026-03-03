from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.models import PageType, Severity


# ── Mixins ──


class TimestampMixin(BaseModel):
    created_at: datetime


class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ── Account ──


class AccountCreate(BaseModel):
    name: str
    slug: str
    plan: str = "free"


class AccountRead(ORMBase, TimestampMixin):
    id: uuid.UUID
    name: str
    slug: str
    plan: str


# ── User ──


class UserCreate(BaseModel):
    email: str
    role: str = "member"


class UserRead(ORMBase, TimestampMixin):
    id: uuid.UUID
    account_id: uuid.UUID
    email: str
    role: str


# ── Workspace ──


class WorkspaceCreate(BaseModel):
    name: str
    slug: str


class WorkspaceRead(ORMBase, TimestampMixin):
    id: uuid.UUID
    account_id: uuid.UUID
    name: str
    slug: str


# ── Competitor ──


class CompetitorCreate(BaseModel):
    name: str
    domain: str
    logo_url: str | None = None


class CompetitorUpdate(BaseModel):
    name: str | None = None
    domain: str | None = None
    logo_url: str | None = None
    is_active: bool | None = None


class CompetitorRead(ORMBase, TimestampMixin):
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    domain: str
    logo_url: str | None
    is_active: bool


# ── Tracked Page ──


class TrackedPageCreate(BaseModel):
    url: str
    page_type: PageType
    check_interval_hours: int = 24


class TrackedPageUpdate(BaseModel):
    url: str | None = None
    page_type: PageType | None = None
    check_interval_hours: int | None = None
    is_active: bool | None = None


class TrackedPageRead(ORMBase, TimestampMixin):
    id: uuid.UUID
    competitor_id: uuid.UUID
    url: str
    page_type: PageType
    check_interval_hours: int
    is_active: bool
    last_checked_at: datetime | None


# ── Snapshot ──


class SnapshotRead(ORMBase):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    tracked_page_id: uuid.UUID
    screenshot_url: str | None
    html_archive_url: str | None
    extracted_text: str
    text_hash: str
    metadata_: dict[str, Any] | None = Field(default=None, alias="metadata_")
    captured_at: datetime


# ── Diff ──


class DiffRead(ORMBase):
    id: uuid.UUID
    tracked_page_id: uuid.UUID
    snapshot_before_id: uuid.UUID
    snapshot_after_id: uuid.UUID
    raw_diff: dict[str, Any]
    is_meaningful: bool | None
    noise_filtered: dict[str, Any] | None
    created_at: datetime


# ── Change Event ──


class ChangeEventRead(ORMBase):
    id: uuid.UUID
    diff_id: uuid.UUID
    workspace_id: uuid.UUID
    competitor_id: uuid.UUID
    categories: list[str]
    severity: Severity | None
    ai_summary: str | None
    ai_why_it_matters: str | None
    ai_next_moves: str | None
    ai_battlecard_block: str | None
    ai_sales_talk_track: str | None
    created_at: datetime


# ── Digest ──


class DigestRead(ORMBase):
    id: uuid.UUID
    workspace_id: uuid.UUID
    period_start: datetime
    period_end: datetime
    change_event_ids: list[uuid.UUID]
    email_sent_at: datetime | None
    web_view_token: str | None
    created_at: datetime


# ── Misc ──


class CaptureNowRequest(BaseModel):
    pass


class PaginatedResponse(BaseModel):
    items: list[Any]
    total: int
    page: int
    page_size: int
