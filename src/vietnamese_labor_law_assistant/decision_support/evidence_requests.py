"""Week-4 registry-driven evidence-request metadata without execution planning.

This module materializes the evidence and calculator requirement metadata that a
future case-analysis topology may need.  It is deliberately not an EvidencePlan:
it cannot generate queries, assign budgets, call tools, rank evidence, or execute
calculator capabilities.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator

from vietnamese_labor_law_assistant.decision_support.issue_registry import (
    ApplicabilityScope,
    CalculatorCapability,
    FactKey,
    IssueDefinition,
    IssueRegistry,
)
from vietnamese_labor_law_assistant.decision_support.issues import (
    IssueCode,
    IssueRefinementReasonCode,
    RefinedIssueStatus,
)
from vietnamese_labor_law_assistant.decision_support.refined_issues import (
    RefinedIssue,
    RefinedIssueResult,
)

_CONTRIBUTING_STATUSES = frozenset(
    {
        RefinedIssueStatus.ACTIVE,
        RefinedIssueStatus.POSSIBLE,
    }
)
_ISSUE_ORDER = {issue_code: index for index, issue_code in enumerate(IssueCode)}
_FACT_ORDER = {fact_key: index for index, fact_key in enumerate(FactKey)}
_CALCULATOR_ORDER = {capability: index for index, capability in enumerate(CalculatorCapability)}

_EvidenceRequestKey: TypeAlias = tuple[Literal["labor_law"], int, int, str]


class EvidenceRequestSkeletonErrorCode(StrEnum):
    """Fail-closed errors for inconsistent refined-issue and registry inputs."""

    REGISTRY_DEFINITION_MISMATCH = "REGISTRY_DEFINITION_MISMATCH"
    AMBIGUOUS_REGISTRY_REQUIREMENT = "AMBIGUOUS_REGISTRY_REQUIREMENT"


class EvidenceRequestSkeletonError(ValueError):
    """Typed domain error raised when safe request metadata cannot be produced."""

    def __init__(self, code: EvidenceRequestSkeletonErrorCode) -> None:
        self.code = code
        super().__init__(code.value)


class RegistryRequirementTrace(BaseModel):
    """One issue-specific registry reason attached to a deduplicated request."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    issue_code: IssueCode
    issue_status: RefinedIssueStatus
    registry_role: str = Field(min_length=1, max_length=300)

    @model_validator(mode="after")
    def validate_trace(self) -> RegistryRequirementTrace:
        if self.issue_status not in _CONTRIBUTING_STATUSES:
            raise ValueError("only contributing issue statuses may reference requirements")
        if not self.registry_role.strip():
            raise ValueError("registry role must not be blank")
        return self


