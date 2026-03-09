"""
Prompt Execution Service — runs prompts globally across AI engines.

Key design:
- Prompts run GLOBALLY (not per workspace)
- Cache key: normalized_text + engine + date
- If result exists for today, reuse it
- Supports ChatGPT, Perplexity, Claude, Gemini
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.models import (
    AIEngineEnum,
    AIEngineResult,
    AIPromptRun,
    AITrackedPrompt,
    AIVisibilityEvent,
    Competitor,
    RunStatusEnum,
)

logger = logging.getLogger(__name__)

ENGINES = [e.value for e in AIEngineEnum]


def normalize_prompt(text: str) -> str:
    """Normalize prompt text for cache key matching."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text[:512]


def get_or_create_prompt_run(
    db: Session,
    prompt_text: str,
    run_date: Optional[datetime] = None,
) -> AIPromptRun:
    """
    Get existing prompt run for today or create a new one.
    This is the GLOBAL cache — if a run exists for this prompt+date, reuse it.
    """
    if run_date is None:
        run_date = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    normalized = normalize_prompt(prompt_text)

    existing = (
        db.query(AIPromptRun)
        .filter(
            AIPromptRun.normalized_text == normalized,
            AIPromptRun.run_date == run_date,
        )
        .first()
    )
    if existing:
        return existing

    run = AIPromptRun(
        prompt_text=prompt_text,
        normalized_text=normalized,
        run_date=run_date,
        status=RunStatusEnum.PENDING.value,
    )
    db.add(run)
    db.flush()
    return run


def _parse_brands_from_response(raw_response: str) -> tuple[list[str], list[dict], list[str]]:
    """
    Parse AI engine response to extract mentioned brands, ranking data, and citations.
    Uses heuristic parsing since actual AI responses vary.
    """
    brands: list[str] = []
    ranking_data: list[dict] = []
    citations: list[str] = []

    if not raw_response:
        return brands, ranking_data, citations

    # Extract numbered list items (common AI response format)
    # Pattern: "1. BrandName" or "1) BrandName" or "- BrandName"
    lines = raw_response.split('\n')
    position = 0
    for line in lines:
        line = line.strip()
        # Numbered list: "1. HubSpot — ..." or "1. **HubSpot**"
        match = re.match(r'^(\d+)[.\)]\s*\**([A-Z][A-Za-z0-9\s\.\-]+)\**', line)
        if match:
            position += 1
            brand = match.group(2).strip().rstrip('*').strip()
            if brand and len(brand) < 100:
                brands.append(brand)
                ranking_data.append({"brand": brand, "position": position})

        # Extract URLs as citations
        urls = re.findall(r'https?://[^\s\)\"\']+', line)
        citations.extend(urls)

    return brands, ranking_data, citations


def execute_prompt_on_engine(
    db: Session,
    prompt_run: AIPromptRun,
    engine: str,
) -> AIEngineResult:
    """
    Execute a prompt on a specific AI engine.
    If cached result exists, return it.

    NOTE: In production, this would call actual AI APIs.
    Currently uses a simulation that returns realistic mock data.
    Set environment variables for real API keys:
    - OPENAI_API_KEY (ChatGPT)
    - PERPLEXITY_API_KEY
    - ANTHROPIC_API_KEY (Claude)
    - GOOGLE_API_KEY (Gemini)
    """
    # Check cache first
    existing = (
        db.query(AIEngineResult)
        .filter(
            AIEngineResult.prompt_run_id == prompt_run.id,
            AIEngineResult.engine == engine,
        )
        .first()
    )
    if existing and existing.status == RunStatusEnum.COMPLETED.value:
        return existing

    if existing:
        result = existing
    else:
        result = AIEngineResult(
            prompt_run_id=prompt_run.id,
            engine=engine,
            status=RunStatusEnum.RUNNING.value,
        )
        db.add(result)
        db.flush()

    try:
        # --- Simulated AI engine response ---
        # In production, replace with actual API calls
        # Query all competitor names globally (not per-workspace) to make
        # simulation realistic — real AI engines would mention real brands.
        all_comps = db.query(Competitor.name).distinct().all()
        known_brands = [c[0] for c in all_comps if c[0]]
        raw_response = _simulate_engine_response(prompt_run.prompt_text, engine, known_brands)

        brands, ranking_data, citations = _parse_brands_from_response(raw_response)

        result.raw_response = raw_response
        result.mentioned_brands = brands
        result.ranking_data = ranking_data
        result.citations = citations
        result.status = RunStatusEnum.COMPLETED.value
        result.executed_at = datetime.now(timezone.utc)
        result.error_message = None

    except Exception as e:
        logger.error(f"Engine {engine} failed for prompt '{prompt_run.prompt_text[:50]}': {e}")
        result.status = RunStatusEnum.FAILED.value
        result.error_message = str(e)[:500]

    db.flush()
    return result


