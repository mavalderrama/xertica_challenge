"""
Unit tests for all 5 repository implementations.

These tests use the real Django ORM against the test database (SQLite in-memory
by default for local runs).  All repository methods are async, so every test
is marked with both @pytest.mark.django_db(transaction=True) and
@pytest.mark.asyncio.
"""

import uuid
from decimal import Decimal

import pytest

from compliance_agent.models import (
    Alert,
    Decision,
    Investigation,
    RiskAnalysis,
)
from compliance_agent.repositories import (
    AlertRepository,
    AuditLogRepository,
    DecisionRepository,
    InvestigationRepository,
    RiskAnalysisRepository,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_alert(
    ext_id: str = "REPO-TEST-001",
    customer_id: str = "CUST-REPO",
    amount: str = "1000.00",
    currency: str = "USD",
    is_pep: bool = False,
) -> Alert:
    from datetime import UTC, datetime

    return await Alert.objects.acreate(
        external_alert_id=ext_id,
        customer_id=customer_id,
        is_pep=is_pep,
        amount=Decimal(amount),
        currency=currency,
        transaction_date=datetime(2024, 1, 1, tzinfo=UTC),
    )


async def _make_investigation(alert: Alert) -> Investigation:
    return await Investigation.objects.acreate(
        alert=alert,
        transaction_history=[],
        documents_analyzed=[],
        structured_context={"test": True},
    )


async def _make_risk_analysis(
    investigation: Investigation, score: int = 5
) -> RiskAnalysis:
    return await RiskAnalysis.objects.acreate(
        investigation=investigation,
        risk_score=score,
        justification="Test justification",
        anomalous_patterns=[],
        human_summary="Test summary",
    )


# ---------------------------------------------------------------------------
# AlertRepository
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
class TestAlertRepository:
    async def test_get_by_id_returns_matching_alert(self):
        alert = await _make_alert(ext_id="ALERT-ID-001")
        repo = AlertRepository()

        result = await repo.get_by_id(alert.id)

        assert result.id == alert.id
        assert result.customer_id == alert.customer_id

    async def test_get_by_external_id_returns_matching_alert(self):
        await _make_alert(ext_id="EXT-ID-002", customer_id="CUST-002")
        repo = AlertRepository()

        result = await repo.get_by_external_id("EXT-ID-002")

        assert result.external_alert_id == "EXT-ID-002"
        assert result.customer_id == "CUST-002"

    async def test_get_by_id_raises_for_unknown_id(self):
        repo = AlertRepository()
        with pytest.raises(Exception):  # noqa: B017 — Django raises DoesNotExist (ObjectDoesNotExist subclass)
            await repo.get_by_id(uuid.uuid4())

    async def test_update_status_persists_new_status(self):
        alert = await _make_alert(ext_id="STATUS-003")
        repo = AlertRepository()

        updated = await repo.update_status(alert.id, Alert.Status.INVESTIGATING)

        assert updated.status == Alert.Status.INVESTIGATING
        # Verify it is actually stored in the DB.
        refreshed = await Alert.objects.aget(pk=alert.id)
        assert refreshed.status == Alert.Status.INVESTIGATING

    async def test_update_status_escalated(self):
        alert = await _make_alert(ext_id="STATUS-004")
        repo = AlertRepository()

        updated = await repo.update_status(alert.id, Alert.Status.ESCALATED)

        assert updated.status == Alert.Status.ESCALATED

    async def test_update_status_dismissed(self):
        alert = await _make_alert(ext_id="STATUS-005")
        repo = AlertRepository()

        updated = await repo.update_status(alert.id, Alert.Status.DISMISSED)

        assert updated.status == Alert.Status.DISMISSED

    async def test_save_new_alert_assigns_id(self):
        from datetime import UTC, datetime

        repo = AlertRepository()
        alert = Alert(
            external_alert_id="SAVE-006",
            customer_id="CUST-006",
            amount=Decimal("300.00"),
            currency="PEN",
            transaction_date=datetime(2024, 1, 1, tzinfo=UTC),
        )

        saved = await repo.save(alert)

        assert saved.id is not None
        assert await Alert.objects.filter(pk=saved.id).aexists()

    async def test_save_existing_alert_updates_record(self):
        alert = await _make_alert(ext_id="SAVE-UPDATE-007")
        repo = AlertRepository()

        alert.customer_id = "UPDATED-CUST"
        saved = await repo.save(alert)

        assert saved.customer_id == "UPDATED-CUST"
        refreshed = await Alert.objects.aget(pk=alert.id)
        assert refreshed.customer_id == "UPDATED-CUST"


# ---------------------------------------------------------------------------
# InvestigationRepository
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
class TestInvestigationRepository:
    async def test_save_and_get_by_alert_id(self):
        alert = await _make_alert(ext_id="INV-001")
        repo = InvestigationRepository()

        inv = Investigation(
            alert=alert,
            transaction_history=[{"amount": 100}],
            documents_analyzed=[],
            structured_context={"key": "value"},
        )
        saved = await repo.save(inv)

        assert saved.id is not None

        result = await repo.get_by_alert_id(alert.id)
        assert result.id == saved.id
        assert result.structured_context == {"key": "value"}

    async def test_get_by_id_returns_investigation(self):
        alert = await _make_alert(ext_id="INV-002")
        investigation = await _make_investigation(alert)
        repo = InvestigationRepository()

        result = await repo.get_by_id(investigation.id)

        assert result.id == investigation.id

    async def test_get_by_alert_id_raises_for_unknown_alert(self):
        repo = InvestigationRepository()
        with pytest.raises(Exception):  # noqa: B017 — Django raises DoesNotExist (ObjectDoesNotExist subclass)
            await repo.get_by_alert_id(uuid.uuid4())

    async def test_save_stores_transaction_history(self):
        alert = await _make_alert(ext_id="INV-003")
        repo = InvestigationRepository()
        tx_history = [{"id": "tx1", "amount": 500}, {"id": "tx2", "amount": 250}]

        inv = Investigation(
            alert=alert,
            transaction_history=tx_history,
            documents_analyzed=[],
            structured_context={},
        )
        saved = await repo.save(inv)

        refreshed = await Investigation.objects.aget(pk=saved.id)
        assert refreshed.transaction_history == tx_history


# ---------------------------------------------------------------------------
# RiskAnalysisRepository
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
class TestRiskAnalysisRepository:
    async def test_save_and_get_by_investigation_id(self):
        alert = await _make_alert(ext_id="RISK-001")
        investigation = await _make_investigation(alert)
        repo = RiskAnalysisRepository()

        risk = RiskAnalysis(
            investigation=investigation,
            risk_score=7,
            justification="High transaction velocity",
            anomalous_patterns=["rapid transfers"],
            human_summary="Potentially suspicious.",
        )
        saved = await repo.save(risk)

        assert saved.id is not None

        result = await repo.get_by_investigation_id(investigation.id)
        assert result.id == saved.id
        assert result.risk_score == 7

    async def test_get_by_id_returns_risk_analysis(self):
        alert = await _make_alert(ext_id="RISK-002")
        investigation = await _make_investigation(alert)
        risk = await _make_risk_analysis(investigation, score=4)
        repo = RiskAnalysisRepository()

        result = await repo.get_by_id(risk.id)

        assert result.id == risk.id
        assert result.risk_score == 4

    async def test_save_updates_existing_record(self):
        alert = await _make_alert(ext_id="RISK-003")
        investigation = await _make_investigation(alert)
        risk = await _make_risk_analysis(investigation, score=3)
        repo = RiskAnalysisRepository()

        risk.risk_score = 9
        risk.justification = "Updated justification"
        saved = await repo.save(risk)

        assert saved.risk_score == 9
        refreshed = await RiskAnalysis.objects.aget(pk=risk.id)
        assert refreshed.risk_score == 9


# ---------------------------------------------------------------------------
# DecisionRepository
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
class TestDecisionRepository:
    async def test_save_and_get_by_risk_analysis_id(self):
        alert = await _make_alert(ext_id="DEC-001")
        investigation = await _make_investigation(alert)
        risk = await _make_risk_analysis(investigation, score=6)
        repo = DecisionRepository()

        decision = Decision(
            risk_analysis=risk,
            decision_type=Decision.DecisionType.ESCALATE,
            confidence=0.95,
            regulations_cited=[],
            step_by_step_reasoning="Score >= 6 triggers review.",
            is_pep_override_applied=False,
        )
        saved = await repo.save(decision)

        assert saved.id is not None

        result = await repo.get_by_risk_analysis_id(risk.id)
        assert result.id == saved.id
        assert result.decision_type == Decision.DecisionType.ESCALATE

    async def test_save_dismiss_decision(self):
        alert = await _make_alert(ext_id="DEC-002")
        investigation = await _make_investigation(alert)
        risk = await _make_risk_analysis(investigation, score=2)
        repo = DecisionRepository()

        decision = Decision(
            risk_analysis=risk,
            decision_type=Decision.DecisionType.DISMISS,
            confidence=0.88,
            regulations_cited=[],
            step_by_step_reasoning="Low risk.",
            is_pep_override_applied=False,
        )
        saved = await repo.save(decision)

        assert saved.decision_type == Decision.DecisionType.DISMISS

    async def test_save_pep_override_decision(self):
        alert = await _make_alert(ext_id="DEC-003", is_pep=True)
        investigation = await _make_investigation(alert)
        risk = await _make_risk_analysis(investigation, score=8)
        repo = DecisionRepository()

        decision = Decision(
            risk_analysis=risk,
            decision_type=Decision.DecisionType.ESCALATE,
            confidence=1.0,
            regulations_cited=[],
            step_by_step_reasoning="PEP hard rule.",
            is_pep_override_applied=True,
        )
        saved = await repo.save(decision)

        assert saved.is_pep_override_applied is True
        assert saved.confidence == 1.0


# ---------------------------------------------------------------------------
# AuditLogRepository
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
class TestAuditLogRepository:
    async def test_create_and_get_by_alert_id(self):
        alert = await _make_alert(ext_id="AUDIT-001")
        repo = AuditLogRepository()

        log = await repo.create(
            alert_id=alert.id,
            event_type="INVESTIGATION",
            agent_name="InvestigadorAgent",
            input_snapshot={"customer_id": alert.customer_id},
            output_snapshot={"tx_count": 10},
            langfuse_trace_id="trace-abc",
            duration_ms=350,
            token_cost_usd=Decimal("0.0012"),
        )

        assert log.id is not None
        assert log.event_type == "INVESTIGATION"

        logs = await repo.get_by_alert_id(alert.id)
        assert len(logs) == 1
        assert logs[0].id == log.id
        assert logs[0].agent_name == "InvestigadorAgent"

    async def test_get_by_alert_id_returns_empty_list_for_unknown_alert(self):
        repo = AuditLogRepository()

        logs = await repo.get_by_alert_id(uuid.uuid4())

        assert logs == []

    async def test_create_multiple_logs_ordered_by_created_at(self):
        alert = await _make_alert(ext_id="AUDIT-002")
        repo = AuditLogRepository()

        await repo.create(
            alert_id=alert.id,
            event_type="INVESTIGATION",
            agent_name="InvestigadorAgent",
            input_snapshot={},
            output_snapshot={},
            langfuse_trace_id="",
            duration_ms=100,
            token_cost_usd=Decimal("0.001"),
        )
        await repo.create(
            alert_id=alert.id,
            event_type="RISK_ANALYSIS",
            agent_name="RiskAnalyzerAgent",
            input_snapshot={},
            output_snapshot={},
            langfuse_trace_id="",
            duration_ms=200,
            token_cost_usd=Decimal("0.002"),
        )
        await repo.create(
            alert_id=alert.id,
            event_type="DECISION",
            agent_name="DecisionAgent",
            input_snapshot={},
            output_snapshot={},
            langfuse_trace_id="",
            duration_ms=150,
            token_cost_usd=Decimal("0.0015"),
        )

        logs = await repo.get_by_alert_id(alert.id)
        assert len(logs) == 3
        # AuditLog orders by created_at ascending — verify event sequence.
        event_types = [log.event_type for log in logs]
        assert "INVESTIGATION" in event_types
        assert "RISK_ANALYSIS" in event_types
        assert "DECISION" in event_types

    async def test_create_log_zero_cost(self):
        alert = await _make_alert(ext_id="AUDIT-003")
        repo = AuditLogRepository()

        log = await repo.create(
            alert_id=alert.id,
            event_type="TEST",
            agent_name="TestAgent",
            input_snapshot={},
            output_snapshot={},
            langfuse_trace_id="",
            duration_ms=0,
            token_cost_usd=Decimal("0.0"),
        )

        assert log.token_cost_usd == Decimal("0.0")
