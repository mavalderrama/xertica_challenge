from unittest.mock import AsyncMock, MagicMock, patch

import pytest


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
    from compliance_agent.services import PipelineService
    from compliance_agent.tools import MockBigQueryTool, MockGCSTool

    # Use real repos against test DB; mock LLM and external services.
    alert_repo = AlertRepository()
    investigation_repo = InvestigationRepository()
    risk_analysis_repo = RiskAnalysisRepository()
    decision_repo = DecisionRepository()
    audit_log_repo = AuditLogRepository()

    mock_llm = MagicMock()
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

    # Patch RunnableSequence.ainvoke so the LangChain chain (prompt | llm | parser) returns
    # our mock dicts without hitting a real LLM.  Side-effect order matches pipeline order:
    # first call is RiskAnalyzer chain, second call is DecisionAgent chain.
    with patch(
        "langchain_core.runnables.base.RunnableSequence.ainvoke",
        new_callable=AsyncMock,
    ) as mock_ainvoke:
        mock_ainvoke.side_effect = [risk_chain_output, decision_chain_output]

        investigador = InvestigadorAgent(
            llm=mock_llm,
            tracer=mock_tracer,
            bq_tool=MockBigQueryTool(),
            gcs_tool=MockGCSTool(),
            investigation_repo=investigation_repo,
            alert_repo=alert_repo,
        )
        risk_analyzer = RiskAnalyzerAgent(
            llm=mock_llm,
            tracer=mock_tracer,
            risk_analysis_repo=risk_analysis_repo,
            investigation_repo=investigation_repo,
        )
        decision_agent = DecisionAgent(
            llm=mock_llm,
            tracer=mock_tracer,
            retriever=mock_retriever,
            decision_repo=decision_repo,
            risk_analysis_repo=risk_analysis_repo,
            audit_log_repo=audit_log_repo,
        )

        compiled = build_compliance_pipeline(investigador, risk_analyzer, decision_agent)
        service = PipelineService(compiled_graph=compiled, alert_repo=alert_repo)
        final_state = await service.process_alert(str(sample_alert.id))

    assert "investigation" in final_state
    assert "risk_analysis" in final_state
    assert "decision" in final_state
    assert final_state["decision"]["decision_type"] in ("ESCALATE", "DISMISS", "REQUEST_INFO")


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
    from compliance_agent.services import PipelineService
    from compliance_agent.tools import MockBigQueryTool, MockGCSTool

    alert_repo = AlertRepository()
    investigation_repo = InvestigationRepository()
    risk_analysis_repo = RiskAnalysisRepository()
    decision_repo = DecisionRepository()
    audit_log_repo = AuditLogRepository()

    mock_llm = MagicMock()
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
    with patch(
        "langchain_core.runnables.base.RunnableSequence.ainvoke",
        new_callable=AsyncMock,
    ) as mock_ainvoke:
        mock_ainvoke.return_value = risk_chain_output

        investigador = InvestigadorAgent(
            llm=mock_llm,
            tracer=mock_tracer,
            bq_tool=MockBigQueryTool(),
            gcs_tool=MockGCSTool(),
            investigation_repo=investigation_repo,
            alert_repo=alert_repo,
        )
        risk_analyzer = RiskAnalyzerAgent(
            llm=mock_llm,
            tracer=mock_tracer,
            risk_analysis_repo=risk_analysis_repo,
            investigation_repo=investigation_repo,
        )
        decision_agent = DecisionAgent(
            llm=mock_llm,
            tracer=mock_tracer,
            retriever=mock_retriever,
            decision_repo=decision_repo,
            risk_analysis_repo=risk_analysis_repo,
            audit_log_repo=audit_log_repo,
        )

        compiled = build_compliance_pipeline(investigador, risk_analyzer, decision_agent)
        service = PipelineService(compiled_graph=compiled, alert_repo=alert_repo)
        final_state = await service.process_alert(str(sample_pep_alert.id))

    assert final_state["decision"]["decision_type"] == "ESCALATE"
    assert final_state["decision"]["is_pep_override_applied"] is True
    # RAG retriever must NOT be called for PEP — hard rule bypasses LLM entirely.
    mock_retriever.retrieve.assert_not_called()
