import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_full_pipeline_non_pep(sample_alert):
    """Full pipeline for a non-PEP alert produces investigation, risk_analysis, and decision."""
    from compliance_agent.agents import (
        DecisionAgent,
        InvestigadorAgent,
        RiskAnalyzerAgent,
    )
    from compliance_agent.graph import build_compliance_pipeline
    from compliance_agent.repositories import (
        AlertRepository,
        AuditLogRepository,
        DecisionRepository,
        InvestigationRepository,
        RiskAnalysisRepository,
    )
    from compliance_agent.services import AuditService, PipelineService
    from compliance_agent.tools import MockBigQueryTool, MockGCSTool

    # Use real repos against test DB; mock LLM and external services.
    alert_repo = AlertRepository()
    investigation_repo = InvestigationRepository()
    risk_analysis_repo = RiskAnalysisRepository()
    decision_repo = DecisionRepository()
    audit_service = AuditService(AuditLogRepository())

    mock_llm = MagicMock()
    mock_llm.model_name = "test-llm"
    mock_tracer = MagicMock()
    mock_retriever = MagicMock()
    mock_retriever.retrieve = AsyncMock(return_value=[])

    risk_chain_output = {
        "risk_score": 3,
        "justification": "Low risk — normal transaction volume.",
        "anomalous_patterns": [],
        "human_summary": "All activity appears normal.",
    }
    decision_chain_output = {
        "decision_type": "DISMISS",
        "confidence": 0.9,
        "regulations_cited": [],
        "step_by_step_reasoning": "Step 1: risk score 3/10. Step 2: no anomalies. Step 3: DISMISS.",
    }

    # Patch RunnableSequence.ainvoke so the LangChain chain (prompt | llm) returns
    # an AIMessage with JSON content and usage_metadata. Side-effect order matches
    # pipeline order: first call is RiskAnalyzer chain, second call is DecisionAgent chain.
    risk_message = AIMessage(
        content=json.dumps(risk_chain_output),
        usage_metadata={"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
    )
    decision_message = AIMessage(
        content=json.dumps(decision_chain_output),
        usage_metadata={"input_tokens": 120, "output_tokens": 60, "total_tokens": 180},
    )
    with patch(
        "langchain_core.runnables.base.RunnableSequence.ainvoke",
        new_callable=AsyncMock,
    ) as mock_ainvoke:
        mock_ainvoke.side_effect = [risk_message, decision_message]

        investigador = InvestigadorAgent(
            llm=mock_llm,
            tracer=mock_tracer,
            bq_tool=MockBigQueryTool(),
            gcs_tool=MockGCSTool(),
            investigation_repo=investigation_repo,
            alert_repo=alert_repo,
            audit_service=audit_service,
        )
        risk_analyzer = RiskAnalyzerAgent(
            llm=mock_llm,
            tracer=mock_tracer,
            risk_analysis_repo=risk_analysis_repo,
            investigation_repo=investigation_repo,
            audit_service=audit_service,
        )
        decision_agent = DecisionAgent(
            llm=mock_llm,
            tracer=mock_tracer,
            retriever=mock_retriever,
            decision_repo=decision_repo,
            risk_analysis_repo=risk_analysis_repo,
            audit_service=audit_service,
        )

        compiled = build_compliance_pipeline(
            investigador, risk_analyzer, decision_agent
        )
        service = PipelineService(compiled_graph=compiled, alert_repo=alert_repo)
        final_state = await service.process_alert(str(sample_alert.id))

    assert "investigation" in final_state
    assert "risk_analysis" in final_state
    assert "decision" in final_state
    assert final_state["decision"]["decision_type"] in (
        "ESCALATE",
        "DISMISS",
        "REQUEST_INFO",
    )


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_full_pipeline_pep_always_escalates(sample_pep_alert):
    """PEP alert is always escalated; LLM decision chain is never invoked."""
    from compliance_agent.agents import (
        DecisionAgent,
        InvestigadorAgent,
        RiskAnalyzerAgent,
    )
    from compliance_agent.graph import build_compliance_pipeline
    from compliance_agent.repositories import (
        AlertRepository,
        AuditLogRepository,
        DecisionRepository,
        InvestigationRepository,
        RiskAnalysisRepository,
    )
    from compliance_agent.services import AuditService, PipelineService
    from compliance_agent.tools import MockBigQueryTool, MockGCSTool

    alert_repo = AlertRepository()
    investigation_repo = InvestigationRepository()
    risk_analysis_repo = RiskAnalysisRepository()
    decision_repo = DecisionRepository()
    audit_service = AuditService(AuditLogRepository())

    mock_llm = MagicMock()
    mock_llm.model_name = "test-llm"
    mock_tracer = MagicMock()
    mock_retriever = MagicMock()
    mock_retriever.retrieve = AsyncMock(return_value=[])

    risk_chain_output = {
        "risk_score": 8,
        "justification": "PEP customer — high inherent risk.",
        "anomalous_patterns": ["PEP"],
        "human_summary": "Politically exposed person requires mandatory escalation.",
    }

    # Only one chain call is expected (RiskAnalyzer); DecisionAgent takes PEP hard-rule
    # path and never calls the LLM chain.
    risk_message = AIMessage(
        content=json.dumps(risk_chain_output),
        usage_metadata={"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
    )
    with patch(
        "langchain_core.runnables.base.RunnableSequence.ainvoke",
        new_callable=AsyncMock,
    ) as mock_ainvoke:
        mock_ainvoke.return_value = risk_message

        investigador = InvestigadorAgent(
            llm=mock_llm,
            tracer=mock_tracer,
            bq_tool=MockBigQueryTool(),
            gcs_tool=MockGCSTool(),
            investigation_repo=investigation_repo,
            alert_repo=alert_repo,
            audit_service=audit_service,
        )
        risk_analyzer = RiskAnalyzerAgent(
            llm=mock_llm,
            tracer=mock_tracer,
            risk_analysis_repo=risk_analysis_repo,
            investigation_repo=investigation_repo,
            audit_service=audit_service,
        )
        decision_agent = DecisionAgent(
            llm=mock_llm,
            tracer=mock_tracer,
            retriever=mock_retriever,
            decision_repo=decision_repo,
            risk_analysis_repo=risk_analysis_repo,
            audit_service=audit_service,
        )

        compiled = build_compliance_pipeline(
            investigador, risk_analyzer, decision_agent
        )
        service = PipelineService(compiled_graph=compiled, alert_repo=alert_repo)
        final_state = await service.process_alert(str(sample_pep_alert.id))

    assert final_state["decision"]["decision_type"] == "ESCALATE"
    assert final_state["decision"]["is_pep_override_applied"] is True
    # RAG retriever must NOT be called for PEP — hard rule bypasses LLM entirely.
    mock_retriever.retrieve.assert_not_called()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_ghost_probe_escalates_on_critical_xgb(ghost_probe_alert):
    """Edge case: xgboost=0.97 must produce ESCALATE even when the transaction amount
    is trivially small ($75 USD). Validates that the ML signal dominates over amount
    heuristics — a dormant-account reactivation probe must not slip through."""
    from compliance_agent.agents import (
        DecisionAgent,
        InvestigadorAgent,
        RiskAnalyzerAgent,
    )
    from compliance_agent.graph import build_compliance_pipeline
    from compliance_agent.repositories import (
        AlertRepository,
        AuditLogRepository,
        DecisionRepository,
        InvestigationRepository,
        RiskAnalysisRepository,
    )
    from compliance_agent.services import AuditService, PipelineService
    from compliance_agent.tools import MockBigQueryTool, MockGCSTool

    alert_repo = AlertRepository()
    investigation_repo = InvestigationRepository()
    risk_analysis_repo = RiskAnalysisRepository()
    decision_repo = DecisionRepository()
    audit_service = AuditService(AuditLogRepository())

    mock_llm = MagicMock()
    mock_llm.model_name = "test-llm"
    mock_tracer = MagicMock()
    mock_retriever = MagicMock()
    mock_retriever.retrieve = AsyncMock(return_value=[])

    # xgboost_score=0.97 maps to CRITICAL band — risk score must reflect this.
    risk_chain_output = {
        "risk_score": 9,
        "justification": "XGBoost score 0.97 (CRITICAL band) — dormant account reactivation with burst micro-transfer pattern.",
        "anomalous_patterns": [
            "ANOMALY_SCORE_CRITICAL",
            "dormant_reactivation",
            "micro_burst",
        ],
        "human_summary": "Critical ML anomaly score despite small USD amount. Pattern consistent with account probing.",
    }
    decision_chain_output = {
        "decision_type": "ESCALATE",
        "confidence": 0.95,
        "regulations_cited": [],
        "step_by_step_reasoning": (
            "Step 1: XGBoost score 0.97 places this in the CRITICAL calibration band. "
            "Step 2: Amount $75 USD is low but irrelevant — XGBoost captures behavioural patterns not visible in raw amount. "
            "Step 3: Dormant account reactivation with burst micro-transfer matches money-mule probe pattern. "
            "Step 4: ESCALATE."
        ),
    }

    risk_message = AIMessage(
        content=json.dumps(risk_chain_output),
        usage_metadata={"input_tokens": 110, "output_tokens": 55, "total_tokens": 165},
    )
    decision_message = AIMessage(
        content=json.dumps(decision_chain_output),
        usage_metadata={"input_tokens": 130, "output_tokens": 65, "total_tokens": 195},
    )

    with patch(
        "langchain_core.runnables.base.RunnableSequence.ainvoke",
        new_callable=AsyncMock,
    ) as mock_ainvoke:
        mock_ainvoke.side_effect = [risk_message, decision_message]

        investigador = InvestigadorAgent(
            llm=mock_llm,
            tracer=mock_tracer,
            bq_tool=MockBigQueryTool(),
            gcs_tool=MockGCSTool(),
            investigation_repo=investigation_repo,
            alert_repo=alert_repo,
            audit_service=audit_service,
        )
        risk_analyzer = RiskAnalyzerAgent(
            llm=mock_llm,
            tracer=mock_tracer,
            risk_analysis_repo=risk_analysis_repo,
            investigation_repo=investigation_repo,
            audit_service=audit_service,
        )
        decision_agent = DecisionAgent(
            llm=mock_llm,
            tracer=mock_tracer,
            retriever=mock_retriever,
            decision_repo=decision_repo,
            risk_analysis_repo=risk_analysis_repo,
            audit_service=audit_service,
        )

        compiled = build_compliance_pipeline(
            investigador, risk_analyzer, decision_agent
        )
        service = PipelineService(compiled_graph=compiled, alert_repo=alert_repo)
        final_state = await service.process_alert(str(ghost_probe_alert.id))

    # Primary assertion: ESCALATE despite the trivially small amount.
    assert final_state["decision"]["decision_type"] == "ESCALATE"
    # PEP hard-rule must NOT have fired — this is a non-PEP escalation.
    assert final_state["decision"].get("is_pep_override_applied") is not True
    # RAG retriever WAS called — non-PEP path goes through the full LLM + RAG decision.
    mock_retriever.retrieve.assert_called()
    # Risk analysis is present and reflects the critical ML signal.
    assert final_state["risk_analysis"]["risk_score"] == 9


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_pep_phantom_escalates_unconditionally(pep_phantom_alert):
    """Edge case: PEP=True with EUR 0.01 and xgboost=0.02. Every financial signal
    (amount, currency, ML score) points to DISMISS. The PEP hard-rule must still
    produce ESCALATE with confidence=1.0 — it is unconditional by design."""
    from compliance_agent.agents import (
        DecisionAgent,
        InvestigadorAgent,
        RiskAnalyzerAgent,
    )
    from compliance_agent.graph import build_compliance_pipeline
    from compliance_agent.repositories import (
        AlertRepository,
        AuditLogRepository,
        DecisionRepository,
        InvestigationRepository,
        RiskAnalysisRepository,
    )
    from compliance_agent.services import AuditService, PipelineService
    from compliance_agent.tools import MockBigQueryTool, MockGCSTool

    alert_repo = AlertRepository()
    investigation_repo = InvestigationRepository()
    risk_analysis_repo = RiskAnalysisRepository()
    decision_repo = DecisionRepository()
    audit_service = AuditService(AuditLogRepository())

    mock_llm = MagicMock()
    mock_llm.model_name = "test-llm"
    mock_tracer = MagicMock()
    mock_retriever = MagicMock()
    mock_retriever.retrieve = AsyncMock(return_value=[])

    # Risk analyzer still runs for PEP alerts (to produce the audit record).
    # Even a low risk score from the LLM must not prevent the PEP hard-rule.
    risk_chain_output = {
        "risk_score": 2,
        "justification": "XGBoost score 0.02 (LOW band). Amount EUR 0.01 is negligible. Routine compliance check.",
        "anomalous_patterns": [],
        "human_summary": "All financial signals indicate low risk. However, customer is PEP.",
    }

    risk_message = AIMessage(
        content=json.dumps(risk_chain_output),
        usage_metadata={"input_tokens": 95, "output_tokens": 45, "total_tokens": 140},
    )

    with patch(
        "langchain_core.runnables.base.RunnableSequence.ainvoke",
        new_callable=AsyncMock,
    ) as mock_ainvoke:
        # Only one chain call expected: RiskAnalyzer. DecisionAgent takes PEP hard-rule
        # path and never reaches the LLM decision chain — regardless of the risk score.
        mock_ainvoke.return_value = risk_message

        investigador = InvestigadorAgent(
            llm=mock_llm,
            tracer=mock_tracer,
            bq_tool=MockBigQueryTool(),
            gcs_tool=MockGCSTool(),
            investigation_repo=investigation_repo,
            alert_repo=alert_repo,
            audit_service=audit_service,
        )
        risk_analyzer = RiskAnalyzerAgent(
            llm=mock_llm,
            tracer=mock_tracer,
            risk_analysis_repo=risk_analysis_repo,
            investigation_repo=investigation_repo,
            audit_service=audit_service,
        )
        decision_agent = DecisionAgent(
            llm=mock_llm,
            tracer=mock_tracer,
            retriever=mock_retriever,
            decision_repo=decision_repo,
            risk_analysis_repo=risk_analysis_repo,
            audit_service=audit_service,
        )

        compiled = build_compliance_pipeline(
            investigador, risk_analyzer, decision_agent
        )
        service = PipelineService(compiled_graph=compiled, alert_repo=alert_repo)
        final_state = await service.process_alert(str(pep_phantom_alert.id))

    # Primary assertion: PEP hard-rule fires unconditionally.
    assert final_state["decision"]["decision_type"] == "ESCALATE"
    assert final_state["decision"]["is_pep_override_applied"] is True
    # Confidence must be 1.0 — deterministic rule, not LLM-estimated.
    assert final_state["decision"]["confidence"] == 1.0
    # RAG retriever must NOT be called — PEP path skips LLM + RAG entirely.
    mock_retriever.retrieve.assert_not_called()
    # Risk score is 2 (low) but the decision is still ESCALATE — that is the point.
    assert final_state["risk_analysis"]["risk_score"] == 2
