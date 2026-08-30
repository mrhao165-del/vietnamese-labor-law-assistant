"""Pure deterministic missing-fact detection over the stable issue registry."""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from vietnamese_labor_law_assistant.decision_support.issue_registry import (
    AlternativeFactSatisfier,
    FactConflictCode,
    FactKey,
    FactRequirement,
    FactSatisfactionRule,
    IssueDefinition,
    IssueRegistry,
)
from vietnamese_labor_law_assistant.decision_support.issues import IssueCode
from vietnamese_labor_law_assistant.decision_support.models import CandidateIssue, CaseFact


class RequirementStatus(StrEnum):
    """How the known facts relate to one configured requirement."""

    SATISFIED = "SATISFIED"
    MISSING = "MISSING"
    POLICY_REJECTED = "POLICY_REJECTED"


class RequirementGapReason(StrEnum):
    """Deterministic reasons a required fact cannot satisfy its requirement."""

    FACT_NOT_PROVIDED = "FACT_NOT_PROVIDED"
    ASSERTION_MODE_NOT_ACCEPTED = "ASSERTION_MODE_NOT_ACCEPTED"
    VERIFICATION_STATUS_NOT_ACCEPTED = "VERIFICATION_STATUS_NOT_ACCEPTED"
    ALTERNATIVE_RULE_NOT_SATISFIED = "ALTERNATIVE_RULE_NOT_SATISFIED"
    CONFLICTING_FACTS = "CONFLICTING_FACTS"


class MissingFactDetectionErrorCode(StrEnum):
    """Fail-closed input errors that prevent a reliable gap result."""

    NO_CANDIDATE_ISSUES = "NO_CANDIDATE_ISSUES"
    UNSUPPORTED_CANDIDATE_ISSUE = "UNSUPPORTED_CANDIDATE_ISSUE"
    DUPLICATE_CANDIDATE_ISSUE = "DUPLICATE_CANDIDATE_ISSUE"
    DUPLICATE_FACT_REPRESENTATION = "DUPLICATE_FACT_REPRESENTATION"


class MissingFactDetectionError(ValueError):
    """Typed domain error for an input that cannot be evaluated safely."""

    def __init__(self, code: MissingFactDetectionErrorCode) -> None:
        self.code = code
        super().__init__(code.value)


class RequirementAssessment(BaseModel):
    """Traceable outcome for one issue-specific fact requirement."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    issue_code: IssueCode
    fact_key: FactKey
    role: str
    critical: bool
    status: RequirementStatus
    matched_fact_ids: tuple[str, ...]
    gap_reasons: tuple[RequirementGapReason, ...]


class IssueMissingFactResult(BaseModel):
    """Requirement outcomes and critical gate state for one candidate issue."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    issue_code: IssueCode
    requirements: tuple[RequirementAssessment, ...]
    satisfied_fields: tuple[FactKey, ...]
    missing_fields: tuple[FactKey, ...]
    critical_missing_fields: tuple[FactKey, ...]
    critical_missing: bool


class AggregatedFieldNeed(BaseModel):
    """One deduplicated field gap with issue-level traceability."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    fact_key: FactKey
    required_by_issues: tuple[IssueCode, ...]
    critical_for_issues: tuple[IssueCode, ...]


class FactConflict(BaseModel):
    """A source-preserving cross-field conflict that blocks substantive routing."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: FactConflictCode
    issue_code: IssueCode
    involved_fact_keys: tuple[FactKey, ...]
    matched_fact_ids: tuple[str, ...]
    resolution_fact_keys: tuple[FactKey, ...]


