"""Integration signal collector — detects integrations added/removed on marketplace pages."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, List

import httpx

from app.models.models import Competitor, SignalType
from app.services.collectors.base import BaseCollector

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 15.0

# Common paths for integration / marketplace pages
INTEGRATION_PATHS = [
    "/integrations",
    "/apps",
    "/marketplace",
    "/partners",
    "/integrations/all",
    "/ecosystem",
    "/connections",
    "/plugins",
]

# Well-known integration names to look for
KNOWN_INTEGRATIONS = [
    "salesforce", "hubspot", "slack", "zapier", "openai", "google",
    "microsoft", "stripe", "shopify", "github", "jira", "asana",
    "notion", "airtable", "twilio", "sendgrid", "mailchimp", "intercom",
    "zendesk", "segment", "snowflake", "databricks", "aws", "azure",
    "gcp", "dropbox", "box", "figma", "linear", "monday",
    "trello", "confluence", "bitbucket", "gitlab", "pagerduty",
    "datadog", "new relic", "amplitude", "mixpanel", "braze",
    "marketo", "pardot", "outreach", "gong", "zoom", "teams",
    "webex", "calendly", "docusign", "workday", "bamboohr",
    "greenhouse", "lever", "okta", "auth0", "cloudflare",
]


def _strip_html(text: str) -> str:
    """Remove HTML tags and collapse whitespace."""
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


class IntegrationAddedCollector(BaseCollector):
    """Detects integrations listed on marketplace/integrations pages."""
    signal_type = SignalType.INTEGRATION_ADDED

    def collect_for_url(
        self, url: str, competitor: Competitor
    ) -> List[dict[str, Any]]:
        page_text = self._fetch_page(url)
        if not page_text:
            raise ValueError(f"Could not fetch {url}")
        return self._extract_integrations(page_text, url, competitor)

    def collect_for_competitor(
        self, competitor: Competitor
    ) -> List[dict[str, Any]]:
        domain = competitor.domain.rstrip("/")
        if not domain.startswith("http"):
            domain = f"https://{domain}"

        events: List[dict[str, Any]] = []

        for path in INTEGRATION_PATHS:
            url = f"{domain}{path}"
            try:
                page_text = self._fetch_page(url)
                if page_text:
                    signals = self._extract_integrations(page_text, url, competitor)
                    events.extend(signals)
                    if signals:
                        logger.info(
                            "IntegrationAddedCollector: found %d signals from %s%s",
                            len(signals), competitor.domain, path,
                        )
                        break
            except Exception:
                continue

        return events

    def _fetch_page(self, url: str) -> str | None:
        try:
            with httpx.Client(timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
                resp = client.get(url, headers={"User-Agent": "CompetitiveIntel/1.0"})
                if resp.status_code != 200:
                    return None
                return resp.text
        except Exception:
            return None

    def _extract_integrations(
        self, html: str, source_url: str, competitor: Competitor
    ) -> List[dict[str, Any]]:
        """Detect known integrations mentioned on the page."""
        events: List[dict[str, Any]] = []
        now = datetime.now(timezone.utc)
        text_lower = _strip_html(html).lower()

        found_integrations = []
        for name in KNOWN_INTEGRATIONS:
            if name in text_lower:
                found_integrations.append(name)

        if not found_integrations:
            return events

        # Group them into a single event
        severity = "high" if len(found_integrations) >= 10 else "medium"
        events.append({
            "title": f"Integrations detected: {len(found_integrations)} partners listed",
            "description": (
                f"{competitor.name} integrations/marketplace page lists "
                f"{len(found_integrations)} known integrations: "
                f"{', '.join(found_integrations[:15])}. "
                f"Source: {source_url}"
            ),
            "source_url": source_url,
            "event_time": now,
            "severity": severity,
            "metadata_json": {
                "integrations_found": found_integrations,
                "count": len(found_integrations),
                "page_path": source_url,
            },
        })

        return events


class IntegrationRemovedCollector(BaseCollector):
    """
    Detects potential integration removals.
    Since we can't compare to a previous state in a single scan,
    this collector checks for deprecation/removal notices on integration pages.
    """
    signal_type = SignalType.INTEGRATION_REMOVED

    REMOVAL_KEYWORDS = [
        "deprecated", "discontinued", "no longer supported", "removed",
        "sunset", "end of life", "eol", "legacy integration",
        "will be removed", "migration required", "breaking change",
    ]

    def collect_for_url(
        self, url: str, competitor: Competitor
    ) -> List[dict[str, Any]]:
        page_text = self._fetch_page(url)
        if not page_text:
            raise ValueError(f"Could not fetch {url}")
        return self._extract_removals(page_text, url, competitor)

    def collect_for_competitor(
        self, competitor: Competitor
    ) -> List[dict[str, Any]]:
        domain = competitor.domain.rstrip("/")
        if not domain.startswith("http"):
            domain = f"https://{domain}"

        events: List[dict[str, Any]] = []

        for path in INTEGRATION_PATHS:
            url = f"{domain}{path}"
            try:
                page_text = self._fetch_page(url)
                if page_text:
                    signals = self._extract_removals(page_text, url, competitor)
                    events.extend(signals)
                    if signals:
                        break
            except Exception:
                continue

        return events

    def _fetch_page(self, url: str) -> str | None:
        try:
            with httpx.Client(timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
                resp = client.get(url, headers={"User-Agent": "CompetitiveIntel/1.0"})
                if resp.status_code != 200:
                    return None
                return resp.text
        except Exception:
            return None

    def _extract_removals(
        self, html: str, source_url: str, competitor: Competitor
    ) -> List[dict[str, Any]]:
        """Detect integration removal/deprecation notices."""
        events: List[dict[str, Any]] = []
        now = datetime.now(timezone.utc)
        text_lower = _strip_html(html).lower()

        matched_keywords = [kw for kw in self.REMOVAL_KEYWORDS if kw in text_lower]

        if not matched_keywords:
            return events

        events.append({
            "title": f"Integration deprecation signals detected ({len(matched_keywords)} indicators)",
            "description": (
                f"{competitor.name} integrations page contains deprecation/removal language: "
                f"{', '.join(matched_keywords)}. "
                f"This may indicate integrations being removed. Source: {source_url}"
            ),
            "source_url": source_url,
            "event_time": now,
            "severity": "high",
            "metadata_json": {
                "removal_keywords_found": matched_keywords,
                "page_path": source_url,
            },
        })

        return events
