"""Funding signal collector — detects funding announcements from press/blog pages."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, List

import httpx

from app.models.models import Competitor, SignalType
from app.services.collectors.base import BaseCollector

logger = logging.getLogger(__name__)

PRESS_PATHS = [
    "/blog",
    "/newsroom",
    "/press",
    "/news",
    "/about/news",
    "/company/news",
    "/press-releases",
    "/announcements",
]

REQUEST_TIMEOUT = 15.0

FUNDING_KEYWORDS = [
    "series a", "series b", "series c", "series d", "series e",
    "seed round", "pre-seed", "funding round", "raised $", "raised €",
    "raised £", "million in funding", "billion in funding",
    "investment round", "venture capital", "funding announcement",
    "acquisition", "acquired by", "has acquired", "merger",
    "ipo", "initial public offering", "went public",
]

FUNDING_PATTERN = re.compile(
    r"(?:raised|secures?d?|closes?d?|announces?d?)\s+"
    r"\$[\d,.]+\s*(?:million|billion|M|B)",
    re.IGNORECASE,
)

AMOUNT_PATTERN = re.compile(
    r"\$\s*([\d,.]+)\s*(million|billion|M|B)",
    re.IGNORECASE,
)


class FundingCollector(BaseCollector):
    signal_type = SignalType.FUNDING

    def collect_for_competitor(
        self, competitor: Competitor
    ) -> List[dict[str, Any]]:
        """Scrape press/blog pages for funding announcements."""
        domain = competitor.domain.rstrip("/")
        if not domain.startswith("http"):
            domain = f"https://{domain}"

        events: List[dict[str, Any]] = []

        for path in PRESS_PATHS:
            url = f"{domain}{path}"
            try:
                page_text = self._fetch_page(url)
                if page_text:
                    signals = self._detect_funding(page_text, url, competitor)
                    events.extend(signals)
                    if signals:
                        logger.info(
                            "FundingCollector: found %d signals from %s%s",
                            len(signals), competitor.domain, path,
                        )
            except Exception:
                continue

        return events

    def _fetch_page(self, url: str) -> str | None:
        """Fetch a page and return text content."""
        with httpx.Client(timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
            resp = client.get(url, headers={"User-Agent": "CompetitiveIntel/1.0"})
            if resp.status_code != 200:
                return None
            return resp.text

    def _detect_funding(
        self, html: str, source_url: str, competitor: Competitor
    ) -> List[dict[str, Any]]:
        """Detect funding signals from page text."""
        text_lower = html.lower()
        events: List[dict[str, Any]] = []

        # Check for funding keywords
        matched_keywords = [kw for kw in FUNDING_KEYWORDS if kw in text_lower]
        if not matched_keywords:
            return events

        # Try to extract specific funding amounts
        amounts = FUNDING_PATTERN.findall(html)
        amount_matches = AMOUNT_PATTERN.findall(html)

        now = datetime.now(timezone.utc)

        if amount_matches:
            for raw_amount, unit in amount_matches[:3]:  # Cap at 3
                amount_str = raw_amount.replace(",", "")
                try:
                    amount = float(amount_str)
                except ValueError:
                    continue
                if unit.lower() in ("billion", "b"):
                    amount *= 1000
                title = f"Funding: ${raw_amount} {unit} raised"
                events.append({
                    "title": title,
                    "description": f"{competitor.name} appears to have raised ${raw_amount} {unit} in funding.",
                    "source_url": source_url,
                    "event_time": now,
                    "severity": "critical" if amount >= 100 else "high",
                    "metadata_json": {
                        "amount_millions": amount,
                        "keywords_matched": matched_keywords[:5],
                    },
                })
        elif matched_keywords:
            # Generic funding signal without specific amount
            # Determine severity based on keywords
            is_acquisition = any(kw in matched_keywords for kw in ["acquisition", "acquired by", "has acquired"])
            severity = "critical" if is_acquisition else "high"
            signal_label = "Acquisition" if is_acquisition else "Funding activity"

            events.append({
                "title": f"{signal_label} detected",
                "description": f"{competitor.name} shows signs of {signal_label.lower()}. "
                              f"Keywords: {', '.join(matched_keywords[:5])}",
                "source_url": source_url,
                "event_time": now,
                "severity": severity,
                "metadata_json": {
                    "keywords_matched": matched_keywords[:10],
                },
            })

        return events
