from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

from app.core.config import get_settings

logger = logging.getLogger(__name__)

COOKIE_BANNER_SELECTORS = [
    "[class*='cookie'] button",
    "[id*='cookie'] button",
    "#onetrust-accept-btn-handler",
    "[class*='consent'] button",
    "[class*='gdpr'] button",
    "button[aria-label*='accept']",
    "button[aria-label*='Accept']",
]


@dataclass
class CaptureResult:
    screenshot_bytes: bytes
    extracted_text: str
    text_hash: str
    html_content: str | None
    metadata: dict


def _dismiss_cookie_banners(page) -> None:
    for selector in COOKIE_BANNER_SELECTORS:
        try:
            btn = page.query_selector(selector)
            if btn and btn.is_visible():
                btn.click()
                page.wait_for_timeout(500)
                return
        except Exception:
            continue


def capture_page(url: str, save_html: bool = False) -> CaptureResult:
    """
    Capture a rendered snapshot of a URL using vanilla Playwright.
    Includes throttling and retry logic.
    """
    settings = get_settings()
    last_error: Exception | None = None

    for attempt in range(1, settings.CAPTURE_MAX_RETRIES + 1):
        try:
            return _do_capture(url, save_html, settings)
        except (PlaywrightTimeout, Exception) as exc:
            last_error = exc
            logger.warning(
                "Capture attempt %d/%d failed for %s: %s",
                attempt,
                settings.CAPTURE_MAX_RETRIES,
                url,
                str(exc),
            )
            if attempt < settings.CAPTURE_MAX_RETRIES:
                time.sleep(settings.CAPTURE_THROTTLE_SECONDS * attempt)

    raise RuntimeError(
        f"Capture failed after {settings.CAPTURE_MAX_RETRIES} retries for {url}"
    ) from last_error


def _do_capture(url: str, save_html: bool, settings) -> CaptureResult:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={
                "width": settings.CAPTURE_VIEWPORT_WIDTH,
                "height": settings.CAPTURE_VIEWPORT_HEIGHT,
            },
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        start_time = time.time()
        page.goto(url, wait_until="networkidle", timeout=settings.CAPTURE_TIMEOUT_MS)
        load_time = time.time() - start_time

        _dismiss_cookie_banners(page)

        # Throttle between actions
        time.sleep(settings.CAPTURE_THROTTLE_SECONDS)

        screenshot_bytes = page.screenshot(full_page=True)

        extracted_text = page.evaluate(
            """() => {
                const body = document.body;
                // Remove hidden elements from text extraction
                const hidden = body.querySelectorAll('[style*="display: none"], [style*="visibility: hidden"], [hidden]');
                hidden.forEach(el => el.remove());
                return body.innerText || '';
            }"""
        )

        html_content = None
        if save_html:
            html_content = page.content()

        text_hash = hashlib.sha256(extracted_text.encode("utf-8")).hexdigest()

        metadata = {
            "url": url,
            "status": page.url,
            "load_time_seconds": round(load_time, 2),
            "viewport": f"{settings.CAPTURE_VIEWPORT_WIDTH}x{settings.CAPTURE_VIEWPORT_HEIGHT}",
        }

        browser.close()

        return CaptureResult(
            screenshot_bytes=screenshot_bytes,
            extracted_text=extracted_text,
            text_hash=text_hash,
            html_content=html_content,
            metadata=metadata,
        )
