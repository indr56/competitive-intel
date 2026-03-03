from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def send_email(
    to: list[str],
    subject: str,
    html_body: str,
    from_override: str | None = None,
) -> dict[str, Any]:
    """
    Send an email via Resend API.
    Returns the Resend response dict or error info.
    """
    settings = get_settings()

    if not settings.RESEND_API_KEY:
        logger.warning("RESEND_API_KEY not set — email not sent (subject: %s)", subject)
        return {"status": "skipped", "reason": "no_api_key"}

    payload = {
        "from": from_override or settings.EMAIL_FROM,
        "to": to,
        "subject": subject,
        "html": html_body,
    }

    try:
        resp = httpx.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {settings.RESEND_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=15.0,
        )
        resp.raise_for_status()
        result = resp.json()
        logger.info("Email sent: %s → %s (id=%s)", subject, to, result.get("id"))
        return result
    except httpx.HTTPStatusError as exc:
        logger.error("Resend API error: %s %s", exc.response.status_code, exc.response.text)
        return {"status": "error", "code": exc.response.status_code, "detail": exc.response.text}
    except Exception as exc:
        logger.error("Email send failed: %s", exc)
        return {"status": "error", "detail": str(exc)}


def build_digest_html(
    workspace_name: str,
    period_label: str,
    changes: list[dict[str, Any]],
) -> str:
    """
    Build digest email HTML from a list of change event dicts.
    Minimal template — upgrade to React Email / mjml in Phase 2.
    """
    change_rows = ""
    for ch in changes:
        severity_color = {
            "critical": "#dc2626",
            "high": "#ea580c",
            "medium": "#ca8a04",
            "low": "#65a30d",
        }.get(ch.get("severity", "medium"), "#6b7280")

        change_rows += f"""
        <tr>
            <td style="padding:12px;border-bottom:1px solid #e5e7eb;">
                <strong>{ch.get('competitor_name', 'Unknown')}</strong><br/>
                <span style="color:{severity_color};font-weight:600;text-transform:uppercase;font-size:12px;">
                    {ch.get('severity', 'medium')}
                </span>
                &nbsp;·&nbsp;
                <span style="color:#6b7280;font-size:12px;">
                    {', '.join(ch.get('categories', []))}
                </span>
            </td>
            <td style="padding:12px;border-bottom:1px solid #e5e7eb;">
                {ch.get('ai_summary', 'No summary available.')}
            </td>
        </tr>
        """

    return f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"></head>
    <body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;margin:0;padding:20px;background:#f9fafb;">
        <div style="max-width:640px;margin:0 auto;background:#fff;border-radius:8px;overflow:hidden;border:1px solid #e5e7eb;">
            <div style="background:#111827;color:#fff;padding:24px;">
                <h1 style="margin:0;font-size:20px;">Competitive Intel Digest</h1>
                <p style="margin:4px 0 0;opacity:0.8;font-size:14px;">{workspace_name} · {period_label}</p>
            </div>
            <table style="width:100%;border-collapse:collapse;">
                <thead>
                    <tr style="background:#f3f4f6;">
                        <th style="padding:12px;text-align:left;font-size:13px;color:#374151;">Competitor</th>
                        <th style="padding:12px;text-align:left;font-size:13px;color:#374151;">Summary</th>
                    </tr>
                </thead>
                <tbody>
                    {change_rows if change_rows else '<tr><td colspan="2" style="padding:24px;text-align:center;color:#9ca3af;">No changes detected this period.</td></tr>'}
                </tbody>
            </table>
            <div style="padding:16px;text-align:center;font-size:12px;color:#9ca3af;">
                Competitive Moves Intelligence
            </div>
        </div>
    </body>
    </html>
    """
