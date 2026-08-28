"""Finite v1.1 Case Analysis orchestration over typed domain capabilities."""

from __future__ import annotations

import uuid
from enum import StrEnum
from typing import Literal, Required, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from vietnamese_labor_law_assistant.decision_support.clarification import (
    ClarificationResult,
    TargetedClarificationBuilder,
)
from vietnamese_labor_law_assistant.decision_support.evidence_requests import (
    EvidenceRequestSkeleton,
    EvidenceRequestSkeletonBuilder,
)
from vietnamese_labor_law_assistant.decision_support.intake import (
    CaseIntakeError,
    validate_case_intake_result,
)
from vietnamese_labor_law_assistant.decision_support.issue_registry import (
    ISSUE_REGISTRY,
    IssueRegistry,
)
from vietnamese_labor_law_assistant.decision_support.missing_facts import (
    MissingFactDetector,
    MissingFactResult,
)
from vietnamese_labor_law_assistant.decision_support.models import (
    CaseIntakeInput,
    CaseIntakeResult,
)
from vietnamese_labor_law_assistant.decision_support.protocols import CaseIntakeExtractor
from vietnamese_labor_law_assistant.decision_support.refined_issues import (
    RefinedIssueEvaluator,
    RefinedIssueResult,
)


class CaseAnalysisStatus(StrEnum):
    """Stable terminal outcomes for one bounded Case Analysis request."""

    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"
    EVIDENCE_REQUEST_READY = "EVIDENCE_REQUEST_READY"
    UNSUPPORTED_SCOPE = "UNSUPPORTED_SCOPE"
    CASE_INTAKE_FAILED = "CASE_INTAKE_FAILED"
    CASE_ANALYSIS_FAILED = "CASE_ANALYSIS_FAILED"


class CaseAnalysisErrorCode(StrEnum):
    """Allowlisted errors that may cross the orchestration boundary."""

    CASE_INTAKE_PROVIDER_UNAVAILABLE = "CASE_INTAKE_PROVIDER_UNAVAILABLE"
    CASE_INTAKE_EMPTY_OUTPUT = "CASE_INTAKE_EMPTY_OUTPUT"
    CASE_INTAKE_SOURCE_INVALID = "CASE_INTAKE_SOURCE_INVALID"
    CASE_INTAKE_SCHEMA_INVALID = "CASE_INTAKE_SCHEMA_INVALID"
    CASE_INTAKE_TIMEOUT = "CASE_INTAKE_TIMEOUT"
    CASE_INTAKE_PROVIDER_ERROR = "CASE_INTAKE_PROVIDER_ERROR"
    CASE_DOMAIN_CONTRACT_INVALID = "CASE_DOMAIN_CONTRACT_INVALID"


