"""Finite, fail-closed Week 1 case-analysis orchestration boundary."""

from __future__ import annotations

import uuid
from enum import StrEnum
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, ConfigDict, Field


class CaseAnalysisStatus(StrEnum):
    """Internal execution result for the unavailable Week 1 case-analysis path."""

    CASE_ANALYSIS_NOT_READY = "CASE_ANALYSIS_NOT_READY"


class CaseAnalysisResult(BaseModel):
    """Typed fail-closed result; it deliberately carries no legal conclusion."""

    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1)
    status: CaseAnalysisStatus
    message: str = Field(min_length=1, max_length=500)


class CaseAnalysisState(TypedDict):
    """Minimum state needed for the Week 1 terminal topology."""

    request_id: str
    question: str
    status: str
    message: str


_NOT_READY_MESSAGE = (
    "Chức năng phân tích vụ việc chưa sẵn sàng; hệ thống không đưa ra kết luận pháp lý."
)


async def case_analysis_not_ready(state: CaseAnalysisState) -> dict[str, str]:
    """Terminate the unimplemented path without calling any capability."""

    del state
    return {
        "status": CaseAnalysisStatus.CASE_ANALYSIS_NOT_READY.value,
        "message": _NOT_READY_MESSAGE,
    }


def build_case_graph() -> StateGraph[CaseAnalysisState]:
    """Create the fixed ``START -> not_ready -> END`` topology."""

    graph = StateGraph(CaseAnalysisState)
    graph.add_node("case_analysis_not_ready", case_analysis_not_ready)
    graph.add_edge(START, "case_analysis_not_ready")
    graph.add_edge("case_analysis_not_ready", END)
    return graph


class CaseGraph:
    """Week 1 orchestration shell reserved for later case-analysis intake wiring."""

    def __init__(self) -> None:
        self.graph = build_case_graph().compile()

    async def run(self, question: str) -> CaseAnalysisResult:
        request_id = str(uuid.uuid4())
        completed = await self.graph.ainvoke(
            {
                "request_id": request_id,
                "question": question,
                "status": "",
                "message": "",
            }
        )
        return CaseAnalysisResult(
            request_id=request_id,
            status=CaseAnalysisStatus(completed["status"]),
            message=completed["message"],
        )