class MissingFactResult(BaseModel):
    """Deterministic multi-issue gap result; it carries no legal conclusion."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    issue_results: tuple[IssueMissingFactResult, ...]
    fields_needed: tuple[AggregatedFieldNeed, ...]
    conflicts: tuple[FactConflict, ...] = ()
    critical_missing: bool


class MissingFactDetector:
    """Compare known facts with registry requirements without deriving new facts."""

    def detect(
        self,
        known_facts: Sequence[CaseFact],
        candidate_issues: Sequence[CandidateIssue],
        registry: IssueRegistry,
    ) -> MissingFactResult:
        facts = tuple(known_facts)
        candidates = tuple(candidate_issues)
        selected_issue_codes = _validate_candidates(candidates, registry)
        _validate_unique_fact_representations(facts)

        issue_results = tuple(
            _assess_issue(definition, facts)
            for definition in registry.definitions
            if definition.issue_code in selected_issue_codes
        )
        fields_needed = _aggregate_fields_needed(issue_results)
        conflicts = _detect_conflicts(registry, selected_issue_codes, facts)
        return MissingFactResult(
            issue_results=issue_results,
            fields_needed=fields_needed,
            conflicts=conflicts,
            critical_missing=any(result.critical_missing for result in issue_results),
        )


def _validate_candidates(
    candidates: tuple[CandidateIssue, ...], registry: IssueRegistry
) -> frozenset[IssueCode]:
    if not candidates:
        raise MissingFactDetectionError(MissingFactDetectionErrorCode.NO_CANDIDATE_ISSUES)

    normalized: list[IssueCode] = []
    for candidate in candidates:
        definition = registry.lookup(candidate.issue_code)
        if definition is None:
            raise MissingFactDetectionError(
                MissingFactDetectionErrorCode.UNSUPPORTED_CANDIDATE_ISSUE
            )
        normalized.append(definition.issue_code)
    if len(normalized) != len(set(normalized)):
        raise MissingFactDetectionError(MissingFactDetectionErrorCode.DUPLICATE_CANDIDATE_ISSUE)
    return frozenset(normalized)


def _validate_unique_fact_representations(facts: tuple[CaseFact, ...]) -> None:
    seen: set[tuple[object, ...]] = set()
    for fact in facts:
        representation = (
            fact.fact_key,
            fact.fact_type,
            fact.raw_value,
            fact.source_ref,
            fact.source_span.start_offset,
            fact.source_span.end_offset,
        )
        if representation in seen:
            raise MissingFactDetectionError(
                MissingFactDetectionErrorCode.DUPLICATE_FACT_REPRESENTATION
            )
        seen.add(representation)


def _assess_issue(
    definition: IssueDefinition, facts: tuple[CaseFact, ...]
) -> IssueMissingFactResult:
    required_facts, critical_facts = _active_requirements(definition, facts)
    critical_keys = set(critical_facts)
    assessments = tuple(
        _assess_requirement(definition.issue_code, requirement, critical_keys, facts)
        for requirement in required_facts
    )
    satisfied_fields = tuple(
        assessment.fact_key
        for assessment in assessments
        if assessment.status is RequirementStatus.SATISFIED
    )
    missing_fields = tuple(
        assessment.fact_key
        for assessment in assessments
        if assessment.status is not RequirementStatus.SATISFIED
    )
    critical_missing_fields = tuple(
        assessment.fact_key
        for assessment in assessments
        if assessment.critical and assessment.status is not RequirementStatus.SATISFIED
    )
    return IssueMissingFactResult(
        issue_code=definition.issue_code,
        requirements=assessments,
        satisfied_fields=satisfied_fields,
        missing_fields=missing_fields,
        critical_missing_fields=critical_missing_fields,
        critical_missing=bool(critical_missing_fields),
    )


def _assess_requirement(
    issue_code: IssueCode,
    requirement: FactRequirement,
    critical_keys: set[FactKey],
    facts: tuple[CaseFact, ...],
) -> RequirementAssessment:
    matching = tuple(
        sorted(
            (fact for fact in facts if fact.fact_key == requirement.fact_key.value),
            key=lambda fact: fact.fact_id,
        )
    )
    satisfying = tuple(
        fact
        for fact in matching
        if fact.assertion_mode in requirement.accepted_assertion_modes
        and fact.verification_status in requirement.accepted_verification_statuses
    )
    alternative_matching = tuple(
        fact
        for alternative in requirement.alternative_satisfiers
        for fact in sorted(
            (fact for fact in facts if fact.fact_key == alternative.fact_key.value),
            key=lambda fact: fact.fact_id,
        )
    )
    alternative_satisfying = tuple(
        fact
        for alternative in requirement.alternative_satisfiers
        for fact in alternative_matching
        if fact.fact_key == alternative.fact_key.value and _alternative_satisfies(fact, alternative)
    )
    if satisfying or alternative_satisfying:
        return RequirementAssessment(
            issue_code=issue_code,
            fact_key=requirement.fact_key,
            role=requirement.role,
            critical=requirement.fact_key in critical_keys,
            status=RequirementStatus.SATISFIED,
            matched_fact_ids=tuple(fact.fact_id for fact in (*satisfying, *alternative_satisfying)),
            gap_reasons=(),
        )
    all_matching = (*matching, *alternative_matching)
    if not all_matching:
        status = RequirementStatus.MISSING
        reasons = (RequirementGapReason.FACT_NOT_PROVIDED,)
    else:
        status = RequirementStatus.POLICY_REJECTED
        reasons = _requirement_rejection_reasons(matching, requirement, alternative_matching)
    return RequirementAssessment(
        issue_code=issue_code,
        fact_key=requirement.fact_key,
        role=requirement.role,
        critical=requirement.fact_key in critical_keys,
        status=status,
        matched_fact_ids=tuple(fact.fact_id for fact in all_matching),
        gap_reasons=reasons,
    )


def _policy_rejection_reasons(
    matching: tuple[CaseFact, ...], requirement: FactRequirement
) -> tuple[RequirementGapReason, ...]:
    reasons: list[RequirementGapReason] = []
    if any(fact.assertion_mode not in requirement.accepted_assertion_modes for fact in matching):
        reasons.append(RequirementGapReason.ASSERTION_MODE_NOT_ACCEPTED)
    if any(
        fact.verification_status not in requirement.accepted_verification_statuses
        for fact in matching
    ):
        reasons.append(RequirementGapReason.VERIFICATION_STATUS_NOT_ACCEPTED)
    return tuple(reasons)


def _active_requirements(
    definition: IssueDefinition,
    facts: tuple[CaseFact, ...],
) -> tuple[tuple[FactRequirement, ...], tuple[FactKey, ...]]:
    for branch in definition.conditional_requirement_branches:
        if any(fact.fact_key == branch.trigger_fact_key.value for fact in facts):
            return branch.required_facts, branch.critical_facts
    return definition.required_facts, definition.critical_facts


def _alternative_satisfies(
    fact: CaseFact,
    alternative: AlternativeFactSatisfier,
) -> bool:
    if (
        fact.assertion_mode not in alternative.accepted_assertion_modes
        or fact.verification_status not in alternative.accepted_verification_statuses
    ):
        return False
    if alternative.rule is FactSatisfactionRule.FIXED_TERM_DURATION_MONTHS_1_TO_36:
        value = fact.normalized_value
        return not isinstance(value, bool) and isinstance(value, (int, float)) and 1 <= value <= 36
    return False


def _requirement_rejection_reasons(
    matching: tuple[CaseFact, ...],
    requirement: FactRequirement,
    alternative_matching: tuple[CaseFact, ...],
) -> tuple[RequirementGapReason, ...]:
    reasons = list(_policy_rejection_reasons(matching, requirement))
    if alternative_matching:
        if any(
            fact.assertion_mode not in alternative.accepted_assertion_modes
            for alternative in requirement.alternative_satisfiers
            for fact in alternative_matching
            if fact.fact_key == alternative.fact_key.value
        ):
            reasons.append(RequirementGapReason.ASSERTION_MODE_NOT_ACCEPTED)
        if any(
            fact.verification_status not in alternative.accepted_verification_statuses
            for alternative in requirement.alternative_satisfiers
            for fact in alternative_matching
            if fact.fact_key == alternative.fact_key.value
        ):
            reasons.append(RequirementGapReason.VERIFICATION_STATUS_NOT_ACCEPTED)
        if not any(
            _alternative_satisfies(fact, alternative)
            for alternative in requirement.alternative_satisfiers
            for fact in alternative_matching
            if fact.fact_key == alternative.fact_key.value
        ):
            reasons.append(RequirementGapReason.ALTERNATIVE_RULE_NOT_SATISFIED)
    return tuple(dict.fromkeys(reasons))


def _detect_conflicts(
    registry: IssueRegistry,
    selected_issue_codes: frozenset[IssueCode],
    facts: tuple[CaseFact, ...],
) -> tuple[FactConflict, ...]:
    conflicts: list[FactConflict] = []
    for definition in registry.definitions:
        if definition.issue_code not in selected_issue_codes:
            continue
        for rule in definition.conflict_rules:
            guard_facts = tuple(
                fact
                for fact in facts
                if fact.fact_key == rule.guard_fact_key.value
                and fact.assertion_mode in rule.accepted_assertion_modes
                and str(fact.normalized_value).upper() in rule.guard_normalized_values
            )
            conflicting_facts = tuple(
                fact
                for fact in facts
                if fact.fact_key == rule.conflicting_fact_key.value
                and fact.assertion_mode in rule.accepted_assertion_modes
            )
            if not guard_facts or not conflicting_facts:
                continue
            matched = tuple(
                sorted((*guard_facts, *conflicting_facts), key=lambda fact: fact.fact_id)
            )
            conflicts.append(
                FactConflict(
                    code=rule.code,
                    issue_code=definition.issue_code,
                    involved_fact_keys=(rule.guard_fact_key, rule.conflicting_fact_key),
                    matched_fact_ids=tuple(fact.fact_id for fact in matched),
                    resolution_fact_keys=rule.resolution_fact_keys,
                )
            )
    return tuple(conflicts)


def _aggregate_fields_needed(
    issue_results: tuple[IssueMissingFactResult, ...],
) -> tuple[AggregatedFieldNeed, ...]:
    field_order: list[FactKey] = []
    required_by: dict[FactKey, list[IssueCode]] = {}
    critical_for: dict[FactKey, list[IssueCode]] = {}
    for issue_result in issue_results:
        for assessment in issue_result.requirements:
            if assessment.status is RequirementStatus.SATISFIED:
                continue
            if assessment.fact_key not in required_by:
                field_order.append(assessment.fact_key)
                required_by[assessment.fact_key] = []
                critical_for[assessment.fact_key] = []
            required_by[assessment.fact_key].append(issue_result.issue_code)
            if assessment.critical:
                critical_for[assessment.fact_key].append(issue_result.issue_code)
    return tuple(
        AggregatedFieldNeed(
            fact_key=fact_key,
            required_by_issues=tuple(required_by[fact_key]),
            critical_for_issues=tuple(critical_for[fact_key]),
        )
        for fact_key in field_order
    )
