from datetime import datetime

from pydantic import BaseModel


class InvestigateRequest(BaseModel):
    pass


class DecisionOut(BaseModel):
    decision_type: str
    confidence: float
    regulations_cited: list[dict]
    step_by_step_reasoning: str
    is_pep_override_applied: bool


class RiskAnalysisOut(BaseModel):
    risk_score: int
    justification: str
    anomalous_patterns: list[str]
    human_summary: str


class InvestigateResponse(BaseModel):
    alert_id: str
    status: str
    risk_analysis: RiskAnalysisOut | None = None
    decision: DecisionOut | None = None
    langfuse_trace_id: str = ""


class AlertStatusResponse(BaseModel):
    alert_id: str
    external_alert_id: str
    status: str
    customer_id: str
    is_pep: bool
    amount: float
    currency: str
    created_at: datetime


class AuditEventOut(BaseModel):
    event_type: str
    agent_name: str
    duration_ms: int
    token_cost_usd: float
    langfuse_trace_id: str
    created_at: datetime


class AuditTrailResponse(BaseModel):
    alert_id: str
    events: list[AuditEventOut]
