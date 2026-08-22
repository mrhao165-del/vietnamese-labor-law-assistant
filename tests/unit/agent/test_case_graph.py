from __future__ import annotations

import inspect

import pytest

from vietnamese_labor_law_assistant.agent.case_graph import (
    CaseAnalysisResult,
    CaseAnalysisStatus,
    CaseGraph,
)


@pytest.mark.asyncio
async def test_case_graph_terminates_with_a_typed_fail_closed_result() -> None:
    result = await CaseGraph().run("Tôi có tranh chấp với công ty.")
    assert isinstance(result, CaseAnalysisResult)
    assert result.status is CaseAnalysisStatus.CASE_ANALYSIS_NOT_READY
    assert result.request_id
    assert "không đưa ra kết luận pháp lý" in result.message
    assert not hasattr(result, "answer")


def test_case_graph_topology_is_finite_and_has_no_loop() -> None:
    graph = CaseGraph().graph.get_graph()
    edges = {(edge.source, edge.target) for edge in graph.edges}
    assert edges == {
        ("__start__", "case_analysis_not_ready"),
        ("case_analysis_not_ready", "__end__"),
    }
    assert all(source != target for source, target in edges)


def test_week1_case_graph_has_no_capability_or_domain_dependencies() -> None:
    module = inspect.getmodule(CaseGraph)
    assert module is not None
    source = inspect.getsource(module)
    for prohibited in (
        "AgentService",
        "Mcp",
        "retrieval",
        "calculator",
        "CaseFact",
        "IssueRegistry",
        "DecisionRule",
    ):
        assert prohibited not in source
