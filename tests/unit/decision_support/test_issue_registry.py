"""Offline contract tests for the stable Week-3 issue registry."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from vietnamese_labor_law_assistant.calculator.rules import DURATION_RULES, NOTICE_RULES
from vietnamese_labor_law_assistant.decision_support.enums import (
    AssertionMode,
    VerificationStatus,
)
from vietnamese_labor_law_assistant.decision_support.issue_registry import (
    ISSUE_REGISTRY,
    ApplicabilityScope,
    CalculatorCapability,
    FactKey,
    IssueDefinition,
    IssueRegistry,
)
from vietnamese_labor_law_assistant.decision_support.issues import IssueCode


def _definition_payload(issue_code: IssueCode) -> dict[str, object]:
    definition = ISSUE_REGISTRY.lookup(issue_code)
    assert definition is not None
    return definition.model_dump(mode="python")


def test_registry_contains_every_supported_candidate_issue_in_stable_order() -> None:
    assert ISSUE_REGISTRY.supported_issue_codes == tuple(IssueCode)
    assert ISSUE_REGISTRY.supported_issue_codes == (
        IssueCode.CONTRACT_TERM,
        IssueCode.EMPLOYEE_UNILATERAL_TERMINATION,
    )


@pytest.mark.parametrize("issue_code", tuple(IssueCode))
def test_registry_lookup_is_deterministic(issue_code: IssueCode) -> None:
    first = ISSUE_REGISTRY.lookup(issue_code)
    second = ISSUE_REGISTRY.lookup(issue_code.value)

    assert first is second
    assert first is not None
    assert first.issue_code is issue_code


def test_unknown_issue_lookup_is_safe() -> None:
    assert ISSUE_REGISTRY.lookup("EMPLOYER_TERMINATION") is None


def test_required_facts_use_closed_policies_and_critical_facts_are_a_subset() -> None:
    for definition in ISSUE_REGISTRY.definitions:
        required_keys = tuple(requirement.fact_key for requirement in definition.required_facts)

        assert required_keys
        assert set(definition.critical_facts) <= set(required_keys)
        for requirement in definition.required_facts:
            assert requirement.accepted_assertion_modes == (
                AssertionMode.EXPLICIT,
                AssertionMode.INFERRED,
            )
            assert requirement.accepted_verification_statuses == (VerificationStatus.UNVERIFIED,)
            assert requirement.role.strip()


def test_registry_metadata_is_bounded_to_current_sources_and_calculators() -> None:
    contract_term = ISSUE_REGISTRY.lookup(IssueCode.CONTRACT_TERM)
    termination = ISSUE_REGISTRY.lookup(IssueCode.EMPLOYEE_UNILATERAL_TERMINATION)

    assert contract_term is not None and termination is not None
    assert contract_term.applicability_scope is ApplicabilityScope.CONTRACT_TYPE_AND_DURATION
    assert contract_term.calculator_needs[0].capability is CalculatorCapability.CONTRACT_DURATION
    assert contract_term.calculator_needs[0].input_fact_keys == (
        FactKey.CONTRACT_TYPE,
        FactKey.CONTRACT_START_DATE,
        FactKey.CONTRACT_END_DATE,
    )
    assert {(need.article, need.clause) for need in contract_term.evidence_needs} == {(20, 1)}

    assert termination.applicability_scope is ApplicabilityScope.EMPLOYEE_UNILATERAL_TERMINATION
    assert termination.calculator_needs[0].capability is CalculatorCapability.NOTICE_PERIOD
    assert termination.calculator_needs[0].input_fact_keys == (
        FactKey.CONTRACT_TYPE,
        FactKey.NOTICE_SPECIAL_CASE,
        FactKey.EMPLOYEE_ROLE,
    )
    assert {(need.article, need.clause) for need in termination.evidence_needs} == {
        (35, 1),
        (35, 2),
        (97, 4),
    }


def test_every_evidence_need_is_an_existing_calculator_legal_basis() -> None:
    canonical_bases = {
        (basis.document_id, basis.article, basis.clause, basis.source_chunk_id)
        for rule in (*DURATION_RULES, *NOTICE_RULES)
        for basis in rule.legal_basis
    }

    for definition in ISSUE_REGISTRY.definitions:
        for need in definition.evidence_needs:
            assert (
                need.document_id,
                need.article,
                need.clause,
                need.source_chunk_id,
            ) in canonical_bases


def test_duplicate_issue_definitions_fail_closed() -> None:
    definition = ISSUE_REGISTRY.definitions[0]

    with pytest.raises(ValidationError, match="issue codes must be unique"):
        IssueRegistry(definitions=(definition, definition))


def test_registry_rejects_missing_or_noncanonical_issue_definitions() -> None:
    with pytest.raises(ValidationError, match="cover every supported issue"):
        IssueRegistry(definitions=(ISSUE_REGISTRY.definitions[0],))
    with pytest.raises(ValidationError, match="canonical IssueCode order"):
        IssueRegistry(definitions=tuple(reversed(ISSUE_REGISTRY.definitions)))


def test_duplicate_required_fact_fails_closed() -> None:
    payload = _definition_payload(IssueCode.CONTRACT_TERM)
    required_facts = list(payload["required_facts"])  # type: ignore[arg-type]
    payload["required_facts"] = [*required_facts, required_facts[0]]

    with pytest.raises(ValidationError, match="required fact keys must be unique"):
        IssueDefinition.model_validate(payload)


def test_critical_fact_outside_required_facts_fails_closed() -> None:
    payload = _definition_payload(IssueCode.CONTRACT_TERM)
    payload["critical_facts"] = [*payload["critical_facts"], FactKey.EVENT_TIME]  # type: ignore[misc]

    with pytest.raises(ValidationError, match="critical facts must be required"):
        IssueDefinition.model_validate(payload)


def test_unknown_issue_and_fact_keys_fail_closed() -> None:
    issue_payload = _definition_payload(IssueCode.CONTRACT_TERM)
    issue_payload["issue_code"] = "EMPLOYER_TERMINATION"
    with pytest.raises(ValidationError):
        IssueDefinition.model_validate(issue_payload)

    fact_payload = _definition_payload(IssueCode.CONTRACT_TERM)
    requirements = list(fact_payload["required_facts"])  # type: ignore[arg-type]
    requirements[0] = {**requirements[0], "fact_key": "MODEL_INVENTED_FACT"}
    fact_payload["required_facts"] = requirements
    with pytest.raises(ValidationError):
        IssueDefinition.model_validate(fact_payload)


def test_invalid_assertion_or_verification_policy_fails_closed() -> None:
    assertion_payload = _definition_payload(IssueCode.CONTRACT_TERM)
    assertion_requirements = list(assertion_payload["required_facts"])  # type: ignore[arg-type]
    assertion_requirements[0] = {
        **assertion_requirements[0],
        "accepted_assertion_modes": ["MODEL_ASSUMED"],
    }
    assertion_payload["required_facts"] = assertion_requirements
    with pytest.raises(ValidationError):
        IssueDefinition.model_validate(assertion_payload)

    verification_payload = _definition_payload(IssueCode.CONTRACT_TERM)
    verification_requirements = list(verification_payload["required_facts"])  # type: ignore[arg-type]
    verification_requirements[0] = {
        **verification_requirements[0],
        "accepted_verification_statuses": [],
    }
    verification_payload["required_facts"] = verification_requirements
    with pytest.raises(ValidationError):
        IssueDefinition.model_validate(verification_payload)


def test_registry_and_nested_contracts_are_immutable() -> None:
    definition = ISSUE_REGISTRY.definitions[0]

    with pytest.raises(ValidationError):
        definition.issue_code = IssueCode.EMPLOYEE_UNILATERAL_TERMINATION
    with pytest.raises(ValidationError):
        definition.required_facts[0].role = "mutated"
    with pytest.raises(AttributeError):
        ISSUE_REGISTRY.definitions.append(definition)  # type: ignore[attr-defined]
