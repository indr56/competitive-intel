"""Scan service — runs signal collectors on-demand for a competitor, using configured sources."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.models.models import Competitor, SignalSource, SignalType
from app.schemas.schemas import (
    ScanResult,
    ScanResultItem,
    TestSourceResult,
)
from app.services.collectors.blog_collector import BlogCollector
from app.services.collectors.hiring_collector import HiringCollector
from app.services.collectors.funding_collector import FundingCollector
from app.services.collectors.review_collector import ReviewCollector
from app.services.collectors.positioning_collector import PositioningCollector
from app.services.collectors.integration_collector import IntegrationAddedCollector, IntegrationRemovedCollector
from app.services.collectors.landing_page_collector import LandingPageCollector

logger = logging.getLogger(__name__)

COLLECTOR_MAP = {
    SignalType.BLOG_POST.value: BlogCollector,
    SignalType.HIRING.value: HiringCollector,
    SignalType.FUNDING.value: FundingCollector,
    SignalType.REVIEW.value: ReviewCollector,
    SignalType.POSITIONING_CHANGE.value: PositioningCollector,
    SignalType.INTEGRATION_ADDED.value: IntegrationAddedCollector,
    SignalType.INTEGRATION_REMOVED.value: IntegrationRemovedCollector,
    SignalType.LANDING_PAGE_CREATED.value: LandingPageCollector,
}

# Signal types that have collectors
SCANNABLE_TYPES = set(COLLECTOR_MAP.keys())

REQUEST_TIMEOUT = 15.0


def scan_competitor(
    db: Session,
    competitor: Competitor,
    signal_types: list[str] | None = None,
) -> ScanResult:
    """
    Run signal collectors for a competitor using configured sources.
    If signal_types is None, scan all scannable types.
    """
    result = ScanResult(
        competitor_id=str(competitor.id),
        competitor_name=competitor.name,
    )

    types_to_scan = signal_types or list(SCANNABLE_TYPES)
    types_to_scan = [t for t in types_to_scan if t in SCANNABLE_TYPES]

    for sig_type in types_to_scan:
        # Get manual sources for this signal type
        sources = (
            db.query(SignalSource)
            .filter(
                SignalSource.competitor_id == competitor.id,
                SignalSource.signal_type == sig_type,
                SignalSource.is_active == True,  # noqa: E712
            )
            .all()
        )

        collector_cls = COLLECTOR_MAP.get(sig_type)
        if not collector_cls:
            continue

        collector = collector_cls(db)

        if sources:
            # Use configured sources
            for source in sources:
                item = _run_source_scan(db, collector, competitor, source)
                result.results.append(item)
                result.sources_scanned += 1
                result.total_events_found += item.events_found
                result.total_events_created += item.events_created
        else:
            # Fallback: auto-discovery (original collector behavior)
            item = _run_auto_discovery(collector, competitor, sig_type)
            result.results.append(item)
            result.sources_scanned += 1
            result.total_events_found += item.events_found
            result.total_events_created += item.events_created

    return result


def _run_source_scan(
    db: Session,
    collector,
    competitor: Competitor,
    source: SignalSource,
) -> ScanResultItem:
    """Run a collector against a specific configured source."""
    now = datetime.now(timezone.utc)
    item = ScanResultItem(
        signal_type=source.signal_type,
        source_url=source.source_url,
    )

    try:
        # Override the collector to use the specific source URL
        events = collector.collect_for_url(source.source_url, competitor)
        item.events_found = len(events)

        # Deduplicate and insert
        for event_data in events:
            created = collector._upsert_event(competitor, event_data)
            if created:
                item.events_created += 1
            else:
                item.events_skipped_dedup += 1

        source.last_checked_at = now
        source.last_success_at = now
        source.last_error = None
        db.commit()

    except Exception as exc:
        logger.error(
            "Scan failed for source %s (%s): %s",
            source.source_url, source.signal_type, exc,
        )
        item.error = str(exc)
        source.last_checked_at = now
        source.last_error = str(exc)
        db.commit()

    return item


def _run_auto_discovery(
    collector,
    competitor: Competitor,
    sig_type: str,
) -> ScanResultItem:
    """Run collector using auto-discovery (default paths)."""
    item = ScanResultItem(signal_type=sig_type)

    try:
        r = collector.run_for_competitor(competitor)
        item.events_found = r.events_found
        item.events_created = r.events_created
        item.events_skipped_dedup = r.events_skipped_dedup
        if r.errors:
            item.error = "; ".join(r.errors)
    except Exception as exc:
        item.error = str(exc)

    return item


def test_source(
    signal_type: str,
    source_url: str,
) -> TestSourceResult:
    """
    Test a signal source URL:
    1. Check if reachable
    2. Validate content matches expected signal type
    3. Return result with item count
    """
    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
            resp = client.get(
                source_url,
                headers={"User-Agent": "CompetitiveIntel/1.0 (source-test)"},
            )
    except httpx.ConnectError:
        return TestSourceResult(
            status="unreachable",
            message=f"Cannot connect to {source_url}",
        )
    except httpx.TimeoutException:
        return TestSourceResult(
            status="unreachable",
            message=f"Timeout connecting to {source_url}",
        )
    except Exception as exc:
        return TestSourceResult(
            status="unreachable",
            message=f"Error: {str(exc)}",
        )

    if resp.status_code >= 400:
        return TestSourceResult(
            status="unreachable",
            message=f"HTTP {resp.status_code} from {source_url}",
        )

    content = resp.text
    content_type = resp.headers.get("content-type", "")

    # Dispatch to signal-type-specific validation
    if signal_type == SignalType.BLOG_POST.value:
        return _test_blog_source(content, content_type, source_url)
    elif signal_type == SignalType.HIRING.value:
        return _test_hiring_source(content, source_url)
    elif signal_type == SignalType.FUNDING.value:
        return _test_funding_source(content, source_url)
    elif signal_type == SignalType.REVIEW.value:
        return _test_review_source(content, source_url)
    elif signal_type == SignalType.MARKETING.value:
        return _test_marketing_source(content, source_url)
    elif signal_type == SignalType.POSITIONING_CHANGE.value:
        return _test_positioning_source(content, source_url)
    elif signal_type == SignalType.INTEGRATION_ADDED.value:
        return _test_integration_source(content, source_url)
    elif signal_type == SignalType.INTEGRATION_REMOVED.value:
        return _test_integration_source(content, source_url)
    elif signal_type == SignalType.LANDING_PAGE_CREATED.value:
        return _test_landing_page_source(content, source_url)
    else:
        return TestSourceResult(
            status="valid",
            message=f"Source reachable (HTTP {resp.status_code}). Content validation not available for {signal_type}.",
        )


def _test_blog_source(content: str, content_type: str, url: str) -> TestSourceResult:
    """Test if URL is a valid blog/RSS/Atom feed."""
    import xml.etree.ElementTree as ET

    is_xml = (
        "xml" in content_type or "rss" in content_type or "atom" in content_type
        or content.strip().startswith("<?xml")
        or content.strip().startswith("<rss")
        or content.strip().startswith("<feed")
    )

    if is_xml:
        try:
            root = ET.fromstring(content)
            items = root.findall(".//item")
            entries = root.findall(".//{http://www.w3.org/2005/Atom}entry")
            count = len(items) + len(entries)
            if count > 0:
                return TestSourceResult(
                    status="valid",
                    message=f"Valid RSS/Atom feed with {count} entries",
                    items_found=count,
                    details={"feed_type": "rss" if items else "atom"},
                )
            return TestSourceResult(
                status="no_items_found",
                message="XML feed parsed but no <item> or <entry> elements found",
            )
        except ET.ParseError:
            pass

    # Check for blog-like HTML
    lower = content.lower()
    blog_indicators = ["<article", "blog-post", "post-title", "entry-title", "class=\"post"]
    found = sum(1 for ind in blog_indicators if ind in lower)
    if found >= 2:
        return TestSourceResult(
            status="valid",
            message=f"HTML page with blog-like content detected ({found} indicators)",
            items_found=found,
        )

    return TestSourceResult(
        status="unexpected_content",
        message="Page reachable but does not appear to be a blog feed or blog page",
    )


def _test_hiring_source(content: str, url: str) -> TestSourceResult:
    """Test if URL is a careers/jobs page."""
    lower = content.lower()
    job_keywords = [
        "careers", "jobs", "open positions", "we're hiring", "join our team",
        "apply now", "job openings", "current openings", "work with us",
    ]
    role_keywords = [
        "engineer", "manager", "designer", "analyst", "developer",
        "director", "lead", "intern", "scientist",
    ]

    job_hits = sum(1 for kw in job_keywords if kw in lower)
    role_hits = sum(1 for kw in role_keywords if kw in lower)

    if job_hits >= 2 and role_hits >= 1:
        return TestSourceResult(
            status="valid",
            message=f"Careers page detected: {job_hits} job indicators, {role_hits} role keywords",
            items_found=role_hits,
            details={"job_indicators": job_hits, "role_keywords": role_hits},
        )
    elif job_hits >= 1:
        return TestSourceResult(
            status="valid",
            message=f"Possible careers page: {job_hits} job indicators found",
            items_found=job_hits,
        )

    return TestSourceResult(
        status="no_items_found",
        message="Page reachable but no careers/job content detected",
    )


def _test_funding_source(content: str, url: str) -> TestSourceResult:
    """Test if URL has funding/press content."""
    lower = content.lower()
    funding_kw = [
        "funding", "series", "raised", "investment", "venture",
        "acquisition", "press release", "newsroom", "announcement",
    ]
    hits = sum(1 for kw in funding_kw if kw in lower)

    if hits >= 2:
        return TestSourceResult(
            status="valid",
            message=f"Press/funding page detected: {hits} relevant keywords",
            items_found=hits,
            details={"keywords_matched": hits},
        )
    elif hits >= 1:
        return TestSourceResult(
            status="valid",
            message=f"Possible press page: {hits} keyword found",
            items_found=hits,
        )

    return TestSourceResult(
        status="no_items_found",
        message="Page reachable but no funding/press content detected",
    )


def _test_review_source(content: str, url: str) -> TestSourceResult:
    """Test if URL has review/rating content."""
    import re
    rating_match = re.search(r'(\d+\.?\d*)\s*(?:out of\s*5|/\s*5|stars?)', content, re.IGNORECASE)
    count_match = re.search(r'(\d[\d,]*)\s*(?:reviews?|ratings?)', content, re.IGNORECASE)

    if rating_match and count_match:
        rating = float(rating_match.group(1))
        count = int(count_match.group(1).replace(",", ""))
        return TestSourceResult(
            status="valid",
            message=f"Review page: rating {rating}/5, {count} reviews detected",
            items_found=1,
            details={"rating": rating, "review_count": count},
        )
    elif rating_match:
        return TestSourceResult(
            status="valid",
            message=f"Rating found ({rating_match.group(1)}/5) but no review count",
            items_found=1,
        )
    elif count_match:
        return TestSourceResult(
            status="valid",
            message=f"Review count found ({count_match.group(1)}) but no rating",
            items_found=1,
        )

    return TestSourceResult(
        status="no_items_found",
        message="Page reachable but no rating/review data detected",
    )


def _test_marketing_source(content: str, url: str) -> TestSourceResult:
    """Test if URL has marketing/landing page content."""
    lower = content.lower()
    marketing_kw = [
        "vs ", "versus", "alternative", "compare", "comparison",
        "switch from", "migrate from", "better than", "why choose",
        "free trial", "get started", "sign up",
    ]
    hits = sum(1 for kw in marketing_kw if kw in lower)

    if hits >= 2:
        return TestSourceResult(
            status="valid",
            message=f"Marketing/comparison page detected: {hits} indicators",
            items_found=hits,
        )
    elif hits >= 1:
        return TestSourceResult(
            status="valid",
            message=f"Possible marketing page: {hits} indicator",
            items_found=hits,
        )

    return TestSourceResult(
        status="no_items_found",
        message="Page reachable but no marketing/comparison content detected",
    )


def _test_positioning_source(content: str, url: str) -> TestSourceResult:
    """Test if URL has positioning/messaging content."""
    lower = content.lower()
    positioning_kw = [
        "ai-powered", "all-in-one", "leading", "best-in-class",
        "next-generation", "platform for", "built for", "designed for",
        "transform", "reimagine", "future of", "the only",
        "enterprise-grade", "trusted by", "powering",
    ]
    structural_kw = ["<h1", "<h2", "hero", "headline", "tagline"]

    pos_hits = sum(1 for kw in positioning_kw if kw in lower)
    struct_hits = sum(1 for kw in structural_kw if kw in lower)

    if pos_hits >= 2 and struct_hits >= 1:
        return TestSourceResult(
            status="valid",
            message=f"Positioning page detected: {pos_hits} messaging keywords, {struct_hits} structural elements",
            items_found=pos_hits,
            details={"positioning_keywords": pos_hits, "structural_elements": struct_hits},
        )
    elif pos_hits >= 1:
        return TestSourceResult(
            status="valid",
            message=f"Possible positioning page: {pos_hits} messaging keyword(s)",
            items_found=pos_hits,
        )

    return TestSourceResult(
        status="no_items_found",
        message="Page reachable but no positioning/messaging content detected",
    )


def _test_integration_source(content: str, url: str) -> TestSourceResult:
    """Test if URL has integration/marketplace content."""
    lower = content.lower()
    integration_kw = [
        "integration", "connect", "apps", "marketplace", "partner",
        "plugin", "extension", "add-on", "connector", "ecosystem",
        "works with", "compatible",
    ]
    known_names = [
        "salesforce", "hubspot", "slack", "zapier", "openai",
        "stripe", "shopify", "github", "jira",
    ]

    kw_hits = sum(1 for kw in integration_kw if kw in lower)
    name_hits = sum(1 for n in known_names if n in lower)

    if kw_hits >= 2 and name_hits >= 2:
        return TestSourceResult(
            status="valid",
            message=f"Integrations page detected: {kw_hits} keywords, {name_hits} known integrations",
            items_found=name_hits,
            details={"integration_keywords": kw_hits, "known_integrations": name_hits},
        )
    elif kw_hits >= 1:
        return TestSourceResult(
            status="valid",
            message=f"Possible integrations page: {kw_hits} keyword(s)",
            items_found=kw_hits,
        )

    return TestSourceResult(
        status="no_items_found",
        message="Page reachable but no integration/marketplace content detected",
    )


def _test_landing_page_source(content: str, url: str) -> TestSourceResult:
    """Test if URL is a strategic landing page."""
    lower = content.lower()
    cta_kw = [
        "get started", "sign up", "book a demo", "start free",
        "try for free", "request demo", "talk to sales", "contact us",
        "learn more", "start trial",
    ]
    has_h1 = "<h1" in lower
    cta_hits = sum(1 for kw in cta_kw if kw in lower)
    content_length = len(lower)

    if has_h1 and cta_hits >= 1 and content_length > 500:
        return TestSourceResult(
            status="valid",
            message=f"Landing page detected: headline present, {cta_hits} CTA(s), {content_length} chars",
            items_found=1,
            details={"has_headline": has_h1, "cta_count": cta_hits, "content_length": content_length},
        )
    elif has_h1 or cta_hits >= 1:
        return TestSourceResult(
            status="valid",
            message=f"Possible landing page: headline={has_h1}, CTAs={cta_hits}",
            items_found=1,
        )

    return TestSourceResult(
        status="no_items_found",
        message="Page reachable but does not appear to be a strategic landing page",
    )
