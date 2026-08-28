"""Deterministic refinement of preliminary issues without legal conclusions.

The current registry can establish only two reachable analysis states: a supported
candidate is ``ACTIVE`` when every configured requirement is satisfied, otherwise it
remains ``POSSIBLE``. ``RESOLVED_OUT`` is reserved until a future typed contract can
represent deterministic exclusion evidence. ``UNSUPPORTED_SCOPE`` is reserved for a
typed applicability boundary that the current complete registry does not expose.
Malformed or unknown candidates fail closed instead of being placed in either reserved
status.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from vietnamese_labor_law_assistant.decision_support.issue_registry import (
    ApplicabilityScope,
    FactKey,
    IssueDefinition,
    IssueRegistry,
)
from vietnamese_labor_law_assistant.decision_support.issues import (
    IssueCode,
    IssueRefinementReasonCode,
    RefinedIssueStatus,
)
from vietnamese_labor_law_assistant.decision_support.missing_facts import (
    IssueMissingFactResult,
    MissingFactDetector,
    MissingFactResult,
)
from vietnamese_labor_law_assistant.decision_support.models import CandidateIssue, CaseFact


class RefinedIssueErrorCode(StrEnum):
    """Fail-closed errors for inconsistent refinement inputs."""

    INCONSISTENT_MISSING_FACT_RESULT = "INCONSISTENT_MISSING_FACT_RESULT"


class RefinedIssueError(ValueError):
    """Typed domain error raised when refinement cannot proceed safely."""

    def __init__(self, code: RefinedIssueErrorCode) -> None:
        self.code = code
        super().__init__(code.value)


class RefinedIssue(BaseModel):
    """Current analysis state and source-grounded trace for one candidate issue."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    issue_code: IssueCode
    candidate_issue: CandidateIssue
    status: RefinedIssueStatus
    reason_code: IssueRefinementReasonCode
    applicability_scope: ApplicabilityScope
    relevant_fact_keys: tuple[FactKey, ...]
    relevant_facts: tuple[CaseFact, ...]
    remaining_missing_fields: tuple[FactKey, ...]
    critical_missing_fields: tuple[FactKey, ...]

    @model_validator(mode="after")
    def validate_refined_issue_contract(self) -> RefinedIssue:
        if self.candidate_issue.issue_code is not self.issue_code:
            raise ValueError("candidate issue must match refined issue code")
        if len(self.relevant_fact_keys) != len(set(self.relevant_fact_keys)):
            raise ValueError("relevant fact keys must be unique")
        if len(self.remaining_missing_fields) != len(set(self.remaining_missing_fields)):
            raise ValueError("remaining missing fields must be unique")
        if len(self.critical_missing_fields) != len(set(self.critical_missing_fields)):
            raise ValueError("critical missing fields must be unique")
        if not set(self.critical_missing_fields).issubset(self.remaining_missing_fields):
            raise ValueError("critical missing fields must remain missing")

        fact_ids = tuple(fact.fact_id for fact in self.relevant_facts)
        if len(fact_ids) != len(set(fact_ids)):
            raise ValueError("relevant fact IDs must be unique")
        if any(fact.fact_key not in self.relevant_fact_keys for fact in self.relevant_facts):
            raise ValueError("relevant facts must match relevant fact keys")

        expected_reason = {
            RefinedIssueStatus.ACTIVE: IssueRefinementReasonCode.REQUIREMENTS_SATISFIED,
            RefinedIssueStatus.RESOLVED_OUT: (
                IssueRefinementReasonCode.DETERMINISTIC_EXCLUSION_ESTABLISHED
            ),
            RefinedIssueStatus.UNSUPPORTED_SCOPE: (
                IssueRefinementReasonCode.APPLICABILITY_SCOPE_UNSUPPORTED
            ),
        }.get(self.status)
        if self.status is RefinedIssueStatus.POSSIBLE:
            expected_reason = (
                IssueRefinementReasonCode.CRITICAL_FACTS_MISSING
                if self.critical_missing_fields
                else IssueRefinementReasonCode.REQUIRED_FACTS_MISSING
            )
        if self.reason_code is not expected_reason:
            raise ValueError("refined status and reason code must be consistent")

        if self.status is RefinedIssueStatus.ACTIVE and self.remaining_missing_fields:
            raise ValueError("active issue cannot have remaining missing fields")
        if self.status is RefinedIssueStatus.POSSIBLE and not self.remaining_missing_fields:
            raise ValueError("possible issue must have remaining missing fields")
        if (
            self.status
            in {
                RefinedIssueStatus.RESOLVED_OUT,
                RefinedIssueStatus.UNSUPPORTED_SCOPE,
            }
            and self.critical_missing_fields
        ):
            raise ValueError("terminal issue status cannot carry a critical missing field")
        return self


