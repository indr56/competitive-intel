from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class KeyChange(BaseModel):
    type: str = Field(..., description="Category of change: pricing, feature, positioning, etc.")
    detail: str = Field(..., description="Specific description of what changed")
    evidence: str = Field(..., description="Quoted text from the diff proving this change")


class ChangeAnalysisOutput(BaseModel):
    summary: str = Field(..., description="1-2 sentence summary of what changed")
    key_changes: List[KeyChange] = Field(
        default_factory=list,
        description="Structured list of individual changes with evidence",
    )
    strategic_impact: str = Field(
        ..., description="low, medium, high, or critical"
    )
    why_it_matters: str = Field(..., description="Strategic implication for our company")
    recommended_actions: List[str] = Field(
        default_factory=list, description="2-3 concrete recommended actions"
    )
    confidence: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Confidence score 0-1"
    )
    evidence: List[str] = Field(
        default_factory=list,
        description="Quoted text from the diff supporting the analysis",
    )


class ObjectionHandler(BaseModel):
    objection: str = Field(..., description="Common buyer objection related to this change")
    response: str = Field(..., description="Recommended response for sales team")


class BattlecardOutput(BaseModel):
    competitor_positioning: str = Field(
        ..., description="How the competitor is positioning after this change"
    )
    our_advantages: List[str] = Field(
        default_factory=list, description="Our advantages given this change"
    )
    their_advantages: List[str] = Field(
        default_factory=list, description="Competitor advantages to be aware of"
    )
    objection_handlers: List[ObjectionHandler] = Field(
        default_factory=list, description="Objection-response pairs for sales"
    )
    key_talking_points: List[str] = Field(
        default_factory=list, description="Top 3 points for sales conversations"
    )
    evidence: List[str] = Field(
        default_factory=list,
        description="Quoted text from the diff supporting this battlecard",
    )


class ExecutiveBriefOutput(BaseModel):
    headline: str = Field(..., description="One-line headline for exec audience")
    tldr: str = Field(..., description="One paragraph executive summary")
    market_implications: str = Field(
        ..., description="What this means for the broader market"
    )
    risk_level: str = Field(..., description="low, medium, high, or critical")
    opportunity: str = Field(
        ..., description="What we can capitalize on from this change"
    )
    recommended_response: str = Field(
        ..., description="Recommended strategic response"
    )
    evidence: List[str] = Field(
        default_factory=list,
        description="Quoted text from the diff supporting this brief",
    )


class SalesEnablementOutput(BaseModel):
    talk_track: str = Field(
        ..., description="Paragraph-length talk track for sales calls"
    )
    discovery_questions: List[str] = Field(
        default_factory=list,
        description="Questions to ask prospects about competitor changes",
    )
    win_themes: List[str] = Field(
        default_factory=list, description="Key themes to drive toward in deals"
    )
    trap_questions: List[str] = Field(
        default_factory=list,
        description="Questions to set traps for competitor weaknesses",
    )
    email_snippet: str = Field(
        default="",
        description="Ready-to-paste email paragraph for outbound/follow-up",
    )
    evidence: List[str] = Field(
        default_factory=list,
        description="Quoted text from the diff supporting these recommendations",
    )


INSIGHT_TYPE_SCHEMAS = {
    "change_analysis": ChangeAnalysisOutput,
    "battlecard": BattlecardOutput,
    "executive_brief": ExecutiveBriefOutput,
    "sales_enablement": SalesEnablementOutput,
}
