"""Hiring signal collector — detects job listings from careers pages."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, List

import httpx

from app.models.models import Competitor, SignalType
from app.services.collectors.base import BaseCollector

logger = logging.getLogger(__name__)

CAREERS_PATHS = [
    "/careers",
    "/jobs",
    "/careers/open-positions",
    "/about/careers",
    "/company/careers",
    "/join",
    "/hiring",
    "/work-with-us",
]

REQUEST_TIMEOUT = 15.0

# Keywords indicating AI/engineering roles (high signal)
AI_KEYWORDS = [
    "machine learning", "ml engineer", "ai engineer", "data scientist",
    "llm", "nlp", "deep learning", "generative ai", "computer vision",
    "artificial intelligence",
]

ENGINEERING_KEYWORDS = [
    "software engineer", "frontend", "backend", "full stack", "fullstack",
    "devops", "sre", "platform engineer", "infrastructure",
]

PRODUCT_KEYWORDS = [
    "product manager", "product designer", "ux", "ui/ux",
    "head of product", "vp product",
]

SALES_KEYWORDS = [
    "account executive", "sales", "business development", "bdr", "sdr",
    "revenue", "customer success",
]


class HiringCollector(BaseCollector):
    signal_type = SignalType.HIRING

    def collect_for_competitor(
        self, competitor: Competitor
    ) -> List[dict[str, Any]]:
        """Scrape careers page for job listings."""
        domain = competitor.domain.rstrip("/")
        if not domain.startswith("http"):
            domain = f"https://{domain}"

        events: List[dict[str, Any]] = []

        for path in CAREERS_PATHS:
            url = f"{domain}{path}"
            try:
                page_text = self._fetch_page(url)
                if page_text:
                    jobs = self._extract_jobs(page_text, url, competitor)
                    events.extend(jobs)
                    if jobs:
                        logger.info(
                            "HiringCollector: found %d signals from %s%s",
                            len(jobs), competitor.domain, path,
                        )
                        break  # Found careers page
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

    def _extract_jobs(
        self, html: str, source_url: str, competitor: Competitor
    ) -> List[dict[str, Any]]:
        """Extract job-related signals from careers page HTML."""
        text_lower = html.lower()
        events: List[dict[str, Any]] = []

        # Count job categories
        ai_count = sum(1 for kw in AI_KEYWORDS if kw in text_lower)
        eng_count = sum(1 for kw in ENGINEERING_KEYWORDS if kw in text_lower)
        product_count = sum(1 for kw in PRODUCT_KEYWORDS if kw in text_lower)
        sales_count = sum(1 for kw in SALES_KEYWORDS if kw in text_lower)

        # Estimate total job count from common patterns
        job_patterns = re.findall(
            r'(?:position|role|job|opening|vacancy)', text_lower
        )
        estimated_total = max(len(job_patterns), ai_count + eng_count + product_count + sales_count)

        now = datetime.now(timezone.utc)

        if ai_count > 0:
            severity = "high" if ai_count >= 3 else "medium"
            events.append({
                "title": f"Hiring AI/ML engineers ({ai_count} roles detected)",
                "description": f"{competitor.name} has {ai_count} AI/ML-related job listings. "
                              f"This may indicate AI product expansion.",
                "source_url": source_url,
                "event_time": now,
                "severity": severity,
                "metadata_json": {
                    "category": "ai_ml",
                    "role_count": ai_count,
                    "estimated_total_openings": estimated_total,
                },
            })

        if eng_count > 0:
            events.append({
                "title": f"Hiring software engineers ({eng_count} roles detected)",
                "description": f"{competitor.name} has {eng_count} engineering job listings.",
                "source_url": source_url,
                "event_time": now,
                "severity": "low",
                "metadata_json": {
                    "category": "engineering",
                    "role_count": eng_count,
                    "estimated_total_openings": estimated_total,
                },
            })

        if product_count > 0:
            events.append({
                "title": f"Hiring product roles ({product_count} roles detected)",
                "description": f"{competitor.name} has {product_count} product-related job listings. "
                              f"May signal new product directions.",
                "source_url": source_url,
                "event_time": now,
                "severity": "medium",
                "metadata_json": {
                    "category": "product",
                    "role_count": product_count,
                    "estimated_total_openings": estimated_total,
                },
            })

        if sales_count > 0:
            events.append({
                "title": f"Hiring sales/BD roles ({sales_count} roles detected)",
                "description": f"{competitor.name} has {sales_count} sales/BD job listings. "
                              f"May signal go-to-market expansion.",
                "source_url": source_url,
                "event_time": now,
                "severity": "low",
                "metadata_json": {
                    "category": "sales",
                    "role_count": sales_count,
                    "estimated_total_openings": estimated_total,
                },
            })

        return events
