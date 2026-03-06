"""Blog signal collector — detects new blog posts and announcements."""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any, List
from email.utils import parsedate_to_datetime

import httpx

from app.models.models import Competitor, SignalType
from app.services.collectors.base import BaseCollector

logger = logging.getLogger(__name__)

# Common blog/RSS paths to check
BLOG_PATHS = [
    "/blog/feed",
    "/blog/rss",
    "/blog/rss.xml",
    "/feed",
    "/feed.xml",
    "/rss",
    "/rss.xml",
    "/atom.xml",
    "/blog/atom.xml",
]

REQUEST_TIMEOUT = 15.0
MAX_ENTRIES = 20


class BlogCollector(BaseCollector):
    signal_type = SignalType.BLOG_POST

    def collect_for_url(
        self, url: str, competitor: Competitor
    ) -> List[dict[str, Any]]:
        """Fetch a specific RSS/Atom feed URL."""
        try:
            entries = self._fetch_feed(url)
            return entries[:MAX_ENTRIES]
        except Exception as exc:
            logger.error("BlogCollector: failed to fetch %s: %s", url, exc)
            raise

    def collect_for_competitor(
        self, competitor: Competitor
    ) -> List[dict[str, Any]]:
        """Fetch RSS/Atom feeds for a competitor domain and extract new posts."""
        domain = competitor.domain.rstrip("/")
        if not domain.startswith("http"):
            domain = f"https://{domain}"

        events: List[dict[str, Any]] = []

        for path in BLOG_PATHS:
            url = f"{domain}{path}"
            try:
                entries = self._fetch_feed(url)
                for entry in entries[:MAX_ENTRIES]:
                    events.append(entry)
                if entries:
                    logger.info(
                        "BlogCollector: found %d posts from %s%s",
                        len(entries), competitor.domain, path,
                    )
                    break  # Found a working feed, stop trying other paths
            except Exception:
                continue  # Try next path

        return events

    def _fetch_feed(self, url: str) -> List[dict[str, Any]]:
        """Fetch and parse an RSS/Atom feed URL."""
        with httpx.Client(timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
            resp = client.get(url, headers={"User-Agent": "CompetitiveIntel/1.0"})
            resp.raise_for_status()

        content_type = resp.headers.get("content-type", "")
        if "xml" not in content_type and "rss" not in content_type and "atom" not in content_type:
            # Might still be XML, try parsing anyway
            if not resp.text.strip().startswith("<?xml") and not resp.text.strip().startswith("<rss") and not resp.text.strip().startswith("<feed"):
                return []

        try:
            root = ET.fromstring(resp.text)
        except ET.ParseError:
            return []

        # Try RSS 2.0
        entries = self._parse_rss(root)
        if entries:
            return entries

        # Try Atom
        entries = self._parse_atom(root)
        return entries

    def _parse_rss(self, root: ET.Element) -> List[dict[str, Any]]:
        """Parse RSS 2.0 feed."""
        entries = []
        # Handle both <rss><channel><item> and direct <channel><item>
        items = root.findall(".//item")
        for item in items[:MAX_ENTRIES]:
            title = self._text(item, "title")
            if not title:
                continue
            link = self._text(item, "link")
            description = self._text(item, "description")
            pub_date = self._text(item, "pubDate")

            event_time = datetime.now(timezone.utc)
            if pub_date:
                try:
                    event_time = parsedate_to_datetime(pub_date)
                    if event_time.tzinfo is None:
                        event_time = event_time.replace(tzinfo=timezone.utc)
                except Exception:
                    pass

            entries.append({
                "title": title[:512],
                "description": (description or "")[:2000],
                "source_url": link,
                "event_time": event_time,
                "severity": "low",
                "metadata_json": {"feed_type": "rss"},
            })
        return entries

    def _parse_atom(self, root: ET.Element) -> List[dict[str, Any]]:
        """Parse Atom feed."""
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entries = []
        for entry in root.findall("atom:entry", ns)[:MAX_ENTRIES]:
            title = self._text(entry, "atom:title", ns)
            if not title:
                continue
            link_el = entry.find("atom:link", ns)
            link = link_el.get("href") if link_el is not None else None
            summary = self._text(entry, "atom:summary", ns) or self._text(entry, "atom:content", ns)
            updated = self._text(entry, "atom:updated", ns) or self._text(entry, "atom:published", ns)

            event_time = datetime.now(timezone.utc)
            if updated:
                try:
                    event_time = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                except Exception:
                    pass

            entries.append({
                "title": title[:512],
                "description": (summary or "")[:2000],
                "source_url": link,
                "event_time": event_time,
                "severity": "low",
                "metadata_json": {"feed_type": "atom"},
            })
        return entries

    @staticmethod
    def _text(el: ET.Element, tag: str, ns: dict | None = None) -> str | None:
        child = el.find(tag, ns) if ns else el.find(tag)
        return child.text.strip() if child is not None and child.text else None
