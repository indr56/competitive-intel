"""Landing page collector — detects new strategic landing pages on competitor sites."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, List
from urllib.parse import urljoin, urlparse

import httpx

from app.models.models import Competitor, SignalType
from app.services.collectors.base import BaseCollector

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 15.0

# Strategic landing page path patterns to probe
STRATEGIC_PATHS = [
    "/ai",
    "/automation",
    "/enterprise",
    "/use-cases",
    "/solutions",
    "/platform",
    "/security",
    "/compliance",
    "/analytics",
    "/workflow",
    "/pricing",
    "/demo",
    "/for-enterprise",
    "/for-startups",
    "/for-teams",
    "/product",
    "/features",
]

# Paths to IGNORE (non-marketing)
IGNORE_PREFIXES = [
    "/blog/", "/docs/", "/help/", "/support/", "/careers/",
    "/jobs/", "/legal/", "/privacy", "/terms", "/sitemap",
    "/feed", "/rss", "/api/", "/login", "/signup", "/register",
    "/admin/", "/static/", "/assets/",
]


def _strip_html(text: str) -> str:
    """Remove HTML tags and collapse whitespace."""
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


class LandingPageCollector(BaseCollector):
    signal_type = SignalType.LANDING_PAGE_CREATED

    def collect_for_url(
        self, url: str, competitor: Competitor
    ) -> List[dict[str, Any]]:
        """Check if a specific URL is a strategic landing page."""
        page_text = self._fetch_page(url)
        if not page_text:
            raise ValueError(f"Could not fetch {url}")
        return self._analyze_page(page_text, url, competitor)

    def collect_for_competitor(
        self, competitor: Competitor
    ) -> List[dict[str, Any]]:
        """Probe strategic paths on competitor domain for landing pages."""
        domain = competitor.domain.rstrip("/")
        if not domain.startswith("http"):
            domain = f"https://{domain}"

        events: List[dict[str, Any]] = []
        seen_titles: set = set()

        for path in STRATEGIC_PATHS:
            url = f"{domain}{path}"
            try:
                page_text = self._fetch_page(url)
                if page_text:
                    signals = self._analyze_page(page_text, url, competitor)
                    for s in signals:
                        if s["title"] not in seen_titles:
                            events.append(s)
                            seen_titles.add(s["title"])
            except Exception:
                continue

        # Also try to discover landing pages from sitemap
        sitemap_pages = self._discover_from_sitemap(domain, competitor)
        for s in sitemap_pages:
            if s["title"] not in seen_titles:
                events.append(s)
                seen_titles.add(s["title"])

        return events

    def _fetch_page(self, url: str) -> str | None:
        """Fetch page HTML content."""
        try:
            with httpx.Client(timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
                resp = client.get(url, headers={"User-Agent": "CompetitiveIntel/1.0"})
                if resp.status_code != 200:
                    return None
                return resp.text
        except Exception:
            return None

    def _analyze_page(
        self, html: str, url: str, competitor: Competitor
    ) -> List[dict[str, Any]]:
        """Analyze if a URL is a strategic landing page."""
        events: List[dict[str, Any]] = []
        now = datetime.now(timezone.utc)

        parsed = urlparse(url)
        path = parsed.path.lower().rstrip("/")

        # Skip non-marketing pages
        if any(path.startswith(prefix) for prefix in IGNORE_PREFIXES):
            return events

        # Skip root page (not a "new" landing page)
        if not path or path == "/":
            return events

        # Extract page title
        title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
        page_title = _strip_html(title_match.group(1)) if title_match else path

        # Extract meta description
        meta_match = re.search(
            r'<meta[^>]*name=["\']description["\'][^>]*content=["\'](.*?)["\']',
            html, re.IGNORECASE
        )
        meta_desc = meta_match.group(1) if meta_match else ""

        # Extract h1
        h1_match = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.IGNORECASE | re.DOTALL)
        h1_text = _strip_html(h1_match.group(1)) if h1_match else ""

        # Check if this looks like a real landing page (has CTA, meaningful content)
        text = _strip_html(html).lower()
        has_cta = any(kw in text for kw in [
            "get started", "sign up", "book a demo", "start free",
            "try for free", "request demo", "talk to sales", "contact us",
            "learn more", "schedule", "start trial",
        ])
        has_enough_content = len(text) > 500

        if not (has_cta and has_enough_content):
            return events

        severity = "medium"
        # Strategic paths get higher severity
        strategic_indicators = [
            "/ai", "/enterprise", "/security", "/compliance",
            "/platform", "/solutions",
        ]
        if any(ind in path for ind in strategic_indicators):
            severity = "high"

        events.append({
            "title": f"Landing page: {page_title[:150]}",
            "description": (
                f"{competitor.name} has a strategic landing page at {url}. "
                f"Headline: \"{h1_text[:200]}\". "
                f"{('Description: ' + meta_desc[:200] + '. ') if meta_desc else ''}"
                f"This page contains CTAs and meaningful marketing content."
            ),
            "source_url": url,
            "event_time": now,
            "severity": severity,
            "metadata_json": {
                "page_title": page_title[:200],
                "h1": h1_text[:200],
                "meta_description": meta_desc[:300],
                "has_cta": has_cta,
                "path": path,
            },
        })

        return events

    def _discover_from_sitemap(
        self, domain: str, competitor: Competitor
    ) -> List[dict[str, Any]]:
        """Try to discover strategic pages from sitemap.xml."""
        events: List[dict[str, Any]] = []
        now = datetime.now(timezone.utc)

        sitemap_url = f"{domain}/sitemap.xml"
        try:
            with httpx.Client(timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
                resp = client.get(sitemap_url, headers={"User-Agent": "CompetitiveIntel/1.0"})
                if resp.status_code != 200:
                    return events
        except Exception:
            return events

        # Extract URLs from sitemap
        urls = re.findall(r'<loc>(.*?)</loc>', resp.text)

        strategic_urls = []
        for url in urls:
            parsed = urlparse(url)
            path = parsed.path.lower().rstrip("/")

            # Skip ignored paths
            if any(path.startswith(prefix) for prefix in IGNORE_PREFIXES):
                continue
            if not path or path == "/":
                continue

            # Check if it matches strategic patterns
            is_strategic = any(
                strategic in path
                for strategic in [
                    "/ai", "/automation", "/enterprise", "/use-cases",
                    "/solutions", "/platform", "/security", "/compliance",
                    "/analytics", "/workflow", "/for-",
                ]
            )
            if is_strategic:
                strategic_urls.append(url)

        if strategic_urls:
            events.append({
                "title": f"Sitemap: {len(strategic_urls)} strategic landing pages discovered",
                "description": (
                    f"{competitor.name} sitemap reveals {len(strategic_urls)} strategic pages: "
                    f"{', '.join(strategic_urls[:10])}."
                ),
                "source_url": sitemap_url,
                "event_time": now,
                "severity": "medium",
                "metadata_json": {
                    "strategic_urls": strategic_urls[:50],
                    "count": len(strategic_urls),
                },
            })

        return events
