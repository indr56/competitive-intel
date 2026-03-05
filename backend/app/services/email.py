from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

SEVERITY_COLORS = {
    "critical": "#dc2626",
    "high": "#ea580c",
    "medium": "#ca8a04",
    "low": "#65a30d",
}


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
    theme: Any = None,
) -> str:
    """
    Build white-label digest email HTML.
    Theme is a WhiteLabelTheme dataclass (or None for defaults).
    """
    brand_color = getattr(theme, "brand_color", "#111827") if theme else "#111827"
    logo_url = getattr(theme, "logo_url", None) if theme else None
    company_name = getattr(theme, "company_name", "Competitive Moves Intelligence") if theme else "Competitive Moves Intelligence"
    footer_text = getattr(theme, "footer_text", f"Powered by {company_name}") if theme else f"Powered by {company_name}"

    logo_html = ""
    if logo_url:
        logo_html = f'<img src="{logo_url}" alt="{company_name}" style="max-height:32px;margin-bottom:8px;" /><br/>'

    change_rows = ""
    for i, ch in enumerate(changes):
        sev = ch.get("severity", "medium")
        severity_color = SEVERITY_COLORS.get(sev, "#6b7280")
        rank = ch.get("rank_score", 0)
        impact = ch.get("impact_score", 0)
        why = ch.get("ai_why_it_matters", "")
        next_moves = ch.get("ai_next_moves", "")

        detail_section = ""
        if why:
            detail_section += f'<p style="margin:6px 0 0;font-size:13px;color:#4b5563;"><strong>Why it matters:</strong> {why}</p>'
        if next_moves:
            detail_section += f'<p style="margin:4px 0 0;font-size:13px;color:#4b5563;"><strong>Next moves:</strong> {next_moves}</p>'

        change_rows += f"""
        <tr>
            <td style="padding:14px;border-bottom:1px solid #e5e7eb;vertical-align:top;width:200px;">
                <strong>{ch.get('competitor_name', 'Unknown')}</strong><br/>
                <span style="color:{severity_color};font-weight:600;text-transform:uppercase;font-size:11px;">
                    {sev}
                </span>
                &nbsp;·&nbsp;
                <span style="color:#6b7280;font-size:11px;">
                    {', '.join(ch.get('categories', []))}
                </span>
                <br/>
                <span style="font-size:10px;color:#9ca3af;">Score: {rank:.0f} · Impact: {impact:.0f}</span>
            </td>
            <td style="padding:14px;border-bottom:1px solid #e5e7eb;vertical-align:top;">
                <p style="margin:0;font-size:14px;">{ch.get('ai_summary', 'No summary available.')}</p>
                {detail_section}
            </td>
        </tr>
        """

    empty_row = '<tr><td colspan="2" style="padding:24px;text-align:center;color:#9ca3af;">No changes detected this period.</td></tr>'

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;margin:0;padding:20px;background:#f9fafb;">
    <div style="max-width:680px;margin:0 auto;background:#fff;border-radius:8px;overflow:hidden;border:1px solid #e5e7eb;">
        <div style="background:{brand_color};color:#fff;padding:24px;">
            {logo_html}
            <h1 style="margin:0;font-size:20px;">Competitive Intel Digest</h1>
            <p style="margin:4px 0 0;opacity:0.8;font-size:14px;">{workspace_name} · {period_label}</p>
            <p style="margin:4px 0 0;opacity:0.6;font-size:12px;">{len(changes)} change{'s' if len(changes) != 1 else ''} ranked by impact</p>
        </div>
        <table style="width:100%;border-collapse:collapse;">
            <thead>
                <tr style="background:#f3f4f6;">
                    <th style="padding:12px;text-align:left;font-size:12px;color:#374151;text-transform:uppercase;letter-spacing:0.5px;">Competitor</th>
                    <th style="padding:12px;text-align:left;font-size:12px;color:#374151;text-transform:uppercase;letter-spacing:0.5px;">Summary &amp; Insights</th>
                </tr>
            </thead>
            <tbody>
                {change_rows if change_rows else empty_row}
            </tbody>
        </table>
        <div style="padding:16px;text-align:center;font-size:11px;color:#9ca3af;border-top:1px solid #e5e7eb;">
            {footer_text}
        </div>
    </div>
</body>
</html>"""


def build_digest_markdown(
    workspace_name: str,
    period_label: str,
    changes: list[dict[str, Any]],
    theme: Any = None,
) -> str:
    """
    Build plain-text Markdown fallback for digest email.
    """
    company_name = getattr(theme, "company_name", "Competitive Moves Intelligence") if theme else "Competitive Moves Intelligence"

    lines = [
        "# Competitive Intel Digest",
        f"**{workspace_name}** · {period_label}",
        f"{len(changes)} change{'s' if len(changes) != 1 else ''} ranked by impact",
        "",
        "---",
        "",
    ]

    for i, ch in enumerate(changes, 1):
        sev = ch.get("severity", "medium").upper()
        categories = ", ".join(ch.get("categories", []))
        summary = ch.get("ai_summary", "No summary available.")
        why = ch.get("ai_why_it_matters", "")
        next_moves = ch.get("ai_next_moves", "")
        rank = ch.get("rank_score", 0)

        lines.append(f"## {i}. {ch.get('competitor_name', 'Unknown')}")
        lines.append(f"**Severity:** {sev} · **Categories:** {categories} · **Score:** {rank:.0f}")
        lines.append("")
        lines.append(summary)
        if why:
            lines.append("")
            lines.append(f"**Why it matters:** {why}")
        if next_moves:
            lines.append("")
            lines.append(f"**Next moves:** {next_moves}")
        lines.append("")
        lines.append("---")
        lines.append("")

    lines.append(f"*{company_name}*")
    return "\n".join(lines)
