from __future__ import annotations

import hashlib
import hmac
import time
from typing import Optional
from urllib.parse import urlencode

from app.core.config import get_settings

DEFAULT_EXPIRY_SECONDS = 30 * 24 * 3600  # 30 days


def _get_secret() -> bytes:
    return get_settings().APP_SECRET_KEY.encode("utf-8")


def sign_digest_url(
    digest_id: str,
    base_url: Optional[str] = None,
    expiry_seconds: int = DEFAULT_EXPIRY_SECONDS,
) -> str:
    """
    Generate a signed URL for public digest report access.
    URL: {base}/api/report/{digest_id}?sig={signature}&exp={expiry}
    """
    exp = int(time.time()) + expiry_seconds
    signature = _compute_signature(digest_id, exp)
    base = base_url or f"http://127.0.0.1:{get_settings().API_PORT}"
    params = urlencode({"sig": signature, "exp": exp})
    return f"{base}/api/report/{digest_id}?{params}"


def verify_signature(digest_id: str, signature: str, expiry: int) -> bool:
    """Verify an HMAC signature and check expiry."""
    if int(time.time()) > expiry:
        return False
    expected = _compute_signature(digest_id, expiry)
    return hmac.compare_digest(signature, expected)


def sign_unsubscribe_token(user_id: str) -> str:
    """Generate an HMAC token for unsubscribe link."""
    payload = f"unsub:{user_id}"
    return hmac.new(_get_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_unsubscribe_token(user_id: str, token: str) -> bool:
    """Verify an unsubscribe token."""
    expected = sign_unsubscribe_token(user_id)
    return hmac.compare_digest(token, expected)


def _compute_signature(digest_id: str, expiry: int) -> str:
    payload = f"{digest_id}:{expiry}"
    return hmac.new(
        _get_secret(), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()
