"""Finite LangGraph topology for Week 9; there are deliberately no recursive edges."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from langgraph.graph import END, START, StateGraph

from .models import AgentState

if TYPE_CHECKING:
    from .service import AgentService


def build_agent_graph(service: AgentService) -> StateGraph[AgentState]:
    graph = StateGraph(AgentState)
    graph.add_node("validate_input", service.validate_input)
    graph.add_node("classify_intent", service.classify_intent)
    graph.add_node("retrieval_only", service.retrieval_only)
    graph.add_node("calculator_only", service.calculator_only)
    graph.add_node("combined_calculator", service.calculator_only)
    graph.add_node("combined_retrieval", service.retrieval_only)
    graph.add_node("build_refusal", service.build_refusal)
    graph.add_node("generate_answer", service.generate_answer)
    graph.add_node("verify_workflow_output", service.verify_workflow_output)
    graph.add_node("finalize", service.finalize)
    graph.add_edge(START, "validate_input")
    graph.add_edge("validate_input", "classify_intent")
    graph.add_conditional_edges(
        "classify_intent",
        service.route_after_classification,
        {
            "retrieval": "retrieval_only",
            "calculator": "calculator_only",
            "combined": "combined_calculator",
            "out_of_scope": "build_refusal",
            "verify": "verify_workflow_output",
        },
    )
    graph.add_edge("retrieval_only", "generate_answer")
    graph.add_edge("calculator_only", "generate_answer")
    graph.add_edge("combined_calculator", "combined_retrieval")
    graph.add_edge("combined_retrieval", "generate_answer")
    graph.add_edge("build_refusal", "verify_workflow_output")
    graph.add_edge("generate_answer", "verify_workflow_output")
    graph.add_edge("verify_workflow_output", "finalize")
    graph.add_edge("finalize", END)
    return graph


RouteName = Literal["retrieval", "calculator", "combined", "out_of_scope", "verify"]
