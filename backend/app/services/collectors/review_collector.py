"""Review/sentiment signal collector — detects review count and rating changes."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, List

import httpx

from app.models.models import Competitor, CompetitorEvent, SignalType
from app.services.collectors.base import BaseCollector

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 15.0

# G2 and review platform paths
REVIEW_SOURCES = [
    {"platform": "g2", "url_template": "https://www.g2.com/products/{slug}/reviews"},
    {"platform": "trustpilot", "url_template": "https://www.trustpilot.com/review/{domain}"},
]

RATING_PATTERN = re.compile(r'(\d+\.?\d*)\s*(?:out of\s*5|/\s*5|stars?)', re.IGNORECASE)
REVIEW_COUNT_PATTERN = re.compile(r'(\d[\d,]*)\s*(?:reviews?|ratings?)', re.IGNORECASE)


class ReviewCollector(BaseCollector):
    signal_type = SignalType.REVIEW

    def collect_for_competitor(
        self, competitor: Competitor
    ) -> List[dict[str, Any]]:
        """Check review platforms for rating/count changes."""
        events: List[dict[str, Any]] = []

        # Try Trustpilot (uses domain directly)
        try:
            trustpilot_events = self._check_trustpilot(competitor)
            events.extend(trustpilot_events)
        except Exception as exc:
            logger.debug("Trustpilot check failed for %s: %s", competitor.domain, exc)

        # Try G2 (uses domain slug)
        try:
            g2_events = self._check_g2(competitor)
            events.extend(g2_events)
        except Exception as exc:
            logger.debug("G2 check failed for %s: %s", competitor.domain, exc)

        return events

    def _check_trustpilot(self, competitor: Competitor) -> List[dict[str, Any]]:
        """Check Trustpilot for review data."""
        domain = competitor.domain.replace("www.", "")
        url = f"https://www.trustpilot.com/review/{domain}"

        html = self._fetch_page(url)
        if not html:
            return []

        rating = self._extract_rating(html)
        review_count = self._extract_review_count(html)

        if rating is None and review_count is None:
            return []

        return self._build_review_event(
            competitor, "trustpilot", url, rating, review_count
        )

    def _check_g2(self, competitor: Competitor) -> List[dict[str, Any]]:
        """Check G2 for review data."""
        # G2 slug is typically the domain without TLD
        slug = competitor.domain.split(".")[0].lower()
        url = f"https://www.g2.com/products/{slug}/reviews"

        html = self._fetch_page(url)
        if not html:
            return []

        rating = self._extract_rating(html)
        review_count = self._extract_review_count(html)

        if rating is None and review_count is None:
            return []

        return self._build_review_event(
            competitor, "g2", url, rating, review_count
        )

    def _fetch_page(self, url: str) -> str | None:
        """Fetch a page and return text content."""
        with httpx.Client(timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
            resp = client.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; CompetitiveIntel/1.0)",
                    "Accept": "text/html",
                },
            )
            if resp.status_code != 200:
                return None
            return resp.text

    def _extract_rating(self, html: str) -> float | None:
        """Extract star rating from page."""
        matches = RATING_PATTERN.findall(html)
        for match in matches:
            try:
                rating = float(match)
                if 0 <= rating <= 5:
                    return rating
            except ValueError:
                continue
        return None

    def _extract_review_count(self, html: str) -> int | None:
        """Extract review count from page."""
        matches = REVIEW_COUNT_PATTERN.findall(html)
        for match in matches:
            try:
                count = int(match.replace(",", ""))
                if count > 0:
                    return count
            except ValueError:
                continue
        return None

    def _build_review_event(
        self,
        competitor: Competitor,
        platform: str,
        url: str,
        rating: float | None,
        review_count: int | None,
    ) -> List[dict[str, Any]]:
        """Build review event, comparing to previous data if available."""
        events: List[dict[str, Any]] = []
        now = datetime.now(timezone.utc)

        # Look up previous review event for comparison
        prev = (
            self.db.query(CompetitorEvent)
            .filter(
                CompetitorEvent.competitor_id == competitor.id,
                CompetitorEvent.signal_type == SignalType.REVIEW.value,
            )
            .order_by(CompetitorEvent.created_at.desc())
            .first()
        )

        prev_rating = None
        prev_count = None
        if prev and prev.metadata_json:
            prev_rating = prev.metadata_json.get("rating")
            prev_count = prev.metadata_json.get("review_count")

        # Build title based on changes detected
        parts = []
        severity = "low"

        if rating is not None:
            if prev_rating is not None and abs(rating - prev_rating) >= 0.1:
                direction = "↑" if rating > prev_rating else "↓"
                parts.append(f"Rating {prev_rating} → {rating} {direction}")
                if rating < prev_rating:
                    severity = "high" if (prev_rating - rating) >= 0.3 else "medium"
                else:
                    severity = "medium"
            elif prev_rating is None:
                parts.append(f"Rating: {rating}/5")

        if review_count is not None:
            if prev_count is not None and review_count != prev_count:
                diff = review_count - prev_count
                parts.append(f"Reviews: {prev_count} → {review_count} ({'+' if diff > 0 else ''}{diff})")
            elif prev_count is None:
                parts.append(f"{review_count} reviews")

        if not parts:
            return events

        title = f"{platform.capitalize()}: {'; '.join(parts)}"

        events.append({
            "title": title,
            "description": f"{competitor.name} on {platform.capitalize()}: {'; '.join(parts)}",
            "source_url": url,
            "event_time": now,
            "severity": severity,
            "metadata_json": {
                "platform": platform,
                "rating": rating,
                "review_count": review_count,
                "prev_rating": prev_rating,
                "prev_review_count": prev_count,
            },
        })

        return events