def _simulate_engine_response(
    prompt_text: str,
    engine: str,
    known_brands: list[str] | None = None,
) -> str:
    """
    Simulate an AI engine response for development/testing.
    Returns a realistic-looking response with brand mentions.

    known_brands: real competitor names from the DB (global, not per-workspace).
    These are injected into the response so workspace filtering can find matches.
    In production (real API calls), this parameter is unused.
    """
    import hashlib
    # Deterministic but varied response based on prompt + engine
    seed = hashlib.md5(f"{prompt_text}:{engine}".encode()).hexdigest()
    seed_int = int(seed[:8], 16)

    # Pool of well-known SaaS brands
    brand_pool = [
        "HubSpot", "Salesforce", "Zapier", "Monday.com", "Asana",
        "Slack", "Notion", "Airtable", "ClickUp", "Trello",
        "Jira", "Linear", "Figma", "Canva", "Miro",
        "Stripe", "Shopify", "Zendesk", "Intercom", "Drift",
        "Mailchimp", "ActiveCampaign", "Semrush", "Ahrefs", "Moz",
        "Datadog", "Snowflake", "Databricks", "Vercel", "Netlify",
    ]

    # Select 5-8 brands deterministically (unchanged from original)
    n_brands = 5 + (seed_int % 4)
    selected = []
    for i in range(n_brands):
        idx = (seed_int + i * 7) % len(brand_pool)
        b = brand_pool[idx]
        if b not in selected:
            selected.append(b)

    # Check if prompt mentions a specific brand and ensure it's included
    prompt_lower = prompt_text.lower()
    for brand in brand_pool:
        if brand.lower() in prompt_lower and brand not in selected:
            selected.insert(0, brand)
            break

    # Inject real competitor brands from DB so filtering can find matches.
    # Deterministically pick 1-3 known brands and insert at varied positions.
    if known_brands:
        n_inject = 1 + (seed_int % min(3, len(known_brands)))
        for i in range(n_inject):
            kb = known_brands[(seed_int + i * 3) % len(known_brands)]
            if kb and kb not in selected:
                insert_pos = min((seed_int + i) % 4, len(selected))
                selected.insert(insert_pos, kb)
        # Also check if prompt mentions a known brand by name
        for kb in known_brands:
            if kb and kb.lower() in prompt_lower and kb not in selected:
                selected.insert(0, kb)
                break
        selected = selected[:8]  # Cap at 8

    lines = [f"Here are the top {engine} recommendations:\n"]
    for i, brand in enumerate(selected, 1):
        lines.append(f"{i}. **{brand}** — A leading solution in this space.")
        if i <= 3:
            domain = brand.lower().replace('.', '').replace(' ', '') + ".com"
            lines.append(f"   Source: https://{domain}")
    lines.append(f"\nThese are based on current market analysis as of 2025.")

    return "\n".join(lines)


def run_prompt_globally(
    db: Session,
    prompt_text: str,
    run_date: Optional[datetime] = None,
) -> AIPromptRun:
    """
    Execute a prompt across all AI engines globally.
    Uses cache — if results exist for today, returns cached.
    """
    prompt_run = get_or_create_prompt_run(db, prompt_text, run_date)

    if prompt_run.status == RunStatusEnum.COMPLETED.value:
        # All engines already ran
        return prompt_run

    prompt_run.status = RunStatusEnum.RUNNING.value
    prompt_run.started_at = datetime.now(timezone.utc)
    db.flush()

    all_completed = True
    for engine in ENGINES:
        result = execute_prompt_on_engine(db, prompt_run, engine)
        if result.status != RunStatusEnum.COMPLETED.value:
            all_completed = False

    if all_completed:
        prompt_run.status = RunStatusEnum.COMPLETED.value
        prompt_run.completed_at = datetime.now(timezone.utc)
    else:
        prompt_run.status = RunStatusEnum.FAILED.value

    db.flush()
    return prompt_run


def run_workspace_prompts(
    db: Session,
    workspace_id: str,
    prompt_ids: Optional[List[str]] = None,
    force: bool = False,
) -> dict:
    """
    Run prompts for a workspace. Leverages global execution with caching.
    If force=True, clear cached results and re-execute.
    Returns summary of what was executed vs cached.
    """
    query = (
        db.query(AITrackedPrompt)
        .filter(
            AITrackedPrompt.workspace_id == workspace_id,
            AITrackedPrompt.is_active == True,
        )
    )
    if prompt_ids:
        query = query.filter(AITrackedPrompt.id.in_(prompt_ids))

    prompts = query.all()

    queued = 0
    cached = 0
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    for tp in prompts:
        normalized = normalize_prompt(tp.prompt_text)
        existing = (
            db.query(AIPromptRun)
            .filter(
                AIPromptRun.normalized_text == normalized,
                AIPromptRun.run_date == today,
                AIPromptRun.status == RunStatusEnum.COMPLETED.value,
            )
            .first()
        )

        if existing and force:
            # Clear stale cache: delete visibility events, engine results, reset run
            engine_result_ids = [
                er.id for er in db.query(AIEngineResult).filter(
                    AIEngineResult.prompt_run_id == existing.id
                ).all()
            ]
            if engine_result_ids:
                db.query(AIVisibilityEvent).filter(
                    AIVisibilityEvent.engine_result_id.in_(engine_result_ids)
                ).delete(synchronize_session=False)
                db.query(AIEngineResult).filter(
                    AIEngineResult.prompt_run_id == existing.id
                ).delete(synchronize_session=False)
            existing.status = RunStatusEnum.PENDING.value
            existing.started_at = None
            existing.completed_at = None
            db.flush()
            existing = None  # Fall through to re-execute

        if existing:
            cached += 1
            tp.last_run_at = datetime.now(timezone.utc)
        else:
            run_prompt_globally(db, tp.prompt_text, today)
            tp.last_run_at = datetime.now(timezone.utc)
            queued += 1

    db.commit()

    return {
        "prompts_queued": queued,
        "cached_reused": cached,
        "message": f"Executed {queued} new, reused {cached} cached results.",
    }
