"""Positioning change collector — detects strategic messaging changes on key pages."""

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

# Pages where positioning/messaging is most visible
POSITIONING_PATHS = [
    "/",
    "/product",
    "/platform",
    "/solutions",
    "/about",
    "/why-us",
]

# Patterns that extract hero / headline-level text
HERO_PATTERNS = [
    re.compile(r'<h1[^>]*>(.*?)</h1>', re.IGNORECASE | re.DOTALL),
    re.compile(r'<h2[^>]*>(.*?)</h2>', re.IGNORECASE | re.DOTALL),
    re.compile(r'class="[^"]*hero[^"]*"[^>]*>(.*?)</(?:div|section)', re.IGNORECASE | re.DOTALL),
    re.compile(r'class="[^"]*headline[^"]*"[^>]*>(.*?)</(?:div|span|p)', re.IGNORECASE | re.DOTALL),
    re.compile(r'class="[^"]*tagline[^"]*"[^>]*>(.*?)</(?:div|span|p)', re.IGNORECASE | re.DOTALL),
]

# Messaging keywords that signal strategic positioning
POSITIONING_KEYWORDS = [
    "ai-powered", "all-in-one", "the #1", "leading", "best-in-class",
    "next-generation", "world's first", "fastest", "most powerful",
    "built for", "designed for", "reimagine", "transform", "future of",
    "platform for", "automation platform", "the only", "enterprise-grade",
    "trusted by", "powering", "supercharge", "accelerate", "unlock",
]


def _strip_html(text: str) -> str:
    """Remove HTML tags and collapse whitespace."""
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


class PositioningCollector(BaseCollector):
    signal_type = SignalType.POSITIONING_CHANGE

    def collect_for_url(
        self, url: str, competitor: Competitor
    ) -> List[dict[str, Any]]:
        """Scrape a specific page for positioning signals."""
        page_text = self._fetch_page(url)
        if not page_text:
            raise ValueError(f"Could not fetch {url}")
        return self._extract_positioning(page_text, url, competitor)

    def collect_for_competitor(
        self, competitor: Competitor
    ) -> List[dict[str, Any]]:
        """Scrape key pages for strategic messaging signals."""
        domain = competitor.domain.rstrip("/")
        if not domain.startswith("http"):
            domain = f"https://{domain}"

        events: List[dict[str, Any]] = []
        seen_titles: set = set()

        for path in POSITIONING_PATHS:
            url = f"{domain}{path}"
            try:
                page_text = self._fetch_page(url)
                if page_text:
                    signals = self._extract_positioning(page_text, url, competitor)
                    for s in signals:
                        if s["title"] not in seen_titles:
                            events.append(s)
                            seen_titles.add(s["title"])
            except Exception:
                continue

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

    def _extract_positioning(
        self, html: str, source_url: str, competitor: Competitor
    ) -> List[dict[str, Any]]:
        """Extract strategic messaging signals from page HTML."""
        events: List[dict[str, Any]] = []
        now = datetime.now(timezone.utc)

        # Extract headlines
        headlines: list[str] = []
        for pattern in HERO_PATTERNS:
            matches = pattern.findall(html)
            for match in matches:
                clean = _strip_html(match).strip()
                if clean and 5 < len(clean) < 300:
                    headlines.append(clean)

        if not headlines:
            return events

        # Check for positioning keywords in headlines
        text_lower = " ".join(headlines).lower()
        matched_keywords = [kw for kw in POSITIONING_KEYWORDS if kw in text_lower]

        if matched_keywords:
            top_headline = headlines[0][:200]
            severity = "high" if len(matched_keywords) >= 3 else "medium"
            events.append({
                "title": f"Positioning: \"{top_headline}\"",
                "description": (
                    f"{competitor.name} homepage/landing page features strategic messaging: "
                    f"\"{top_headline}\". "
                    f"Matched positioning keywords: {', '.join(matched_keywords[:5])}. "
                    f"Total {len(headlines)} headlines analyzed from {source_url}."
                ),
                "source_url": source_url,
                "event_time": now,
                "severity": severity,
                "metadata_json": {
                    "headlines": headlines[:10],
                    "matched_keywords": matched_keywords[:10],
                    "page_path": source_url,
                },
            })

        return events
