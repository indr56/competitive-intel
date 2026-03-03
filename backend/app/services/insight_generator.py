from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.llm_service import LLMCallResult, get_llm_service
from app.core.prompt_templates import get_latest_template, get_template
from app.models.models import ChangeEvent, Diff, Insight
from app.services.differ import DiffResult

logger = logging.getLogger(__name__)

# Default insight types generated for every change event
DEFAULT_INSIGHT_TYPES = ["change_analysis"]


def _build_template_context(
    diff_record: Diff,
    change_event: ChangeEvent,
    diff_result: Optional[DiffResult] = None,
) -> Dict[str, Any]:
    """
    Build the template context dict from DB records.
    If a DiffResult is not provided, reconstruct additions/removals from raw_diff.
    """
    raw = diff_record.raw_diff or {}
    diff_lines_list = raw.get("lines", [])

    if diff_result:
        additions = diff_result.additions
        removals = diff_result.removals
    else:
        # Reconstruct from stored diff lines
        additions = [
            l[1:] for l in diff_lines_list
            if isinstance(l, str) and l.startswith("+") and not l.startswith("+++")
        ]
        removals = [
            l[1:] for l in diff_lines_list
            if isinstance(l, str) and l.startswith("-") and not l.startswith("---")
        ]

    page = diff_record.tracked_page
    page_type = page.page_type if page else "unknown"
    if hasattr(page_type, "value"):
        page_type = page_type.value

    rule_categories = change_event.categories or []

    return {
        "page_type": page_type,
        "additions": "\n".join(additions[:50]),
        "removals": "\n".join(removals[:50]),
        "diff_lines": "\n".join(diff_lines_list[:200]),
        "rule_categories": str(rule_categories),
        "_additions_list": additions,
        "_removals_list": removals,
    }


def _get_next_version(
    db: Session,
    change_event_id: str,
    insight_type: str,
) -> int:
    """Get the next version number for an insight."""
    latest = (
        db.query(Insight)
        .filter(
            Insight.change_event_id == change_event_id,
            Insight.insight_type == insight_type,
        )
        .order_by(Insight.version.desc())
        .first()
    )
    return (latest.version + 1) if latest else 1


def generate_insight(
    change_event_id: str,
    insight_type: str,
    db: Session,
    template_id: Optional[str] = None,
    custom_instructions: Optional[str] = None,
    regeneration_reason: Optional[str] = None,
    regenerated_from_id: Optional[str] = None,
) -> Insight:
    """
    Generate a single insight for a change event.

    1. Load change_event + diff from DB
    2. Build template context
    3. Call LLMService.generate_insight()
    4. Store result as Insight row
    """
    change_event = db.query(ChangeEvent).filter(
        ChangeEvent.id == change_event_id
    ).first()
    if not change_event:
        raise ValueError(f"ChangeEvent {change_event_id} not found")

    diff_record = change_event.diff
    if not diff_record:
        raise ValueError(f"No diff found for ChangeEvent {change_event_id}")

    # Resolve template
    if template_id:
        template = get_template(template_id)
    else:
        template = get_latest_template(insight_type)

    # Build context
    context = _build_template_context(diff_record, change_event)

    # Append custom instructions if provided
    if custom_instructions:
        context["diff_lines"] += f"\n\nAdditional instructions: {custom_instructions}"

    # Call LLM
    workspace_id = str(change_event.workspace_id)
    llm_service = get_llm_service()
    result: LLMCallResult = llm_service.generate_insight(
        template=template,
        context=context,
        workspace_id=workspace_id,
        additions=context["_additions_list"],
        removals=context["_removals_list"],
    )

    # Determine version
    version = _get_next_version(db, change_event_id, insight_type)

    # Build Insight record
    insight = Insight(
        change_event_id=change_event.id,
        insight_type=insight_type,
        version=version,
        prompt_template_id=template.template_id,
        content=result.content or {"error": result.error},
        evidence_refs=result.grounded_evidence or [],
        is_grounded=result.is_grounded,
        validation_errors=result.validation_errors,
        model_used=result.model_used,
        provider=result.provider,
        token_count_input=result.input_tokens,
        token_count_output=result.output_tokens,
        cost_usd=result.cost_usd,
        latency_ms=result.latency_ms,
        regeneration_reason=regeneration_reason,
        regenerated_from_id=regenerated_from_id,
    )
    db.add(insight)
    db.commit()
    db.refresh(insight)

    logger.info(
        "Generated %s v%d for change_event %s (grounded=%s, cost=$%.4f, %dms)",
        insight_type, version, change_event_id,
        result.is_grounded, result.cost_usd, result.latency_ms,
    )
    return insight


def generate_all_insights(
    change_event_id: str,
    db: Session,
    insight_types: Optional[List[str]] = None,
) -> List[Insight]:
    """
    Generate all default insight types for a change event.
    Returns list of created Insight records.
    """
    types = insight_types or DEFAULT_INSIGHT_TYPES
    insights = []
    for itype in types:
        try:
            insight = generate_insight(change_event_id, itype, db)
            insights.append(insight)
        except Exception as exc:
            logger.error(
                "Failed to generate %s for change_event %s: %s",
                itype, change_event_id, exc,
            )
    return insights


def regenerate_insight(
    insight_id: str,
    db: Session,
    reason: str = "manual",
    custom_instructions: Optional[str] = None,
) -> Insight:
    """
    Regenerate an existing insight, creating a new version.
    Preserves the old version.
    """
    original = db.query(Insight).filter(Insight.id == insight_id).first()
    if not original:
        raise ValueError(f"Insight {insight_id} not found")

    return generate_insight(
        change_event_id=str(original.change_event_id),
        insight_type=original.insight_type,
        db=db,
        regeneration_reason=reason,
        regenerated_from_id=insight_id,
        custom_instructions=custom_instructions,
    )