class CaseAnalysisResult(BaseModel):
    """Typed safe terminal; it deliberately carries no legal conclusion."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id: str = Field(min_length=1)
    status: CaseAnalysisStatus
    message: str = Field(min_length=1, max_length=500)
    error_code: CaseAnalysisErrorCode | None = None
    intake_result: CaseIntakeResult | None = None
    missing_facts: MissingFactResult | None = None
    clarification: ClarificationResult | None = None
    refined_issues: RefinedIssueResult | None = None
    evidence_request: EvidenceRequestSkeleton | None = None

    @model_validator(mode="after")
    def validate_terminal_payload(self) -> CaseAnalysisResult:
        if self.status is CaseAnalysisStatus.CLARIFICATION_REQUIRED:
            if (
                self.intake_result is None
                or self.missing_facts is None
                or self.clarification is None
                or not self.missing_facts.fields_needed
                or not self.clarification.questions
                or self.refined_issues is not None
                or self.evidence_request is not None
                or self.error_code is not None
            ):
                raise ValueError("clarification terminal requires only missing-fact metadata")
            return self

        if self.status is CaseAnalysisStatus.EVIDENCE_REQUEST_READY:
            if (
                self.intake_result is None
                or self.missing_facts is None
                or self.missing_facts.fields_needed
                or self.clarification is not None
                or self.refined_issues is None
                or self.evidence_request is None
                or self.error_code is not None
            ):
                raise ValueError("evidence-request terminal requires complete deterministic state")
            return self

        if self.status is CaseAnalysisStatus.UNSUPPORTED_SCOPE:
            if (
                self.intake_result is None
                or self.intake_result.candidate_issues
                or self.missing_facts is not None
                or self.clarification is not None
                or self.refined_issues is not None
                or self.evidence_request is not None
                or self.error_code is not None
            ):
                raise ValueError("unsupported terminal requires an empty candidate issue set")
            return self

        if self.error_code is None:
            raise ValueError("failure terminal requires a safe error code")
        if self.clarification is not None or self.evidence_request is not None:
            raise ValueError("failure terminal cannot carry downstream output")
        if self.status is CaseAnalysisStatus.CASE_INTAKE_FAILED and any(
            value is not None
            for value in (self.intake_result, self.missing_facts, self.refined_issues)
        ):
            raise ValueError("intake failure cannot carry unvalidated intake state")
        return self


class CaseAnalysisState(TypedDict, total=False):
    """Typed data passed through the finite Case Analysis topology."""

    request_id: Required[str]
    question: Required[str]
    intake_result: CaseIntakeResult
    missing_facts: MissingFactResult
    clarification: ClarificationResult
    refined_issues: RefinedIssueResult
    evidence_request: EvidenceRequestSkeleton
    status: CaseAnalysisStatus
    error_code: CaseAnalysisErrorCode
    message: str


class _CaseAnalysisStateUpdate(TypedDict, total=False):
    intake_result: CaseIntakeResult
    missing_facts: MissingFactResult
    clarification: ClarificationResult
    refined_issues: RefinedIssueResult
    evidence_request: EvidenceRequestSkeleton
    status: CaseAnalysisStatus
    error_code: CaseAnalysisErrorCode
    message: str


_CLARIFICATION_MESSAGE = "Cần bổ sung thông tin trước khi tiếp tục phân tích vụ việc."
_EVIDENCE_READY_MESSAGE = (
    "Đã chuẩn bị yêu cầu bằng chứng ở mức siêu dữ liệu; chưa thực hiện phân tích pháp lý."
)
_UNSUPPORTED_MESSAGE = "Nội dung hiện tại không có vấn đề thuộc phạm vi phân tích được hỗ trợ."
_INTAKE_FAILED_MESSAGE = "Không thể tiếp nhận dữ liệu vụ việc một cách an toàn."
_ANALYSIS_FAILED_MESSAGE = "Không thể tiếp tục phân tích vụ việc một cách an toàn."
_INTAKE_ERROR_CODES = {
    code.value: code
    for code in CaseAnalysisErrorCode
    if code is not CaseAnalysisErrorCode.CASE_DOMAIN_CONTRACT_INVALID
}


class _CaseAnalysisNodes:
    def __init__(
        self,
        case_intake_extractor: CaseIntakeExtractor,
        registry: IssueRegistry,
        missing_fact_detector: MissingFactDetector,
        clarification_builder: TargetedClarificationBuilder,
        refined_issue_evaluator: RefinedIssueEvaluator,
        evidence_request_builder: EvidenceRequestSkeletonBuilder,
    ) -> None:
        self.case_intake_extractor = case_intake_extractor
        self.registry = registry
        self.missing_fact_detector = missing_fact_detector
        self.clarification_builder = clarification_builder
        self.refined_issue_evaluator = refined_issue_evaluator
        self.evidence_request_builder = evidence_request_builder

    async def case_intake(self, state: CaseAnalysisState) -> _CaseAnalysisStateUpdate:
        try:
            case_input = CaseIntakeInput(
                source_text=state["question"].strip(),
                source_ref=f"user_message:{state['request_id']}",
            )
            extracted = await self.case_intake_extractor.extract(case_input)
            payload = {
                field_name: getattr(extracted, field_name)
                for field_name in CaseIntakeResult.model_fields
            }
            intake_result = validate_case_intake_result(
                case_input,
                CaseIntakeResult.model_validate(payload),
            )
        except CaseIntakeError as error:
            return _intake_failure(_safe_intake_error_code(error.reason))
        except ValidationError:
            return _intake_failure(CaseAnalysisErrorCode.CASE_INTAKE_SCHEMA_INVALID)
        except ValueError:
            return _intake_failure(CaseAnalysisErrorCode.CASE_INTAKE_SOURCE_INVALID)
        except Exception:
            return _intake_failure(CaseAnalysisErrorCode.CASE_INTAKE_PROVIDER_ERROR)

        if not intake_result.candidate_issues:
            return {
                "intake_result": intake_result,
                "status": CaseAnalysisStatus.UNSUPPORTED_SCOPE,
                "message": _UNSUPPORTED_MESSAGE,
            }
        return {"intake_result": intake_result}

    def detect_missing_facts(self, state: CaseAnalysisState) -> _CaseAnalysisStateUpdate:
        intake_result = state.get("intake_result")
        if intake_result is None:
            return _analysis_failure()
        try:
            missing_facts = self.missing_fact_detector.detect(
                intake_result.facts,
                intake_result.candidate_issues,
                self.registry,
            )
        except Exception:
            return _analysis_failure()
        return {"missing_facts": missing_facts}

    def build_clarification(self, state: CaseAnalysisState) -> _CaseAnalysisStateUpdate:
        missing_facts = state.get("missing_facts")
        if missing_facts is None:
            return _analysis_failure()
        try:
            clarification = self.clarification_builder.build(missing_facts)
        except Exception:
            return _analysis_failure()
        return {
            "clarification": clarification,
            "status": CaseAnalysisStatus.CLARIFICATION_REQUIRED,
            "message": _CLARIFICATION_MESSAGE,
        }

    def refine_issues(self, state: CaseAnalysisState) -> _CaseAnalysisStateUpdate:
        intake_result = state.get("intake_result")
        missing_facts = state.get("missing_facts")
        if intake_result is None or missing_facts is None:
            return _analysis_failure()
        try:
            refined_issues = self.refined_issue_evaluator.refine(
                intake_result.facts,
                intake_result.candidate_issues,
                missing_facts,
                self.registry,
            )
        except Exception:
            return _analysis_failure()
        return {"refined_issues": refined_issues}

    def build_evidence_request(self, state: CaseAnalysisState) -> _CaseAnalysisStateUpdate:
        refined_issues = state.get("refined_issues")
        if refined_issues is None:
            return _analysis_failure()
        try:
            evidence_request = self.evidence_request_builder.build(
                refined_issues,
                self.registry,
            )
        except Exception:
            return _analysis_failure()
        return {
            "evidence_request": evidence_request,
            "status": CaseAnalysisStatus.EVIDENCE_REQUEST_READY,
            "message": _EVIDENCE_READY_MESSAGE,
        }


def _route_after_intake(
    state: CaseAnalysisState,
) -> Literal["detect_missing_facts", "__end__"]:
    return "__end__" if "status" in state else "detect_missing_facts"


def _route_after_missing_facts(
    state: CaseAnalysisState,
) -> Literal["build_clarification", "refine_issues", "__end__"]:
    if "status" in state:
        return "__end__"
    missing_facts = state.get("missing_facts")
    if missing_facts is None:
        return "__end__"
    if missing_facts.fields_needed:
        return "build_clarification"
    return "refine_issues"


def _route_after_refinement(
    state: CaseAnalysisState,
) -> Literal["build_evidence_request", "__end__"]:
    return "__end__" if "status" in state else "build_evidence_request"


def build_case_graph(
    case_intake_extractor: CaseIntakeExtractor,
    registry: IssueRegistry = ISSUE_REGISTRY,
    *,
    missing_fact_detector: MissingFactDetector | None = None,
    clarification_builder: TargetedClarificationBuilder | None = None,
    refined_issue_evaluator: RefinedIssueEvaluator | None = None,
    evidence_request_builder: EvidenceRequestSkeletonBuilder | None = None,
) -> StateGraph[CaseAnalysisState]:
    """Create the fixed five-node graph; every conditional route reaches ``END``."""

    nodes = _CaseAnalysisNodes(
        case_intake_extractor,
        registry,
        missing_fact_detector or MissingFactDetector(),
        clarification_builder or TargetedClarificationBuilder(),
        refined_issue_evaluator or RefinedIssueEvaluator(),
        evidence_request_builder or EvidenceRequestSkeletonBuilder(),
    )
    graph = StateGraph(CaseAnalysisState)
    graph.add_node("case_intake", nodes.case_intake)
    graph.add_node("detect_missing_facts", nodes.detect_missing_facts)
    graph.add_node("build_clarification", nodes.build_clarification)
    graph.add_node("refine_issues", nodes.refine_issues)
    graph.add_node("build_evidence_request", nodes.build_evidence_request)
    graph.add_edge(START, "case_intake")
    graph.add_conditional_edges(
        "case_intake",
        _route_after_intake,
        {"detect_missing_facts": "detect_missing_facts", END: END},
    )
    graph.add_conditional_edges(
        "detect_missing_facts",
        _route_after_missing_facts,
        {
            "build_clarification": "build_clarification",
            "refine_issues": "refine_issues",
            END: END,
        },
    )
    graph.add_edge("build_clarification", END)
    graph.add_conditional_edges(
        "refine_issues",
        _route_after_refinement,
        {"build_evidence_request": "build_evidence_request", END: END},
    )
    graph.add_edge("build_evidence_request", END)
    return graph


class CaseGraph:
    """Run one finite Case Analysis request with an injected Case Intake port."""

    def __init__(
        self,
        case_intake_extractor: CaseIntakeExtractor,
        registry: IssueRegistry = ISSUE_REGISTRY,
        *,
        missing_fact_detector: MissingFactDetector | None = None,
        clarification_builder: TargetedClarificationBuilder | None = None,
        refined_issue_evaluator: RefinedIssueEvaluator | None = None,
        evidence_request_builder: EvidenceRequestSkeletonBuilder | None = None,
    ) -> None:
        self.graph = build_case_graph(
            case_intake_extractor,
            registry,
            missing_fact_detector=missing_fact_detector,
            clarification_builder=clarification_builder,
            refined_issue_evaluator=refined_issue_evaluator,
            evidence_request_builder=evidence_request_builder,
        ).compile()

    async def run(self, question: str) -> CaseAnalysisResult:
        request_id = str(uuid.uuid4())
        try:
            completed = await self.graph.ainvoke(
                {
                    "request_id": request_id,
                    "question": question,
                }
            )
            return CaseAnalysisResult(
                request_id=request_id,
                status=completed["status"],
                message=completed["message"],
                error_code=completed.get("error_code"),
                intake_result=completed.get("intake_result"),
                missing_facts=completed.get("missing_facts"),
                clarification=completed.get("clarification"),
                refined_issues=completed.get("refined_issues"),
                evidence_request=completed.get("evidence_request"),
            )
        except Exception:
            return CaseAnalysisResult(
                request_id=request_id,
                status=CaseAnalysisStatus.CASE_ANALYSIS_FAILED,
                message=_ANALYSIS_FAILED_MESSAGE,
                error_code=CaseAnalysisErrorCode.CASE_DOMAIN_CONTRACT_INVALID,
            )


def _safe_intake_error_code(reason: str) -> CaseAnalysisErrorCode:
    return _INTAKE_ERROR_CODES.get(
        reason,
        CaseAnalysisErrorCode.CASE_INTAKE_PROVIDER_ERROR,
    )


def _intake_failure(error_code: CaseAnalysisErrorCode) -> _CaseAnalysisStateUpdate:
    return {
        "status": CaseAnalysisStatus.CASE_INTAKE_FAILED,
        "error_code": error_code,
        "message": _INTAKE_FAILED_MESSAGE,
    }


def _analysis_failure() -> _CaseAnalysisStateUpdate:
    return {
        "status": CaseAnalysisStatus.CASE_ANALYSIS_FAILED,
        "error_code": CaseAnalysisErrorCode.CASE_DOMAIN_CONTRACT_INVALID,
        "message": _ANALYSIS_FAILED_MESSAGE,
    }