class RefinedIssueResult(BaseModel):
    """Canonical refined-issue ordering and aggregate critical-gap state."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    issues: tuple[RefinedIssue, ...] = Field(min_length=1)
    critical_missing: bool

    @model_validator(mode="after")
    def validate_result_contract(self) -> RefinedIssueResult:
        issue_codes = tuple(issue.issue_code for issue in self.issues)
        if len(issue_codes) != len(set(issue_codes)):
            raise ValueError("refined issue codes must be unique")
        canonical_order = tuple(code for code in IssueCode if code in issue_codes)
        if issue_codes != canonical_order:
            raise ValueError("refined issues must follow canonical IssueCode order")
        expected_critical_missing = any(issue.critical_missing_fields for issue in self.issues)
        if self.critical_missing is not expected_critical_missing:
            raise ValueError("aggregate critical missing state must match refined issues")
        return self


class RefinedIssueEvaluator:
    """Re-evaluate candidates from registry requirements and the latest fact state."""

    def refine(
        self,
        known_facts: Sequence[CaseFact],
        candidate_issues: Sequence[CandidateIssue],
        missing_facts: MissingFactResult,
        registry: IssueRegistry,
    ) -> RefinedIssueResult:
        facts = tuple(known_facts)
        candidates = tuple(candidate_issues)
        expected_missing = MissingFactDetector().detect(facts, candidates, registry)
        if missing_facts != expected_missing:
            raise RefinedIssueError(RefinedIssueErrorCode.INCONSISTENT_MISSING_FACT_RESULT)

        candidates_by_code = {candidate.issue_code: candidate for candidate in candidates}
        refined = tuple(
            _refine_supported_issue(
                candidates_by_code[issue_result.issue_code],
                issue_result,
                _definition_or_raise(registry, issue_result.issue_code),
                facts,
            )
            for issue_result in expected_missing.issue_results
        )
        return RefinedIssueResult(
            issues=refined,
            critical_missing=expected_missing.critical_missing,
        )


def _definition_or_raise(registry: IssueRegistry, issue_code: IssueCode) -> IssueDefinition:
    definition = registry.lookup(issue_code)
    if definition is None:
        raise RefinedIssueError(RefinedIssueErrorCode.INCONSISTENT_MISSING_FACT_RESULT)
    return definition


def _refine_supported_issue(
    candidate: CandidateIssue,
    missing: IssueMissingFactResult,
    definition: IssueDefinition,
    facts: tuple[CaseFact, ...],
) -> RefinedIssue:
    relevant_fact_keys, relevant_facts = _relevant_fact_trace(definition, facts)
    if missing.critical_missing:
        status = RefinedIssueStatus.POSSIBLE
        reason = IssueRefinementReasonCode.CRITICAL_FACTS_MISSING
    elif missing.missing_fields:
        status = RefinedIssueStatus.POSSIBLE
        reason = IssueRefinementReasonCode.REQUIRED_FACTS_MISSING
    else:
        status = RefinedIssueStatus.ACTIVE
        reason = IssueRefinementReasonCode.REQUIREMENTS_SATISFIED
    return RefinedIssue(
        issue_code=definition.issue_code,
        candidate_issue=candidate,
        status=status,
        reason_code=reason,
        applicability_scope=definition.applicability_scope,
        relevant_fact_keys=relevant_fact_keys,
        relevant_facts=relevant_facts,
        remaining_missing_fields=missing.missing_fields,
        critical_missing_fields=missing.critical_missing_fields,
    )


def _relevant_fact_trace(
    definition: IssueDefinition,
    facts: tuple[CaseFact, ...],
) -> tuple[tuple[FactKey, ...], tuple[CaseFact, ...]]:
    facts_by_key: dict[FactKey, tuple[CaseFact, ...]] = {}
    for requirement in definition.required_facts:
        matches = tuple(
            sorted(
                (fact for fact in facts if fact.fact_key == requirement.fact_key.value),
                key=lambda fact: fact.fact_id,
            )
        )
        if matches:
            facts_by_key[requirement.fact_key] = matches
    relevant_keys = tuple(facts_by_key)
    relevant_facts = tuple(fact for fact_key in relevant_keys for fact in facts_by_key[fact_key])
    return relevant_keys, relevant_facts
