"""Base collector class for all signal collectors."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, List, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.models import Competitor, CompetitorEvent, SignalType

logger = logging.getLogger(__name__)


class CollectorResult:
    """Result from a single collector run for one competitor."""

    def __init__(self):
        self.events_found: int = 0
        self.events_created: int = 0
        self.events_skipped_dedup: int = 0
        self.errors: list[str] = []


class BaseCollector(ABC):
    """
    Base class for all signal collectors.

    Subclasses must implement:
        - signal_type: the SignalType enum value
        - collect_for_competitor(): fetch + detect events for a single competitor
    """

    signal_type: SignalType

    def __init__(self, db: Session):
        self.db = db

    @abstractmethod
    def collect_for_competitor(
        self, competitor: Competitor
    ) -> List[dict[str, Any]]:
        """
        Fetch source data and return a list of raw event dicts.

        Each dict must contain at minimum:
            - title: str
            - source_url: str (optional)
            - description: str (optional)
            - event_time: datetime (optional, defaults to now)
            - metadata_json: dict (optional)
            - severity: str (optional, defaults to "medium")
        """
        ...

    def collect_for_url(
        self, url: str, competitor: Competitor
    ) -> List[dict[str, Any]]:
        """
        Collect events from a specific URL (for manual signal sources).
        Default: delegates to collect_for_competitor (auto-discovery).
        Subclasses should override for URL-specific collection.
        """
        return self.collect_for_competitor(competitor)

    def run_for_competitor(self, competitor: Competitor) -> CollectorResult:
        """Run collection for a single competitor with dedup and error handling."""
        result = CollectorResult()

        try:
            raw_events = self.collect_for_competitor(competitor)
        except Exception as exc:
            logger.error(
                "%s collector failed for competitor %s (%s): %s",
                self.signal_type.value, competitor.name, competitor.domain, exc,
            )
            result.errors.append(str(exc))
            return result

        result.events_found = len(raw_events)

        for event_data in raw_events:
            created = self._upsert_event(competitor, event_data)
            if created:
                result.events_created += 1
            else:
                result.events_skipped_dedup += 1

        return result

    def run_for_workspace(self, workspace_id: str) -> dict[str, Any]:
        """Run collection for all active competitors in a workspace."""
        competitors = (
            self.db.query(Competitor)
            .filter(
                Competitor.workspace_id == workspace_id,
                Competitor.is_active == True,  # noqa: E712
            )
            .all()
        )

        total_result = {
            "signal_type": self.signal_type.value,
            "competitors_processed": 0,
            "events_found": 0,
            "events_created": 0,
            "events_skipped_dedup": 0,
            "errors": [],
        }

        for comp in competitors:
            r = self.run_for_competitor(comp)
            total_result["competitors_processed"] += 1
            total_result["events_found"] += r.events_found
            total_result["events_created"] += r.events_created
            total_result["events_skipped_dedup"] += r.events_skipped_dedup
            total_result["errors"].extend(r.errors)

        return total_result

    def _upsert_event(
        self, competitor: Competitor, event_data: dict[str, Any]
    ) -> bool:
        """
        Insert a CompetitorEvent, skipping if duplicate (idempotent).
        Returns True if a new row was created, False if deduped.
        """
        event = CompetitorEvent(
            workspace_id=competitor.workspace_id,
            competitor_id=competitor.id,
            signal_type=self.signal_type.value,
            title=event_data["title"][:512],
            description=event_data.get("description"),
            source_url=event_data.get("source_url"),
            event_time=event_data.get("event_time", datetime.now(timezone.utc)),
            metadata_json=event_data.get("metadata_json", {}),
            severity=event_data.get("severity", "medium"),
        )

        try:
            self.db.add(event)
            self.db.flush()
            self.db.commit()

            # Generate AI analysis for the new event
            try:
                from app.services.signal_analyzer import generate_signal_analysis
                generate_signal_analysis(event, self.db, competitor_name=competitor.name)
            except Exception as exc:
                logger.warning("AI analysis failed for event %s (non-fatal): %s", event.id, exc)

            return True
        except IntegrityError:
            self.db.rollback()
            logger.debug(
                "Dedup: skipping existing %s event for %s: %s",
                self.signal_type.value, competitor.domain, event_data["title"][:80],
            )
            return False
