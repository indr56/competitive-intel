"""
AI Visibility Intelligence API endpoints.

Routes:
- Keywords: CRUD + extraction
- Prompt Sources: suggestions + approval workflow
- Tracked Prompts: list, run, pause, delete
- Visibility Trends: analytics
- AI Impact Insights: correlation data
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.plan_enforcement import enforce_billing_active, get_workspace_billing
from app.core.billing import get_plan_limits
from app.models.models import (
    AIEngineResult,
    AIImpactInsight,
    AIPromptCluster,
    AIPromptRun,
    AIPromptSource,
    AITrackedPrompt,
    AIVisibilityEvent,
    AIWorkspaceKeyword,
    Competitor,
    PromptSourceType,
    PromptStatusEnum,
    Workspace,
)
from app.schemas.schemas import (
    AIEngineResultRead,
    AIImpactInsightRead,
    AIInsightCompactRead,
    AIInsightDetailRead,
    AIKeywordCreate,
    AIKeywordRead,
    AIPromptApproveRequest,
    AIPromptClusterRead,
    AIPromptRejectRequest,
    AIPromptRunRead,
    AIPromptSourceCreate,
    AIPromptSourceRead,
    AITrackedPromptRead,
    AIVisibilityEventRead,
    GenerateSuggestionsRequest,
    GenerateSuggestionsResponse,
    RunPromptsRequest,
    RunPromptsResponse,
    VisibilityTrendPoint,
    VisibilityTrendsResponse,
)
from app.services.ai_visibility.keyword_extraction import extract_keywords_for_workspace
from app.services.ai_visibility.prompt_suggestion import generate_all_suggestions
from app.services.ai_visibility.prompt_execution import normalize_prompt, run_workspace_prompts
from app.services.ai_visibility.workspace_filtering import filter_results_for_workspace
from app.services.ai_visibility.visibility_trends import (
    get_visibility_trends,
    get_engines_breakdown,
    get_competitor_visibility_summary,
    get_citation_urls,
)
from app.services.ai_visibility.correlation_engine import (
    correlate_signals_with_visibility,
    _generate_summary_text,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ai-visibility"])

PROMPT_LIMITS = {"starter": 10, "pro": 25, "agency": 100}


def _check_ws(db: Session, workspace_id: uuid.UUID) -> Workspace:
    ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not ws:
        raise HTTPException(404, "Workspace not found")
    return ws


def _check_prompt_limit(db: Session, workspace_id: uuid.UUID, count_to_add: int = 1):
    billing = get_workspace_billing(workspace_id, db)
    limit = PROMPT_LIMITS.get(billing.plan_type, 10)
    current = (
        db.query(AITrackedPrompt)
        .filter(AITrackedPrompt.workspace_id == workspace_id)
        .count()
    )
    if current + count_to_add > limit:
        raise HTTPException(
            403,
            f"Tracked prompt limit reached ({limit} for {billing.plan_type} plan). "
            f"Currently using {current}. Upgrade to add more.",
        )


# ═══════════════════════════════════════════════
# Keywords
# ═══════════════════════════════════════════════


@router.get(
    "/api/workspaces/{workspace_id}/ai-visibility/keywords",
    response_model=list[AIKeywordRead],
)
def list_keywords(
    workspace_id: uuid.UUID,
    source: str | None = None,
    db: Session = Depends(get_db),
):
    _check_ws(db, workspace_id)
    q = db.query(AIWorkspaceKeyword).filter(AIWorkspaceKeyword.workspace_id == workspace_id)
    if source:
        q = q.filter(AIWorkspaceKeyword.source == source)
    return q.order_by(AIWorkspaceKeyword.created_at.desc()).all()


@router.post(
    "/api/workspaces/{workspace_id}/ai-visibility/keywords",
    response_model=AIKeywordRead,
    status_code=201,
)
def add_keyword(
    workspace_id: uuid.UUID,
    body: AIKeywordCreate,
    db: Session = Depends(get_db),
):
    _check_ws(db, workspace_id)
    kw = body.keyword.strip().lower()
    if not kw or len(kw) < 2:
        raise HTTPException(400, "Keyword too short")

    existing = (
        db.query(AIWorkspaceKeyword)
        .filter(AIWorkspaceKeyword.workspace_id == workspace_id, AIWorkspaceKeyword.keyword == kw)
        .first()
    )
    if existing:
        raise HTTPException(409, "Keyword already exists")

    obj = AIWorkspaceKeyword(
        workspace_id=workspace_id,
        keyword=kw,
        source=body.source,
        is_approved=body.source == "user",
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.post(
    "/api/workspaces/{workspace_id}/ai-visibility/keywords/approve",
    response_model=list[AIKeywordRead],
)
def approve_keywords(
    workspace_id: uuid.UUID,
    keyword_ids: list[uuid.UUID],
    db: Session = Depends(get_db),
):
    _check_ws(db, workspace_id)
    keywords = (
        db.query(AIWorkspaceKeyword)
        .filter(
            AIWorkspaceKeyword.workspace_id == workspace_id,
            AIWorkspaceKeyword.id.in_(keyword_ids),
        )
        .all()
    )
    for kw in keywords:
        kw.is_approved = True
    db.commit()
    return keywords


@router.delete(
    "/api/workspaces/{workspace_id}/ai-visibility/keywords/{keyword_id}",
    status_code=204,
)
def delete_keyword(
    workspace_id: uuid.UUID,
    keyword_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    kw = (
        db.query(AIWorkspaceKeyword)
        .filter(AIWorkspaceKeyword.id == keyword_id, AIWorkspaceKeyword.workspace_id == workspace_id)
        .first()
    )
    if not kw:
        raise HTTPException(404, "Keyword not found")
    db.delete(kw)
    db.commit()


@router.post(
    "/api/workspaces/{workspace_id}/ai-visibility/keywords/extract",
)
def extract_keywords(
    workspace_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    _check_ws(db, workspace_id)
    result = extract_keywords_for_workspace(db, str(workspace_id))
    return result


# ═══════════════════════════════════════════════
# Prompt Sources (Suggestions)
# ═══════════════════════════════════════════════


@router.get(
    "/api/workspaces/{workspace_id}/ai-visibility/suggestions",
    response_model=list[AIPromptSourceRead],
)
def list_suggestions(
    workspace_id: uuid.UUID,
    source_type: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    _check_ws(db, workspace_id)
    q = db.query(AIPromptSource).filter(AIPromptSource.workspace_id == workspace_id)
    if source_type:
        q = q.filter(AIPromptSource.source_type == source_type)
    if status:
        q = q.filter(AIPromptSource.status == status)
    return q.order_by(AIPromptSource.created_at.desc()).all()


@router.post(
    "/api/workspaces/{workspace_id}/ai-visibility/suggestions",
    response_model=AIPromptSourceRead,
    status_code=201,
)
def add_suggestion(
    workspace_id: uuid.UUID,
    body: AIPromptSourceCreate,
    db: Session = Depends(get_db),
):
    _check_ws(db, workspace_id)
    text = body.prompt_text.strip().lower()
    if not text or len(text) < 5:
        raise HTTPException(400, "Prompt text too short")

    existing = (
        db.query(AIPromptSource)
        .filter(AIPromptSource.workspace_id == workspace_id, AIPromptSource.prompt_text == text)
        .first()
    )
    if existing:
        raise HTTPException(409, "Suggestion already exists")

    obj = AIPromptSource(
        workspace_id=workspace_id,
        prompt_text=text,
        source_type=body.source_type,
        source_detail=body.source_detail,
        status=PromptStatusEnum.SUGGESTED.value,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.post(
    "/api/workspaces/{workspace_id}/ai-visibility/suggestions/generate",
    response_model=GenerateSuggestionsResponse,
)
def generate_suggestions(
    workspace_id: uuid.UUID,
    body: GenerateSuggestionsRequest | None = None,
    db: Session = Depends(get_db),
):
    _check_ws(db, workspace_id)
    source_types = body.source_types if body else None
    result = generate_all_suggestions(db, str(workspace_id), source_types)
    return GenerateSuggestionsResponse(**result)


# ═══════════════════════════════════════════════
# Prompt Approval
# ═══════════════════════════════════════════════


@router.post(
    "/api/workspaces/{workspace_id}/ai-visibility/suggestions/approve",
    response_model=list[AITrackedPromptRead],
)
def approve_prompts(
    workspace_id: uuid.UUID,
    body: AIPromptApproveRequest,
    db: Session = Depends(get_db),
):
    """Approve suggested prompts → create tracked prompts."""
    _check_ws(db, workspace_id)

    sources = (
        db.query(AIPromptSource)
        .filter(
            AIPromptSource.workspace_id == workspace_id,
            AIPromptSource.id.in_(body.prompt_source_ids),
            AIPromptSource.status == PromptStatusEnum.SUGGESTED.value,
        )
        .all()
    )

    _check_prompt_limit(db, workspace_id, len(sources))

    created = []
    for src in sources:
        src.status = PromptStatusEnum.APPROVED.value

        # Check if already tracked
        existing = (
            db.query(AITrackedPrompt)
            .filter(
                AITrackedPrompt.workspace_id == workspace_id,
                AITrackedPrompt.prompt_text == src.prompt_text,
            )
            .first()
        )
        if existing:
            created.append(existing)
            continue

        tp = AITrackedPrompt(
            workspace_id=workspace_id,
            prompt_text=src.prompt_text,
            normalized_text=normalize_prompt(src.prompt_text),
            source_type=src.source_type,
            is_active=True,
        )
        db.add(tp)
        db.flush()
        created.append(tp)

    db.commit()
    for tp in created:
        db.refresh(tp)
    return created


@router.post(
    "/api/workspaces/{workspace_id}/ai-visibility/suggestions/reject",
)
def reject_prompts(
    workspace_id: uuid.UUID,
    body: AIPromptRejectRequest,
    db: Session = Depends(get_db),
):
    _check_ws(db, workspace_id)
    sources = (
        db.query(AIPromptSource)
        .filter(
            AIPromptSource.workspace_id == workspace_id,
            AIPromptSource.id.in_(body.prompt_source_ids),
        )
        .all()
    )
    for src in sources:
        src.status = PromptStatusEnum.REJECTED.value
    db.commit()
    return {"rejected": len(sources)}


# ═══════════════════════════════════════════════
# Tracked Prompts
# ═══════════════════════════════════════════════


@router.get(
    "/api/workspaces/{workspace_id}/ai-visibility/prompts",
    response_model=list[AITrackedPromptRead],
)
def list_tracked_prompts(
    workspace_id: uuid.UUID,
    active_only: bool = False,
    db: Session = Depends(get_db),
):
    _check_ws(db, workspace_id)
    q = db.query(AITrackedPrompt).filter(AITrackedPrompt.workspace_id == workspace_id)
    if active_only:
        q = q.filter(AITrackedPrompt.is_active == True)
    return q.order_by(AITrackedPrompt.created_at.desc()).all()


@router.post(
    "/api/workspaces/{workspace_id}/ai-visibility/prompts/{prompt_id}/pause",
)
def pause_prompt(
    workspace_id: uuid.UUID,
    prompt_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    tp = (
        db.query(AITrackedPrompt)
        .filter(AITrackedPrompt.id == prompt_id, AITrackedPrompt.workspace_id == workspace_id)
        .first()
    )
    if not tp:
        raise HTTPException(404, "Prompt not found")
    tp.is_active = not tp.is_active
    db.commit()
    db.refresh(tp)
    return {"id": str(tp.id), "is_active": tp.is_active}


@router.delete(
    "/api/workspaces/{workspace_id}/ai-visibility/prompts/{prompt_id}",
    status_code=204,
)
def delete_prompt(
    workspace_id: uuid.UUID,
    prompt_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    tp = (
        db.query(AITrackedPrompt)
        .filter(AITrackedPrompt.id == prompt_id, AITrackedPrompt.workspace_id == workspace_id)
        .first()
    )
    if not tp:
        raise HTTPException(404, "Prompt not found")
    db.delete(tp)
    db.commit()


@router.get(
    "/api/workspaces/{workspace_id}/ai-visibility/prompts/limits",
)
def get_prompt_limits(
    workspace_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    _check_ws(db, workspace_id)
    billing = get_workspace_billing(workspace_id, db)
    limit = PROMPT_LIMITS.get(billing.plan_type, 10)
    current = (
        db.query(AITrackedPrompt)
        .filter(AITrackedPrompt.workspace_id == workspace_id)
        .count()
    )
    return {"limit": limit, "used": current, "remaining": max(0, limit - current), "plan": billing.plan_type}


# ═══════════════════════════════════════════════
# Prompt Execution
# ═══════════════════════════════════════════════


@router.post(
    "/api/workspaces/{workspace_id}/ai-visibility/prompts/run",
    response_model=RunPromptsResponse,
)
def run_prompts(
    workspace_id: uuid.UUID,
    force: bool = False,
    body: RunPromptsRequest | None = None,
    db: Session = Depends(get_db),
):
    """Run prompts (manual trigger). Uses global cache. force=true clears cache."""
    _check_ws(db, workspace_id)
    prompt_ids = [str(pid) for pid in body.prompt_ids] if body and body.prompt_ids else None
    result = run_workspace_prompts(db, str(workspace_id), prompt_ids, force=force)
    filter_results_for_workspace(db, str(workspace_id))
    return RunPromptsResponse(**result)


@router.post(
    "/api/workspaces/{workspace_id}/ai-visibility/prompts/{prompt_id}/run",
    response_model=RunPromptsResponse,
)
def run_single_prompt(
    workspace_id: uuid.UUID,
    prompt_id: uuid.UUID,
    force: bool = False,
    db: Session = Depends(get_db),
):
    """Run a single prompt (Run Now button). force=true clears cache."""
    _check_ws(db, workspace_id)
    result = run_workspace_prompts(db, str(workspace_id), [str(prompt_id)], force=force)
    filter_results_for_workspace(db, str(workspace_id))
    return RunPromptsResponse(**result)


# ═══════════════════════════════════════════════
# Visibility Events
# ═══════════════════════════════════════════════


@router.get(
    "/api/workspaces/{workspace_id}/ai-visibility/events",
    response_model=list[AIVisibilityEventRead],
)
def list_visibility_events(
    workspace_id: uuid.UUID,
    competitor_id: uuid.UUID | None = None,
    engine: str | None = None,
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db),
):
    _check_ws(db, workspace_id)
    q = db.query(AIVisibilityEvent).filter(AIVisibilityEvent.workspace_id == workspace_id)
    if competitor_id:
        q = q.filter(AIVisibilityEvent.competitor_id == competitor_id)
    if engine:
        q = q.filter(AIVisibilityEvent.engine == engine)
    return q.order_by(AIVisibilityEvent.event_date.desc()).limit(limit).all()


@router.post(
    "/api/workspaces/{workspace_id}/ai-visibility/filter",
)
def run_workspace_filter(
    workspace_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """Manually trigger workspace filtering of global results."""
    _check_ws(db, workspace_id)
    result = filter_results_for_workspace(db, str(workspace_id))
    return result


# ═══════════════════════════════════════════════
# Visibility Trends
# ═══════════════════════════════════════════════


@router.get(
    "/api/workspaces/{workspace_id}/ai-visibility/trends",
)
def get_trends(
    workspace_id: uuid.UUID,
    competitor_id: uuid.UUID | None = None,
    days: int = Query(default=30, le=365),
    engine: str | None = None,
    db: Session = Depends(get_db),
):
    _check_ws(db, workspace_id)

    trends = get_visibility_trends(
        db, str(workspace_id),
        competitor_id=str(competitor_id) if competitor_id else None,
        days=days,
        engine=engine,
    )
    engines_breakdown = get_engines_breakdown(
        db, str(workspace_id),
        competitor_id=str(competitor_id) if competitor_id else None,
        days=days,
    )
    summary = get_competitor_visibility_summary(db, str(workspace_id), days=days)
    citations = get_citation_urls(
        db, str(workspace_id),
        competitor_id=str(competitor_id) if competitor_id else None,
        days=days,
    )

    return {
        "trends": trends,
        "engines_breakdown": engines_breakdown,
        "competitor_summary": summary,
        "citations": citations,
    }


# ═══════════════════════════════════════════════
# AI Impact Insights
# ═══════════════════════════════════════════════


@router.get(
    "/api/workspaces/{workspace_id}/ai-visibility/insights",
    response_model=list[AIImpactInsightRead],
)
def list_insights(
    workspace_id: uuid.UUID,
    competitor_id: uuid.UUID | None = None,
    priority: str | None = None,
    insight_type: str | None = None,
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_db),
):
    _check_ws(db, workspace_id)
    q = db.query(AIImpactInsight).filter(AIImpactInsight.workspace_id == workspace_id)
    if competitor_id:
        q = q.filter(AIImpactInsight.competitor_id == competitor_id)
    if priority:
        q = q.filter(AIImpactInsight.priority_level == priority)
    if insight_type:
        q = q.filter(AIImpactInsight.insight_type == insight_type)
    return q.order_by(AIImpactInsight.created_at.desc()).limit(limit).all()


@router.get(
    "/api/workspaces/{workspace_id}/ai-visibility/insights/compact",
    response_model=list[AIInsightCompactRead],
)
def list_insights_compact(
    workspace_id: uuid.UUID,
    competitor_id: uuid.UUID | None = None,
    priority: str | None = None,
    insight_type: str | None = None,
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_db),
):
    """Return compact insight cards for the feed view."""
    _check_ws(db, workspace_id)
    q = db.query(AIImpactInsight).filter(AIImpactInsight.workspace_id == workspace_id)
    if competitor_id:
        q = q.filter(AIImpactInsight.competitor_id == competitor_id)
    if priority:
        q = q.filter(AIImpactInsight.priority_level == priority)
    if insight_type:
        q = q.filter(AIImpactInsight.insight_type == insight_type)
    rows = q.order_by(AIImpactInsight.created_at.desc()).limit(limit).all()

    # Build comp name lookup
    comp_ids = {r.competitor_id for r in rows}
    comps = db.query(Competitor).filter(Competitor.id.in_(comp_ids)).all() if comp_ids else []
    comp_map = {str(c.id): c.name for c in comps}

    cards = []
    for r in rows:
        delta = (r.visibility_delta if r.visibility_delta is not None
                 else r.visibility_after - r.visibility_before)
        engines = r.engines_affected or []
        engine_summary = ", ".join(engines) if engines else "none"
        comp_name = comp_map.get(str(r.competitor_id), "Unknown")
        summary_text = _generate_summary_text(
            insight_type=r.insight_type or "ai_impact",
            competitor_name=comp_name,
            signal_type=r.signal_type or "",
            engines_affected=engines,
            visibility_delta=delta,
            visibility_before=r.visibility_before,
            visibility_after=r.visibility_after,
        )
        cards.append(AIInsightCompactRead(
            insight_id=r.id,
            insight_type=r.insight_type or "ai_impact",
            priority=r.priority_level,
            competitor_name=comp_name,
            signal_type=r.signal_type,
            short_title=r.short_title,
            signal_headline=r.signal_headline,
            visibility_before=r.visibility_before,
            visibility_after=r.visibility_after,
            visibility_delta=delta,
            engine_summary=engine_summary,
            impact_score=r.impact_score,
            correlation_confidence=r.correlation_confidence,
            summary_text=summary_text,
            timestamp=r.created_at,
        ))
    return cards


@router.get(
    "/api/workspaces/{workspace_id}/ai-visibility/insights/{insight_id}",
    response_model=AIInsightDetailRead,
)
def get_insight_detail(
    workspace_id: uuid.UUID,
    insight_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """Return expanded insight detail for a single insight."""
    _check_ws(db, workspace_id)
    r = (
        db.query(AIImpactInsight)
        .filter(
            AIImpactInsight.id == insight_id,
            AIImpactInsight.workspace_id == workspace_id,
        )
        .first()
    )
    if not r:
        raise HTTPException(404, "Insight not found")

    comp = db.query(Competitor).filter(Competitor.id == r.competitor_id).first()
    comp_name = comp.name if comp else "Unknown"

    delta = (r.visibility_delta if r.visibility_delta is not None
             else r.visibility_after - r.visibility_before)

    # Prompt context
    prompt_source = None
    prompt_run_timestamp = None
    if r.tracked_prompt_id:
        tp = db.query(AITrackedPrompt).filter(AITrackedPrompt.id == r.tracked_prompt_id).first()
        if tp:
            prompt_source = tp.source_type
            prompt_run_timestamp = tp.last_run_at

    # Citations by engine
    citations_by_engine: dict[str, list[str]] = {}
    if r.citations:
        for url in r.citations:
            citations_by_engine.setdefault("all", []).append(url)
    if r.engine_breakdown:
        for eng, data in r.engine_breakdown.items():
            cu = data.get("citation_url")
            if cu:
                citations_by_engine.setdefault(eng, []).append(cu)

    # Actions
    ws = str(workspace_id)
    actions = {
        "view_signal": f"/dashboard/activity-feed?signal_id={r.signal_event_id}" if r.signal_event_id else "",
        "view_prompt_analytics": f"/dashboard/ai-visibility/trends?prompt_id={r.tracked_prompt_id}" if r.tracked_prompt_id else "",
        "view_competitor_timeline": f"/dashboard/competitors/{r.competitor_id}",
        "rerun_prompt": f"/api/workspaces/{ws}/ai-visibility/prompts/{r.tracked_prompt_id}/run?force=true" if r.tracked_prompt_id else "",
    }

    return AIInsightDetailRead(
        insight_id=r.id,
        insight_type=r.insight_type or "ai_impact",
        competitor_name=comp_name,
        competitor_id=r.competitor_id,
        priority=r.priority_level,
        impact_score=r.impact_score,
        correlation_confidence=r.correlation_confidence,
        signal_type=r.signal_type,
        timestamp=r.created_at,
        signal_title=r.signal_title,
        signal_timestamp=r.signal_timestamp,
        signal_event_id=r.signal_event_id,
        prompt_text=r.prompt_text,
        prompt_cluster_name=r.prompt_cluster_name,
        prompt_source=prompt_source,
        prompt_run_timestamp=prompt_run_timestamp,
        visibility_before=r.visibility_before,
        visibility_after=r.visibility_after,
        visibility_delta=delta,
        engines_detected=r.engines_affected or [],
        engine_breakdown=r.engine_breakdown,
        citations=citations_by_engine,
        reasoning=r.reasoning,
        explanation=r.explanation,
        previous_mentions=r.previous_mentions or [],
        current_mentions=r.current_mentions or [],
        actions=actions,
        signal_headline=r.signal_headline,
        confidence_factors=r.confidence_factors,
        prompt_relevance_score=r.prompt_relevance_score,
    )


@router.post(
    "/api/workspaces/{workspace_id}/ai-visibility/insights/correlate",
)
def run_correlation(
    workspace_id: uuid.UUID,
    days: int = Query(default=7, le=30),
    db: Session = Depends(get_db),
):
    """Manually trigger correlation engine."""
    _check_ws(db, workspace_id)
    result = correlate_signals_with_visibility(db, str(workspace_id), days=days)
    return result


# ═══════════════════════════════════════════════
# Prompt Runs (admin view)
# ═══════════════════════════════════════════════


@router.get(
    "/api/workspaces/{workspace_id}/ai-visibility/runs",
    response_model=list[AIPromptRunRead],
)
def list_prompt_runs(
    workspace_id: uuid.UUID,
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_db),
):
    """List recent global prompt runs relevant to this workspace's tracked prompts."""
    _check_ws(db, workspace_id)
    # Get normalized texts for this workspace's tracked prompts
    tracked = (
        db.query(AITrackedPrompt.normalized_text)
        .filter(AITrackedPrompt.workspace_id == workspace_id)
        .all()
    )
    normalized_texts = [t[0] for t in tracked]
    if not normalized_texts:
        return []

    runs = (
        db.query(AIPromptRun)
        .filter(AIPromptRun.normalized_text.in_(normalized_texts))
        .order_by(AIPromptRun.run_date.desc())
        .limit(limit)
        .all()
    )
    return runs


@router.get(
    "/api/workspaces/{workspace_id}/ai-visibility/runs/{run_id}/results",
    response_model=list[AIEngineResultRead],
)
def get_run_results(
    workspace_id: uuid.UUID,
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    _check_ws(db, workspace_id)
    return (
        db.query(AIEngineResult)
        .filter(AIEngineResult.prompt_run_id == run_id)
        .order_by(AIEngineResult.engine)
        .all()
    )
