from langgraph.graph import END, START, StateGraph

from compliance_agent.agents.decision_agent import DecisionAgent
from compliance_agent.agents.investigador import InvestigadorAgent
from compliance_agent.agents.risk_analyzer import RiskAnalyzerAgent
from compliance_agent.graph.state import PipelineState


def build_compliance_pipeline(
    investigador: InvestigadorAgent,
    risk_analyzer: RiskAnalyzerAgent,
    decision_agent: DecisionAgent,
):
    """
    Builds the LangGraph compliance pipeline.
    Topology: START → investigador → risk_analyzer → decision → END
    """
    graph = StateGraph(PipelineState)

    graph.add_node("investigador", investigador.run)  # type: ignore
    graph.add_node("risk_analyzer", risk_analyzer.run)  # type: ignore
    graph.add_node("decision", decision_agent.run)  # type: ignore

    graph.add_edge(START, "investigador")
    graph.add_edge("investigador", "risk_analyzer")
    graph.add_edge("risk_analyzer", "decision")
    graph.add_edge("decision", END)

    return graph.compile()
