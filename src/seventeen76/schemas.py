from __future__ import annotations

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    email: str
    name: str = "Citizen"
    persona: str = ""
    interests: str = ""


class SessionResponse(BaseModel):
    token: str
    user_id: int
    name: str
    email: str
    persona: str = ""
    interests: str = ""


class AISearchRequest(BaseModel):
    query: str
    action_type: str | None = None


class RuleCard(BaseModel):
    id: int
    agency: str
    title: str
    tac_citation: str
    action_type: str
    status: str
    summary: str
    why_matters: str
    heard_signal: str
    source_url: str
    forecast_count: int = 0
    watched: bool = False
    match_reason: str = ""


class RuleDetail(RuleCard):
    affected_groups: list[str] = Field(default_factory=list)
    top_concerns: list["CommentResponse"] = Field(default_factory=list)
    findings: list["Finding"] = Field(default_factory=list)
    authority_links: list["AuthorityLink"] = Field(default_factory=list)


class SourceRef(BaseModel):
    id: int
    label: str
    url: str
    snippet: str


class CommentResponse(BaseModel):
    id: int
    concern: str
    agency_response: str
    disposition: str
    evidence_source_id: int | None = None


class Finding(BaseModel):
    id: int
    label: str
    summary: str
    source_id: int | None = None


class AuthorityLink(BaseModel):
    id: int
    citation: str
    url: str
    summary: str


class BriefResponse(BaseModel):
    rule_id: int
    plain_summary: str
    affected_groups: list[str]
    status_text: str
    public_heard_signal: str
    body: str
    source_ids: list[int]


class ForecastCard(BaseModel):
    id: int
    rule_id: int
    question: str
    display_question: str = ""
    resolution_criteria: str
    source_of_truth: str
    status: str
    aggregate_probability: float
    user_probability: float | None = None


class ForecastPositionRequest(BaseModel):
    probability: float = Field(ge=0, le=1)
    rationale: str = ""


class ForecastPositionResponse(BaseModel):
    forecast_id: int
    user_id: int
    probability: float
    aggregate_probability: float
    reputation: float


class WatchlistRequest(BaseModel):
    kind: str
    value: str


class WatchlistItem(BaseModel):
    id: int
    kind: str
    value: str


class AlertItem(BaseModel):
    id: int
    title: str
    body: str
    source_url: str
    read: bool
    created_at: str


class InvestigationResponse(BaseModel):
    rule_id: int
    graph_run_id: int
    status: str
    brief: BriefResponse


RuleDetail.model_rebuild()
