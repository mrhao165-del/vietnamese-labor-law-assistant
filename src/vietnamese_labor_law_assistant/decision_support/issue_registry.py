"""Stable, immutable issue requirements for the bounded v1.1 legal scope."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from vietnamese_labor_law_assistant.decision_support.enums import (
    AssertionMode,
    VerificationStatus,
)
from vietnamese_labor_law_assistant.decision_support.issues import IssueCode


class FactKey(StrEnum):
    """Closed facts grounded in Week-2 intake labels or existing calculator inputs."""

    CONTRACT_DURATION = "CONTRACT_DURATION"
    CONTRACT_EXPIRY_STATEMENT = "CONTRACT_EXPIRY_STATEMENT"
    CONTRACT_SIGNED_DATE = "CONTRACT_SIGNED_DATE"
    CONTRACT_TYPE = "CONTRACT_TYPE"
    EVENT_TIME = "EVENT_TIME"
    UNPAID_WAGES_AMOUNT = "UNPAID_WAGES_AMOUNT"
    UNPAID_WAGES_DURATION = "UNPAID_WAGES_DURATION"
    CONTRACT_START_DATE = "CONTRACT_START_DATE"
    CONTRACT_END_DATE = "CONTRACT_END_DATE"
    NOTICE_SPECIAL_CASE = "NOTICE_SPECIAL_CASE"
    EMPLOYEE_ROLE = "EMPLOYEE_ROLE"
    INTENDED_TERMINATION_DATE = "INTENDED_TERMINATION_DATE"
    INTENDED_TERMINATION_REFERENCE_DATE = "INTENDED_TERMINATION_REFERENCE_DATE"
    WAGE_PAYMENT_PROBLEM = "WAGE_PAYMENT_PROBLEM"
    WAGE_PAYMENT_DUE_DATE = "WAGE_PAYMENT_DUE_DATE"
    WAGE_PAYMENT_STATUS = "WAGE_PAYMENT_STATUS"
    WAGE_DELAY_FORCE_MAJEURE = "WAGE_DELAY_FORCE_MAJEURE"


class FactSatisfactionRule(StrEnum):
    """Closed deterministic rules by which another fact may satisfy a requirement."""

    FIXED_TERM_DURATION_MONTHS_1_TO_36 = "FIXED_TERM_DURATION_MONTHS_1_TO_36"


class FactConflictCode(StrEnum):
    """Typed cross-field conflicts that must fail closed."""

    INDEFINITE_WITH_CONTRACT_END_DATE = "INDEFINITE_WITH_CONTRACT_END_DATE"


class CalculatorCapability(StrEnum):
    """Existing deterministic calculator capabilities referenced as metadata only."""

    CONTRACT_DURATION = "CONTRACT_DURATION"
    NOTICE_PERIOD = "NOTICE_PERIOD"


class ApplicabilityScope(StrEnum):
    """Closed descriptions of the legal scope represented by each issue."""

    CONTRACT_TYPE_AND_DURATION = "CONTRACT_TYPE_AND_DURATION"
    EMPLOYEE_UNILATERAL_TERMINATION = "EMPLOYEE_UNILATERAL_TERMINATION"


class AlternativeFactSatisfier(BaseModel):
    """A source-grounded alternative that may satisfy one semantic requirement."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    fact_key: FactKey
    rule: FactSatisfactionRule
    accepted_assertion_modes: tuple[AssertionMode, ...] = Field(
        default=(AssertionMode.EXPLICIT, AssertionMode.INFERRED), min_length=1
    )
    accepted_verification_statuses: tuple[VerificationStatus, ...] = Field(
        default=(VerificationStatus.UNVERIFIED,), min_length=1
    )