class EvidenceRequestIssueState(BaseModel):
    """Refined issue state used to decide whether requirements are materialized."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    issue_code: IssueCode
    status: RefinedIssueStatus
    reason_code: IssueRefinementReasonCode
    applicability_scope: ApplicabilityScope
    critical_missing_fields: tuple[FactKey, ...]
    contributes_requirements: bool

    @model_validator(mode="after")
    def validate_selection_policy(self) -> EvidenceRequestIssueState:
        if len(self.critical_missing_fields) != len(set(self.critical_missing_fields)):
            raise ValueError("critical missing fields must be unique")
        canonical_fields = tuple(
            fact_key for fact_key in FactKey if fact_key in self.critical_missing_fields
        )
        if self.critical_missing_fields != canonical_fields:
            raise ValueError("critical missing fields must follow canonical FactKey order")
        if self.contributes_requirements is not (self.status in _CONTRIBUTING_STATUSES):
            raise ValueError("issue contribution flag must match refined status policy")
        if self.critical_missing_fields and self.status is not RefinedIssueStatus.POSSIBLE:
            raise ValueError("critical missing fields require a possible issue state")
        return self


class LegalEvidenceRequest(BaseModel):
    """Deduplicated canonical source metadata copied from registry requirements."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    document_id: Literal["labor_law"] = "labor_law"
    article: int = Field(gt=0)
    clause: int = Field(gt=0)
    source_chunk_id: str = Field(pattern=r"^ll_[0-9a-f]{32}$")
    issue_traces: tuple[RegistryRequirementTrace, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_issue_traces(self) -> LegalEvidenceRequest:
        _validate_trace_order(self.issue_traces)
        return self


class CalculatorRequirementRequest(BaseModel):
    """Deduplicated calculator capability metadata; no calculator can be executed here."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    capability: CalculatorCapability
    input_fact_keys: tuple[FactKey, ...] = Field(min_length=1)
    issue_traces: tuple[RegistryRequirementTrace, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_request(self) -> CalculatorRequirementRequest:
        if len(self.input_fact_keys) != len(set(self.input_fact_keys)):
            raise ValueError("calculator input fact keys must be unique")
        if self.input_fact_keys != _canonical_fact_keys(self.input_fact_keys):
            raise ValueError("calculator input fact keys must follow canonical FactKey order")
        _validate_trace_order(self.issue_traces)
        return self


class EvidenceRequestSkeleton(BaseModel):
    """Bounded Week-4 request metadata and the critical-fact safety gate."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    issue_states: tuple[EvidenceRequestIssueState, ...] = Field(min_length=1)
    evidence_requests: tuple[LegalEvidenceRequest, ...]
    calculator_requests: tuple[CalculatorRequirementRequest, ...]
    substantive_analysis_blocked: bool

    @model_validator(mode="after")
    def validate_skeleton(self) -> EvidenceRequestSkeleton:
        issue_codes = tuple(state.issue_code for state in self.issue_states)
        if len(issue_codes) != len(set(issue_codes)):
            raise ValueError("issue states must be unique")
        canonical_codes = tuple(issue_code for issue_code in IssueCode if issue_code in issue_codes)
        if issue_codes != canonical_codes:
            raise ValueError("issue states must follow canonical IssueCode order")

        expected_blocked = any(state.critical_missing_fields for state in self.issue_states)
        if self.substantive_analysis_blocked is not expected_blocked:
            raise ValueError("substantive analysis gate must match critical missing fields")

        contributing_states = {
            state.issue_code: state for state in self.issue_states if state.contributes_requirements
        }
        for trace in _all_traces(self):
            state = contributing_states.get(trace.issue_code)
            if state is None or trace.issue_status is not state.status:
                raise ValueError("requirement trace must match a contributing issue state")

        evidence_keys = tuple(
            (
                request.document_id,
                request.article,
                request.clause,
                request.source_chunk_id,
            )
            for request in self.evidence_requests
        )
        if len(evidence_keys) != len(set(evidence_keys)):
            raise ValueError("legal evidence requests must be deduplicated")
        calculator_keys = tuple(
            (request.capability, request.input_fact_keys) for request in self.calculator_requests
        )
        if len(calculator_keys) != len(set(calculator_keys)):
            raise ValueError("calculator requests must be deduplicated")
        return self


class EvidenceRequestSkeletonBuilder:
    """Materialize registry requirements selected by immutable refined issue states."""

    def build(
        self,
        refined_issues: RefinedIssueResult,
        registry: IssueRegistry,
    ) -> EvidenceRequestSkeleton:
        refined_by_code = {issue.issue_code: issue for issue in refined_issues.issues}
        states: list[EvidenceRequestIssueState] = []
        evidence: dict[_EvidenceRequestKey, list[RegistryRequirementTrace]] = {}
        calculators: dict[
            tuple[CalculatorCapability, tuple[FactKey, ...]],
            list[RegistryRequirementTrace],
        ] = {}

        for definition in registry.definitions:
            refined = refined_by_code.get(definition.issue_code)
            if refined is None:
                continue
            _validate_registry_match(refined, definition)
            contributes = refined.status in _CONTRIBUTING_STATUSES
            states.append(
                EvidenceRequestIssueState(
                    issue_code=refined.issue_code,
                    status=refined.status,
                    reason_code=refined.reason_code,
                    applicability_scope=refined.applicability_scope,
                    critical_missing_fields=_canonical_fact_keys(refined.critical_missing_fields),
                    contributes_requirements=contributes,
                )
            )
            if not contributes:
                continue
            _collect_evidence_requirements(evidence, refined, definition)
            _collect_calculator_requirements(calculators, refined, definition)

        if len(states) != len(refined_issues.issues):
            raise EvidenceRequestSkeletonError(
                EvidenceRequestSkeletonErrorCode.REGISTRY_DEFINITION_MISMATCH
            )

        evidence_requests = tuple(
            LegalEvidenceRequest(
                document_id=key[0],
                article=key[1],
                clause=key[2],
                source_chunk_id=key[3],
                issue_traces=_canonical_traces(traces),
            )
            for key, traces in sorted(evidence.items())
        )
        calculator_requests = tuple(
            CalculatorRequirementRequest(
                capability=key[0],
                input_fact_keys=key[1],
                issue_traces=_canonical_traces(traces),
            )
            for key, traces in sorted(
                calculators.items(),
                key=lambda item: (_CALCULATOR_ORDER[item[0][0]], item[0][1]),
            )
        )
        return EvidenceRequestSkeleton(
            issue_states=tuple(states),
            evidence_requests=evidence_requests,
            calculator_requests=calculator_requests,
            substantive_analysis_blocked=refined_issues.critical_missing,
        )


def _validate_registry_match(refined: RefinedIssue, definition: IssueDefinition) -> None:
    if (
        refined.issue_code is not definition.issue_code
        or refined.applicability_scope is not definition.applicability_scope
    ):
        raise EvidenceRequestSkeletonError(
            EvidenceRequestSkeletonErrorCode.REGISTRY_DEFINITION_MISMATCH
        )


def _collect_evidence_requirements(
    requests: dict[_EvidenceRequestKey, list[RegistryRequirementTrace]],
    refined: RefinedIssue,
    definition: IssueDefinition,
) -> None:
    for need in definition.evidence_needs:
        key = (need.document_id, need.article, need.clause, need.source_chunk_id)
        _append_trace(
            requests.setdefault(key, []),
            RegistryRequirementTrace(
                issue_code=refined.issue_code,
                issue_status=refined.status,
                registry_role=need.role,
            ),
        )


def _collect_calculator_requirements(
    requests: dict[
        tuple[CalculatorCapability, tuple[FactKey, ...]],
        list[RegistryRequirementTrace],
    ],
    refined: RefinedIssue,
    definition: IssueDefinition,
) -> None:
    for need in definition.calculator_needs:
        key = (need.capability, _canonical_fact_keys(need.input_fact_keys))
        _append_trace(
            requests.setdefault(key, []),
            RegistryRequirementTrace(
                issue_code=refined.issue_code,
                issue_status=refined.status,
                registry_role=need.role,
            ),
        )


def _append_trace(
    traces: list[RegistryRequirementTrace],
    trace: RegistryRequirementTrace,
) -> None:
    same_issue = next(
        (existing for existing in traces if existing.issue_code is trace.issue_code),
        None,
    )
    if same_issue is None:
        traces.append(trace)
        return
    if same_issue != trace:
        raise EvidenceRequestSkeletonError(
            EvidenceRequestSkeletonErrorCode.AMBIGUOUS_REGISTRY_REQUIREMENT
        )


def _canonical_fact_keys(fact_keys: tuple[FactKey, ...]) -> tuple[FactKey, ...]:
    return tuple(sorted(fact_keys, key=_FACT_ORDER.__getitem__))


def _canonical_traces(
    traces: list[RegistryRequirementTrace],
) -> tuple[RegistryRequirementTrace, ...]:
    return tuple(sorted(traces, key=lambda trace: _ISSUE_ORDER[trace.issue_code]))


def _validate_trace_order(traces: tuple[RegistryRequirementTrace, ...]) -> None:
    issue_codes = tuple(trace.issue_code for trace in traces)
    if len(issue_codes) != len(set(issue_codes)):
        raise ValueError("issue traces must be unique per issue")
    if traces != tuple(sorted(traces, key=lambda trace: _ISSUE_ORDER[trace.issue_code])):
        raise ValueError("issue traces must follow canonical IssueCode order")


def _all_traces(
    skeleton: EvidenceRequestSkeleton,
) -> tuple[RegistryRequirementTrace, ...]:
    return tuple(
        trace
        for request in (*skeleton.evidence_requests, *skeleton.calculator_requests)
        for trace in request.issue_traces
    )
