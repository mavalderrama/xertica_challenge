from typing import Any, TypedDict


class PipelineState(TypedDict, total=False):
    alert_id: str
    alert_data: dict[str, Any]
    investigation: dict[str, Any]
    risk_analysis: dict[str, Any]
    decision: dict[str, Any]
    errors: list[str]
    langfuse_trace_id: str