class FactRequirement(BaseModel):
    """One required fact and the intake assertions that may satisfy it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    fact_key: FactKey
    role: str = Field(min_length=1, max_length=300)
    accepted_assertion_modes: tuple[AssertionMode, ...] = Field(
        default=(AssertionMode.EXPLICIT, AssertionMode.INFERRED), min_length=1
    )
    accepted_verification_statuses: tuple[VerificationStatus, ...] = Field(
        default=(VerificationStatus.UNVERIFIED,), min_length=1
    )
    alternative_satisfiers: tuple[AlternativeFactSatisfier, ...] = ()

    @model_validator(mode="after")
    def validate_policies(self) -> FactRequirement:
        if not self.role.strip():
            raise ValueError("fact requirement role must not be blank")
        if len(self.accepted_assertion_modes) != len(set(self.accepted_assertion_modes)):
            raise ValueError("accepted assertion modes must be unique")
        if len(self.accepted_verification_statuses) != len(
            set(self.accepted_verification_statuses)
        ):
            raise ValueError("accepted verification statuses must be unique")
        alternative_keys = tuple(item.fact_key for item in self.alternative_satisfiers)
        if len(alternative_keys) != len(set(alternative_keys)):
            raise ValueError("alternative satisfier fact keys must be unique")
        if self.fact_key in alternative_keys:
            raise ValueError("an alternative satisfier must use another fact key")
        return self


class ConditionalRequirementBranch(BaseModel):
    """A deterministic trigger that replaces an issue's ordinary requirements."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    trigger_fact_key: FactKey
    required_facts: tuple[FactRequirement, ...] = Field(min_length=1)
    critical_facts: tuple[FactKey, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_branch(self) -> ConditionalRequirementBranch:
        required_keys = tuple(item.fact_key for item in self.required_facts)
        if len(required_keys) != len(set(required_keys)):
            raise ValueError("conditional required fact keys must be unique")
        if not set(self.critical_facts).issubset(required_keys):
            raise ValueError("conditional critical facts must be required facts")
        return self


class IssueConflictRule(BaseModel):
    """One explicit cross-field combination that requires clarification."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: FactConflictCode
    guard_fact_key: FactKey
    guard_normalized_values: tuple[str, ...] = Field(min_length=1)
    conflicting_fact_key: FactKey
    resolution_fact_keys: tuple[FactKey, ...] = Field(min_length=1)
    accepted_assertion_modes: tuple[AssertionMode, ...] = (AssertionMode.EXPLICIT,)

    @model_validator(mode="after")
    def validate_rule(self) -> IssueConflictRule:
        if len(self.guard_normalized_values) != len(set(self.guard_normalized_values)):
            raise ValueError("conflict guard values must be unique")
        if len(self.resolution_fact_keys) != len(set(self.resolution_fact_keys)):
            raise ValueError("conflict resolution fact keys must be unique")
        return self


class EvidenceNeed(BaseModel):
    """Canonical source metadata needed by an issue, without retrieval execution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    document_id: Literal["labor_law"] = "labor_law"
    article: int = Field(gt=0)
    clause: int = Field(gt=0)
    source_chunk_id: str = Field(pattern=r"^ll_[0-9a-f]{32}$")
    role: str = Field(min_length=1, max_length=300)


class CalculatorNeed(BaseModel):
    """Calculator input metadata only; this contract cannot execute a capability."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    capability: CalculatorCapability
    input_fact_keys: tuple[FactKey, ...] = Field(min_length=1)
    role: str = Field(min_length=1, max_length=300)

    @model_validator(mode="after")
    def validate_input_fact_keys(self) -> CalculatorNeed:
        if len(self.input_fact_keys) != len(set(self.input_fact_keys)):
            raise ValueError("calculator input fact keys must be unique")
        if not self.role.strip():
            raise ValueError("calculator need role must not be blank")
        return self


class IssueDefinition(BaseModel):
    """Complete deterministic requirements for one supported candidate issue."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    issue_code: IssueCode
    required_facts: tuple[FactRequirement, ...] = Field(min_length=1)
    critical_facts: tuple[FactKey, ...] = Field(min_length=1)
    conditional_requirement_branches: tuple[ConditionalRequirementBranch, ...] = ()
    context_fact_keys: tuple[FactKey, ...] = ()
    conflict_rules: tuple[IssueConflictRule, ...] = ()
    evidence_needs: tuple[EvidenceNeed, ...] = Field(min_length=1)
    calculator_needs: tuple[CalculatorNeed, ...] = Field(min_length=1)
    applicability_scope: ApplicabilityScope

    @model_validator(mode="after")
    def validate_fact_contract(self) -> IssueDefinition:
        required_keys = tuple(requirement.fact_key for requirement in self.required_facts)
        if len(required_keys) != len(set(required_keys)):
            raise ValueError("required fact keys must be unique")
        if len(self.critical_facts) != len(set(self.critical_facts)):
            raise ValueError("critical fact keys must be unique")
        if not set(self.critical_facts).issubset(required_keys):
            raise ValueError("critical facts must be required facts")
        if len(self.context_fact_keys) != len(set(self.context_fact_keys)):
            raise ValueError("context fact keys must be unique")
        branch_triggers = tuple(
            branch.trigger_fact_key for branch in self.conditional_requirement_branches
        )
        if len(branch_triggers) != len(set(branch_triggers)):
            raise ValueError("conditional requirement triggers must be unique")
        conflict_codes = tuple(rule.code for rule in self.conflict_rules)
        if len(conflict_codes) != len(set(conflict_codes)):
            raise ValueError("conflict rule codes must be unique")
        accepted_calculator_keys = set(required_keys) | set(self.context_fact_keys)
        accepted_calculator_keys.update(
            alternative.fact_key
            for requirement in self.required_facts
            for alternative in requirement.alternative_satisfiers
        )
        for calculator_need in self.calculator_needs:
            if not set(calculator_need.input_fact_keys).issubset(accepted_calculator_keys):
                raise ValueError("calculator input facts must be required or context facts")
        return self


class IssueRegistry(BaseModel):
    """Complete registry with exact IssueCode coverage and canonical ordering."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    definitions: tuple[IssueDefinition, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_registry(self) -> IssueRegistry:
        issue_codes = tuple(definition.issue_code for definition in self.definitions)
        if len(issue_codes) != len(set(issue_codes)):
            raise ValueError("issue codes must be unique")
        canonical_codes = tuple(IssueCode)
        if set(issue_codes) != set(canonical_codes):
            raise ValueError("registry must cover every supported issue")
        if issue_codes != canonical_codes:
            raise ValueError("registry definitions must follow canonical IssueCode order")
        return self

    @property
    def supported_issue_codes(self) -> tuple[IssueCode, ...]:
        """Return stable IssueCode ordering without exposing mutable state."""

        return tuple(definition.issue_code for definition in self.definitions)

    def lookup(self, issue_code: IssueCode | str) -> IssueDefinition | None:
        """Return one immutable definition, or ``None`` for an unsupported code."""

        try:
            normalized = issue_code if isinstance(issue_code, IssueCode) else IssueCode(issue_code)
        except ValueError:
            return None
        return next(
            (definition for definition in self.definitions if definition.issue_code is normalized),
            None,
        )


ISSUE_REGISTRY = IssueRegistry(
    definitions=(
        IssueDefinition(
            issue_code=IssueCode.CONTRACT_TERM,
            required_facts=(
                FactRequirement(
                    fact_key=FactKey.CONTRACT_TYPE,
                    role="Select the bounded Article 20 contract-type rule.",
                    alternative_satisfiers=(
                        AlternativeFactSatisfier(
                            fact_key=FactKey.CONTRACT_DURATION,
                            rule=FactSatisfactionRule.FIXED_TERM_DURATION_MONTHS_1_TO_36,
                        ),
                    ),
                ),
            ),
            critical_facts=(FactKey.CONTRACT_TYPE,),
            context_fact_keys=(
                FactKey.CONTRACT_DURATION,
                FactKey.CONTRACT_START_DATE,
                FactKey.CONTRACT_END_DATE,
            ),
            conflict_rules=(
                IssueConflictRule(
                    code=FactConflictCode.INDEFINITE_WITH_CONTRACT_END_DATE,
                    guard_fact_key=FactKey.CONTRACT_TYPE,
                    guard_normalized_values=("INDEFINITE",),
                    conflicting_fact_key=FactKey.CONTRACT_END_DATE,
                    resolution_fact_keys=(
                        FactKey.CONTRACT_TYPE,
                        FactKey.CONTRACT_END_DATE,
                    ),
                ),
            ),
            evidence_needs=(
                EvidenceNeed(
                    article=20,
                    clause=1,
                    source_chunk_id="ll_d0c5f537983c0aad635529f412e426f5",
                    role="Ground contract type and the fixed-term maximum duration.",
                ),
            ),
            calculator_needs=(
                CalculatorNeed(
                    capability=CalculatorCapability.CONTRACT_DURATION,
                    input_fact_keys=(
                        FactKey.CONTRACT_TYPE,
                        FactKey.CONTRACT_START_DATE,
                        FactKey.CONTRACT_END_DATE,
                    ),
                    role="Describe inputs for the existing deterministic duration capability.",
                ),
            ),
            applicability_scope=ApplicabilityScope.CONTRACT_TYPE_AND_DURATION,
        ),
        IssueDefinition(
            issue_code=IssueCode.EMPLOYEE_UNILATERAL_TERMINATION,
            required_facts=(
                FactRequirement(
                    fact_key=FactKey.CONTRACT_TYPE,
                    role="Select the ordinary Article 35 notice branch when no exception applies.",
                    alternative_satisfiers=(
                        AlternativeFactSatisfier(
                            fact_key=FactKey.CONTRACT_DURATION,
                            rule=FactSatisfactionRule.FIXED_TERM_DURATION_MONTHS_1_TO_36,
                        ),
                    ),
                ),
                FactRequirement(
                    fact_key=FactKey.NOTICE_SPECIAL_CASE,
                    role="Select only an allowlisted no-notice or external-regulation branch.",
                ),
                FactRequirement(
                    fact_key=FactKey.EMPLOYEE_ROLE,
                    role="Distinguish standard work from the bounded special-occupation branch.",
                ),
            ),
            critical_facts=(
                FactKey.CONTRACT_TYPE,
                FactKey.NOTICE_SPECIAL_CASE,
                FactKey.EMPLOYEE_ROLE,
            ),
            conditional_requirement_branches=(
                ConditionalRequirementBranch(
                    trigger_fact_key=FactKey.WAGE_PAYMENT_PROBLEM,
                    required_facts=(
                        FactRequirement(
                            fact_key=FactKey.WAGE_PAYMENT_DUE_DATE,
                            role="Establish when the wage payment became due.",
                        ),
                        FactRequirement(
                            fact_key=FactKey.WAGE_PAYMENT_STATUS,
                            role="Establish whether the due wage remains unpaid or late.",
                        ),
                        FactRequirement(
                            fact_key=FactKey.WAGE_DELAY_FORCE_MAJEURE,
                            role="Check the bounded Article 97(4) force-majeure delay exception.",
                        ),
                    ),
                    critical_facts=(
                        FactKey.WAGE_PAYMENT_DUE_DATE,
                        FactKey.WAGE_PAYMENT_STATUS,
                        FactKey.WAGE_DELAY_FORCE_MAJEURE,
                    ),
                ),
            ),
            context_fact_keys=(
                FactKey.CONTRACT_DURATION,
                FactKey.INTENDED_TERMINATION_DATE,
                FactKey.INTENDED_TERMINATION_REFERENCE_DATE,
                FactKey.EVENT_TIME,
                FactKey.WAGE_PAYMENT_PROBLEM,
                FactKey.WAGE_PAYMENT_DUE_DATE,
                FactKey.WAGE_PAYMENT_STATUS,
                FactKey.WAGE_DELAY_FORCE_MAJEURE,
            ),
            evidence_needs=(
                EvidenceNeed(
                    article=35,
                    clause=1,
                    source_chunk_id="ll_6af59ba448952c1c927978713d34d984",
                    role="Ground ordinary employee notice periods and external-regulation limits.",
                ),
                EvidenceNeed(
                    article=35,
                    clause=2,
                    source_chunk_id="ll_610e9077fc973dabc980978eb3f3da54",
                    role="Ground the allowlisted employee no-notice cases.",
                ),
                EvidenceNeed(
                    article=97,
                    clause=4,
                    source_chunk_id="ll_637097a07e629f3154a38864853c6790",
                    role="Preserve the existing wage-delay exception limitation.",
                ),
            ),
            calculator_needs=(
                CalculatorNeed(
                    capability=CalculatorCapability.NOTICE_PERIOD,
                    input_fact_keys=(
                        FactKey.CONTRACT_TYPE,
                        FactKey.NOTICE_SPECIAL_CASE,
                        FactKey.EMPLOYEE_ROLE,
                    ),
                    role="Describe inputs for the existing deterministic notice capability.",
                ),
            ),
            applicability_scope=ApplicabilityScope.EMPLOYEE_UNILATERAL_TERMINATION,
        ),
    )
)
