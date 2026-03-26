from decimal import Decimal
from unittest.mock import MagicMock


def test_audit_service_log_event():
    from compliance_agent.services.audit_service import AuditService

    repo = MagicMock()
    mock_log = MagicMock()
    repo.create.return_value = mock_log

    service = AuditService(audit_log_repo=repo)
    service.log_agent_event(
        alert_id="alert-1",
        event_type="INVESTIGATION",
        agent_name="InvestigadorAgent",
        input_snapshot={"customer_id": "C1"},
        output_snapshot={"tx_count": 5},
        langfuse_trace_id="trace-xyz",
        duration_ms=1234,
        token_cost_usd=0.001,
    )

    repo.create.assert_called_once()
    call_kwargs = repo.create.call_args.kwargs
    assert call_kwargs["alert_id"] == "alert-1"
    assert call_kwargs["event_type"] == "INVESTIGATION"
    assert call_kwargs["agent_name"] == "InvestigadorAgent"
    assert call_kwargs["duration_ms"] == 1234
    assert call_kwargs["token_cost_usd"] == Decimal("0.001")


def test_audit_service_get_trail():
    from compliance_agent.services.audit_service import AuditService

    repo = MagicMock()
    repo.get_by_alert_id.return_value = [MagicMock(), MagicMock()]

    service = AuditService(audit_log_repo=repo)
    events = service.get_audit_trail("alert-1")

    assert len(events) == 2
    repo.get_by_alert_id.assert_called_once_with("alert-1")


def test_audit_service_zero_cost():
    from compliance_agent.services.audit_service import AuditService

    repo = MagicMock()
    service = AuditService(audit_log_repo=repo)
    service.log_agent_event(
        alert_id="a",
        event_type="TEST",
        agent_name="test",
        input_snapshot={},
        output_snapshot={},
    )
    call_kwargs = repo.create.call_args.kwargs
    assert call_kwargs["token_cost_usd"] == Decimal("0.0")
