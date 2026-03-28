from fastapi import APIRouter, Depends, HTTPException

from compliance_agent.api.dependencies import (
    get_alert_repo,
    get_audit_service,
    get_pipeline_service,
)
from compliance_agent.api.schemas.alert_schemas import (
    AlertStatusResponse,
    AuditEventOut,
    AuditTrailResponse,
    InvestigateRequest,
    InvestigateResponse,
)
from compliance_agent.repositories.interfaces import IAlertRepository
from compliance_agent.services.audit_service import AuditService
from compliance_agent.services.pipeline_service import PipelineService

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


@router.post("/{alert_id}/investigate", response_model=InvestigateResponse)
async def investigate_alert(
    alert_id: str,
    _request: InvestigateRequest = InvestigateRequest(),
    pipeline_service: PipelineService = Depends(get_pipeline_service),
) -> InvestigateResponse:
    try:
        final_state = await pipeline_service.process_alert(alert_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    risk_data = final_state.get("risk_analysis", {})
    decision_data = final_state.get("decision", {})

    return InvestigateResponse(
        alert_id=alert_id,
        status=decision_data.get("decision_type", "UNKNOWN"),
        risk_analysis=risk_data or None,
        decision=decision_data or None,
        langfuse_trace_id=final_state.get("langfuse_trace_id", ""),
    )


@router.get("/{alert_id}/status", response_model=AlertStatusResponse)
async def get_alert_status(
    alert_id: str,
    alert_repo: IAlertRepository = Depends(get_alert_repo),
) -> AlertStatusResponse:
    try:
        alert = await alert_repo.get_by_id(alert_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Alert not found") from exc

    return AlertStatusResponse(
        alert_id=str(alert.id),
        external_alert_id=alert.external_alert_id,
        status=alert.status,
        customer_id=alert.customer_id,
        is_pep=alert.is_pep,
        amount=float(alert.amount),
        currency=alert.currency,
        created_at=alert.created_at,
    )


@router.get("/{alert_id}/audit-trail", response_model=AuditTrailResponse)
async def get_audit_trail(
    alert_id: str,
    audit_service: AuditService = Depends(get_audit_service),
) -> AuditTrailResponse:
    events = await audit_service.get_audit_trail(alert_id)
    return AuditTrailResponse(
        alert_id=alert_id,
        events=[
            AuditEventOut(
                event_type=e.event_type,
                agent_name=e.agent_name,
                duration_ms=e.duration_ms,
                token_cost_usd=float(e.token_cost_usd),
                langfuse_trace_id=e.langfuse_trace_id,
                created_at=e.created_at,
            )
            for e in events
        ],
    )
