from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Type

from pydantic import BaseModel

from app.core.insight_schemas import (
    BattlecardOutput,
    ChangeAnalysisOutput,
    ExecutiveBriefOutput,
    SalesEnablementOutput,
)

EVIDENCE_GUARDRAIL = (
    "CRITICAL RULE: You MUST quote specific text from the diff as evidence. "
    "Every claim you make must be backed by actual text that was added or removed. "
    "Never fabricate or assume changes that are not explicitly present in the diff. "
    "If you are unsure, say so. Do not hallucinate."
)


@dataclass
class PromptTemplate:
    template_id: str
    version: str
    insight_type: str
    system_prompt: str
    user_prompt: str
    output_schema: Type[BaseModel]
    description: str = ""
    model_tier: str = "default"


def _json_schema_hint(schema_cls: Type[BaseModel]) -> str:
    """Generate a JSON example hint from a Pydantic model's field names."""
    fields = schema_cls.model_fields
    lines = []
    for name, info in fields.items():
        desc = info.description or ""
        lines.append(f'  "{name}": "... {desc} ..."')
    return "{\n" + ",\n".join(lines) + "\n}"


# ── Change Analysis Template ──

CHANGE_ANALYSIS_V1 = PromptTemplate(
    template_id="change_analysis_v1",
    version="1.0",
    insight_type="change_analysis",
    description="Comprehensive change analysis with evidence-grounded insights",
    system_prompt=(
        "You are a senior competitive intelligence analyst at a SaaS company. "
        "You analyze changes detected on competitor websites and produce structured, "
        "actionable insights backed by evidence from the actual diff.\n\n"
        f"{EVIDENCE_GUARDRAIL}\n\n"
        "Respond ONLY with valid JSON matching the schema provided. "
        "No markdown, no commentary outside the JSON."
    ),
    user_prompt=(
        "A competitor's **{page_type}** page has changed.\n\n"
        "--- REMOVED TEXT ---\n{removals}\n\n"
        "--- ADDED TEXT ---\n{additions}\n\n"
        "--- UNIFIED DIFF ---\n{diff_lines}\n\n"
        "Rule-based categories detected: {rule_categories}\n\n"
        "Produce a JSON object with this exact schema:\n"
        "{schema_hint}\n\n"
        "Requirements:\n"
        "- summary: 1-2 sentences about what specifically changed\n"
        "- key_changes: each must have type, detail, and quoted evidence from the diff\n"
        "- strategic_impact: one of low, medium, high, critical\n"
        "- why_it_matters: strategic implication for us\n"
        "- recommended_actions: 2-3 concrete actions\n"
        "- confidence: 0.0-1.0 based on how clear the change is\n"
        "- evidence: list of exact quotes from the diff"
    ),
    output_schema=ChangeAnalysisOutput,
    model_tier="default",
)


# ── Battlecard Template ──

BATTLECARD_V1 = PromptTemplate(
    template_id="battlecard_v1",
    version="1.0",
    insight_type="battlecard",
    description="Sales-ready competitive battlecard based on detected changes",
    system_prompt=(
        "You are a competitive intelligence analyst writing sales battlecards. "
        "Your output is used directly by sales teams in live deals. "
        "Be specific, actionable, and always reference the actual diff evidence.\n\n"
        f"{EVIDENCE_GUARDRAIL}\n\n"
        "Respond ONLY with valid JSON matching the schema provided."
    ),
    user_prompt=(
        "A competitor's **{page_type}** page has changed.\n\n"
        "--- REMOVED TEXT ---\n{removals}\n\n"
        "--- ADDED TEXT ---\n{additions}\n\n"
        "--- UNIFIED DIFF ---\n{diff_lines}\n\n"
        "Produce a battlecard JSON with this schema:\n"
        "{schema_hint}\n\n"
        "Requirements:\n"
        "- competitor_positioning: how they position after this change\n"
        "- our_advantages: what advantages this change gives us\n"
        "- their_advantages: honest assessment of their strengths\n"
        "- objection_handlers: 2-3 objection/response pairs\n"
        "- key_talking_points: top 3 points for sales calls\n"
        "- evidence: exact quotes from the diff"
    ),
    output_schema=BattlecardOutput,
    model_tier="default",
)


# ── Executive Brief Template ──

