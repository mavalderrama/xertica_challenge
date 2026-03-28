import os
from functools import lru_cache
from typing import Any


@lru_cache
def get_llm() -> Any:
    provider = os.environ.get("LLM_PROVIDER", "openai").lower()

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            api_key=os.environ.get("OPENAI_API_KEY", ""),
            temperature=0,
        )

    # provider == "vertexai"
    from langchain_google_vertexai import ChatVertexAI

    return ChatVertexAI(
        model_name=os.environ.get("GEMINI_MODEL", "gemini-2.0-flash-001"),
        project=os.environ.get("GCP_PROJECT_ID", ""),
        location=os.environ.get("GCP_LOCATION", "us-central1"),
        temperature=0,
    )


@lru_cache
def get_tracer():
    from compliance_agent.observability import LangfuseTracer

    return LangfuseTracer()


@lru_cache
def get_bq_tool():
    use_mock = os.environ.get("USE_MOCK_BQ", "true").lower() == "true"
    if use_mock:
        from compliance_agent.tools import MockBigQueryTool

        return MockBigQueryTool()
    from compliance_agent.tools import BigQueryTool

    return BigQueryTool()


@lru_cache
def get_gcs_tool():
    use_mock = os.environ.get("USE_MOCK_GCS", "true").lower() == "true"
    if use_mock:
        from compliance_agent.tools import MockGCSTool

        return MockGCSTool()
    from compliance_agent.tools import GCSTool

    return GCSTool()


@lru_cache
def get_alert_repo():
    from compliance_agent.repositories import AlertRepository

    return AlertRepository()


@lru_cache
def get_investigation_repo():
    from compliance_agent.repositories import InvestigationRepository

    return InvestigationRepository()


@lru_cache
def get_decision_repo():
    from compliance_agent.repositories import DecisionRepository

    return DecisionRepository()


@lru_cache
def get_audit_log_repo():
    from compliance_agent.repositories import AuditLogRepository

    return AuditLogRepository()


@lru_cache
def get_risk_analysis_repo():
    from compliance_agent.repositories import RiskAnalysisRepository

    return RiskAnalysisRepository()


@lru_cache
def get_retriever():
    from compliance_agent.rag import (
        GraphRetriever,
        HFEmbedder,
        HybridRetriever,
        SparseVectorRetriever,
        VectorStoreRetriever,
    )

    embedder = HFEmbedder()
    return HybridRetriever(
        vector_retriever=VectorStoreRetriever(embedder),
        sparse_retriever=SparseVectorRetriever(),
        graph_retriever=GraphRetriever(embedder),
    )


def get_audit_service():
    from compliance_agent.services import AuditService

    return AuditService(get_audit_log_repo())


def get_pipeline_service():
    from compliance_agent.agents import (
        DecisionAgent,
        InvestigadorAgent,
        RiskAnalyzerAgent,
    )
    from compliance_agent.graph import build_compliance_pipeline
    from compliance_agent.services import PipelineService

    investigador = InvestigadorAgent(
        llm=get_llm(),
        tracer=get_tracer(),
        bq_tool=get_bq_tool(),
        gcs_tool=get_gcs_tool(),
        investigation_repo=get_investigation_repo(),
        alert_repo=get_alert_repo(),
    )
    risk_analyzer = RiskAnalyzerAgent(
        llm=get_llm(),
        tracer=get_tracer(),
        risk_analysis_repo=get_risk_analysis_repo(),
        investigation_repo=get_investigation_repo(),
    )
    decision_agent = DecisionAgent(
        llm=get_llm(),
        tracer=get_tracer(),
        retriever=get_retriever(),
        decision_repo=get_decision_repo(),
        risk_analysis_repo=get_risk_analysis_repo(),
        audit_log_repo=get_audit_log_repo(),
    )
    compiled = build_compliance_pipeline(investigador, risk_analyzer, decision_agent)
    return PipelineService(compiled_graph=compiled, alert_repo=get_alert_repo())