EXECUTIVE_BRIEF_V1 = PromptTemplate(
    template_id="executive_brief_v1",
    version="1.0",
    insight_type="executive_brief",
    description="C-level strategic brief on competitive changes",
    system_prompt=(
        "You are a VP of Strategy writing a brief for the executive team. "
        "Be concise, strategic, and focused on business impact. "
        "Always ground claims in the actual changes detected.\n\n"
        f"{EVIDENCE_GUARDRAIL}\n\n"
        "Respond ONLY with valid JSON matching the schema provided."
    ),
    user_prompt=(
        "A competitor's **{page_type}** page has changed.\n\n"
        "--- REMOVED TEXT ---\n{removals}\n\n"
        "--- ADDED TEXT ---\n{additions}\n\n"
        "Produce an executive brief JSON with this schema:\n"
        "{schema_hint}\n\n"
        "Requirements:\n"
        "- headline: punchy one-liner for exec audience\n"
        "- tldr: one paragraph max\n"
        "- risk_level: low, medium, high, or critical\n"
        "- opportunity: what we can capitalize on\n"
        "- evidence: exact quotes from the diff"
    ),
    output_schema=ExecutiveBriefOutput,
    model_tier="default",
)


# ── Sales Enablement Template ──

SALES_ENABLEMENT_V1 = PromptTemplate(
    template_id="sales_enablement_v1",
    version="1.0",
    insight_type="sales_enablement",
    description="Sales talk tracks and discovery questions based on competitive changes",
    system_prompt=(
        "You are a sales enablement specialist. "
        "You create talk tracks, discovery questions, and positioning guidance "
        "that sales reps can use immediately in customer conversations. "
        "Be practical and specific.\n\n"
        f"{EVIDENCE_GUARDRAIL}\n\n"
        "Respond ONLY with valid JSON matching the schema provided."
    ),
    user_prompt=(
        "A competitor's **{page_type}** page has changed.\n\n"
        "--- REMOVED TEXT ---\n{removals}\n\n"
        "--- ADDED TEXT ---\n{additions}\n\n"
        "Produce a sales enablement JSON with this schema:\n"
        "{schema_hint}\n\n"
        "Requirements:\n"
        "- talk_track: paragraph for sales calls\n"
        "- discovery_questions: 3-4 questions to ask prospects\n"
        "- win_themes: 2-3 themes to drive toward\n"
        "- trap_questions: questions that expose competitor weaknesses\n"
        "- email_snippet: ready-to-paste outbound paragraph\n"
        "- evidence: exact quotes from the diff"
    ),
    output_schema=SalesEnablementOutput,
    model_tier="default",
)


# ── Template Registry ──

TEMPLATE_REGISTRY: Dict[str, PromptTemplate] = {
    t.template_id: t
    for t in [
        CHANGE_ANALYSIS_V1,
        BATTLECARD_V1,
        EXECUTIVE_BRIEF_V1,
        SALES_ENABLEMENT_V1,
    ]
}

# Also index by insight_type → latest template
LATEST_TEMPLATE_BY_TYPE: Dict[str, PromptTemplate] = {
    "change_analysis": CHANGE_ANALYSIS_V1,
    "battlecard": BATTLECARD_V1,
    "executive_brief": EXECUTIVE_BRIEF_V1,
    "sales_enablement": SALES_ENABLEMENT_V1,
}


def get_template(template_id: str) -> PromptTemplate:
    """Get a specific template by ID."""
    if template_id not in TEMPLATE_REGISTRY:
        raise ValueError(
            f"Unknown template '{template_id}'. "
            f"Available: {list(TEMPLATE_REGISTRY.keys())}"
        )
    return TEMPLATE_REGISTRY[template_id]


def get_latest_template(insight_type: str) -> PromptTemplate:
    """Get the latest version of a template for a given insight type."""
    if insight_type not in LATEST_TEMPLATE_BY_TYPE:
        raise ValueError(
            f"Unknown insight type '{insight_type}'. "
            f"Available: {list(LATEST_TEMPLATE_BY_TYPE.keys())}"
        )
    return LATEST_TEMPLATE_BY_TYPE[insight_type]


def render_prompt(
    template: PromptTemplate,
    context: Dict[str, Any],
) -> tuple:
    """
    Render system_prompt and user_prompt by substituting context variables.
    Returns (system_prompt, user_prompt).
    """
    schema_hint = _json_schema_hint(template.output_schema)
    ctx = {**context, "schema_hint": schema_hint}

    system = template.system_prompt
    user = template.user_prompt.format(**ctx)
    return system, user
