"""Deterministic, bounded clarification over missing-fact detector output."""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from vietnamese_labor_law_assistant.decision_support.issue_registry import FactKey
from vietnamese_labor_law_assistant.decision_support.issues import IssueCode
from vietnamese_labor_law_assistant.decision_support.missing_facts import (
    AggregatedFieldNeed,
    FactConflict,
    IssueMissingFactResult,
    MissingFactResult,
    RequirementGapReason,
    RequirementStatus,
)

DEFAULT_MAX_QUESTIONS_PER_ROUND = 3


class ClarificationPriorityPolicy(StrEnum):
    """Closed ordering policies; the legacy value exists only for frozen regressions."""

    LEGAL_INFORMATION_VALUE = "LEGAL_INFORMATION_VALUE"
    LEGACY_REGISTRY_ORDER = "LEGACY_REGISTRY_ORDER"


class ClarificationReasonCode(StrEnum):
    """Stable machine reasons for a bounded clarification result."""

    NO_MISSING_FACTS = "NO_MISSING_FACTS"
    CRITICAL_FACTS_MISSING = "CRITICAL_FACTS_MISSING"
    REQUIRED_FACTS_MISSING = "REQUIRED_FACTS_MISSING"
    CONFLICTING_FACTS = "CONFLICTING_FACTS"


class ClarificationErrorCode(StrEnum):
    """Fail-closed errors for malformed or unsupported clarification input."""

    INVALID_QUESTION_BUDGET = "INVALID_QUESTION_BUDGET"
    INVALID_PREVIOUS_REQUESTED_FIELD = "INVALID_PREVIOUS_REQUESTED_FIELD"
    MALFORMED_MISSING_FACT_RESULT = "MALFORMED_MISSING_FACT_RESULT"
    MISSING_QUESTION_TEMPLATE = "MISSING_QUESTION_TEMPLATE"


class ClarificationError(ValueError):
    """Typed domain error raised when safe clarification cannot be produced."""

    def __init__(self, code: ClarificationErrorCode) -> None:
        self.code = code
        super().__init__(code.value)


class ClarificationQuestion(BaseModel):
    """One neutral question for one deduplicated missing field."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    fact_key: FactKey
    question: str = Field(min_length=1, max_length=600)
    critical: bool
    related_issue_codes: tuple[IssueCode, ...] = Field(min_length=1)
    requirement_reasons: tuple[RequirementGapReason, ...] = Field(min_length=1)
    priority: int = Field(ge=1)


class ClarificationResult(BaseModel):
    """Bounded clarification round without legal analysis or conclusions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    reason_code: ClarificationReasonCode
    fields_needed: tuple[AggregatedFieldNeed, ...]
    conflicts: tuple[FactConflict, ...] = ()
    questions: tuple[ClarificationQuestion, ...]

    @model_validator(mode="after")
    def validate_round_contract(self) -> ClarificationResult:
        question_keys = tuple(question.fact_key for question in self.questions)
        if len(question_keys) != len(set(question_keys)):
            raise ValueError("clarification question fields must be unique")
        allowed_question_keys = {field.fact_key for field in self.fields_needed}
        allowed_question_keys.update(
            fact_key for conflict in self.conflicts for fact_key in conflict.resolution_fact_keys
        )
        if not set(question_keys).issubset(allowed_question_keys):
            raise ValueError(
                "clarification questions must target gaps or conflict resolution fields"
            )
        if tuple(question.priority for question in self.questions) != tuple(
            range(1, len(self.questions) + 1)
        ):
            raise ValueError("clarification priorities must be contiguous")
        if (
            not self.fields_needed
            and not self.conflicts
            and (self.reason_code is not ClarificationReasonCode.NO_MISSING_FACTS or self.questions)
        ):
            raise ValueError("no missing facts must produce no questions")
        if (self.fields_needed or self.conflicts) and (
            self.reason_code is ClarificationReasonCode.NO_MISSING_FACTS
        ):
            raise ValueError("gaps or conflicts require a clarification reason")
        if self.conflicts and self.reason_code is not ClarificationReasonCode.CONFLICTING_FACTS:
            raise ValueError("fact conflicts require the conflict reason")
        return self


_QUESTION_TEMPLATES: dict[FactKey, str] = {
    FactKey.CONTRACT_TYPE: (
        "Hợp đồng lao động thuộc loại không xác định thời hạn, xác định thời hạn dưới 12 "
        "tháng, hay xác định thời hạn từ 12 đến 36 tháng?"
    ),
    FactKey.CONTRACT_START_DATE: (
        "Ngày bắt đầu của khoảng thời gian hợp đồng cần xem xét là ngày nào?"
    ),
    FactKey.CONTRACT_END_DATE: (
        "Ngày kết thúc của khoảng thời gian hợp đồng cần xem xét là ngày nào?"
    ),
    FactKey.NOTICE_SPECIAL_CASE: (
        "Vui lòng mô tả các tình tiết cụ thể của việc nghỉ có thể liên quan đến trường hợp "
        "đặc biệt về báo trước."
    ),
    FactKey.EMPLOYEE_ROLE: (
        "Công việc hoặc chức danh của bạn là gì? Vui lòng nêu thêm nếu công việc có tính "
        "chất đặc thù."
    ),
    FactKey.WAGE_PAYMENT_DUE_DATE: (
        "Khoản lương này đến hạn phải trả vào thời điểm nào theo kỳ trả lương đã thỏa thuận?"
    ),
    FactKey.WAGE_PAYMENT_STATUS: (
        "Đến hiện tại khoản lương đến hạn vẫn chưa được trả, hay đã được trả nhưng bị chậm?"
    ),
    FactKey.WAGE_DELAY_FORCE_MAJEURE: (
        "Doanh nghiệp có nêu sự kiện bất khả kháng và các biện pháp khắc phục liên quan đến việc "
        "chậm trả lương hay không?"
    ),
    FactKey.INTENDED_TERMINATION_REFERENCE_DATE: (
        "Mốc thời gian tham chiếu cho ngày dự định chấm dứt hợp đồng là ngày nào?"
    ),
}

_CONFLICT_QUESTION_TEMPLATES: dict[FactKey, str] = {
    FactKey.CONTRACT_TYPE: (
        "Bạn xác nhận hợp đồng là không xác định thời hạn hay xác định thời hạn?"
    ),
    FactKey.CONTRACT_END_DATE: (
        "Ngày kết thúc đã nêu là ngày hết hạn của hợp đồng hay là một mốc thời gian khác?"
    ),
}

_LEGAL_INFORMATION_VALUE: dict[FactKey, int] = {
    FactKey.CONTRACT_TYPE: 100,
    FactKey.NOTICE_SPECIAL_CASE: 90,
    FactKey.WAGE_PAYMENT_DUE_DATE: 90,
    FactKey.WAGE_PAYMENT_STATUS: 85,
    FactKey.WAGE_DELAY_FORCE_MAJEURE: 80,
    FactKey.EMPLOYEE_ROLE: 70,
    FactKey.INTENDED_TERMINATION_REFERENCE_DATE: 60,
    FactKey.CONTRACT_END_DATE: 40,
    FactKey.CONTRACT_START_DATE: 30,
}


class TargetedClarificationBuilder:
    """Select neutral questions from deterministic missing-fact metadata."""

    def build(
        self,
        missing_facts: MissingFactResult,
        *,
        previously_requested_fields: Sequence[FactKey | str] = (),
        max_questions: int = DEFAULT_MAX_QUESTIONS_PER_ROUND,
        priority_policy: ClarificationPriorityPolicy = (
            ClarificationPriorityPolicy.LEGAL_INFORMATION_VALUE
        ),
    ) -> ClarificationResult:
        if isinstance(max_questions, bool) or max_questions < 1:
            raise ClarificationError(ClarificationErrorCode.INVALID_QUESTION_BUDGET)
        _validate_missing_fact_result(missing_facts)
        previous = _normalize_previous_fields(previously_requested_fields)

        if not missing_facts.fields_needed and not missing_facts.conflicts:
            return ClarificationResult(
                reason_code=ClarificationReasonCode.NO_MISSING_FACTS,
                fields_needed=(),
                conflicts=(),
                questions=(),
            )

        ranked = sorted(
            enumerate(missing_facts.fields_needed),
            key=lambda item: (
                not bool(item[1].critical_for_issues),
                -len(item[1].required_by_issues),
                -_LEGAL_INFORMATION_VALUE.get(item[1].fact_key, 0)
                if priority_policy is ClarificationPriorityPolicy.LEGAL_INFORMATION_VALUE
                else 0,
                item[0],
            ),
        )
        conflict_questions = _build_conflict_questions(
            missing_facts.conflicts,
            previous,
            max_questions,
        )
        selected = tuple(
            field_need
            for _, field_need in ranked
            if field_need.fact_key not in previous
            and field_need.fact_key not in {question.fact_key for question in conflict_questions}
        )[: max_questions - len(conflict_questions)]
        gap_questions = tuple(
            _build_question(priority, field_need, missing_facts)
            for priority, field_need in enumerate(
                selected,
                start=len(conflict_questions) + 1,
            )
        )
        questions = (*conflict_questions, *gap_questions)
        return ClarificationResult(
            reason_code=(
                ClarificationReasonCode.CONFLICTING_FACTS
                if missing_facts.conflicts
                else ClarificationReasonCode.CRITICAL_FACTS_MISSING
                if missing_facts.critical_missing
                else ClarificationReasonCode.REQUIRED_FACTS_MISSING
            ),
            fields_needed=missing_facts.fields_needed,
            conflicts=missing_facts.conflicts,
            questions=questions,
        )


def _normalize_previous_fields(fields: Sequence[FactKey | str]) -> frozenset[FactKey]:
    normalized: set[FactKey] = set()
    for field in fields:
        try:
            normalized.add(field if isinstance(field, FactKey) else FactKey(field))
        except ValueError as error:
            raise ClarificationError(
                ClarificationErrorCode.INVALID_PREVIOUS_REQUESTED_FIELD
            ) from error
    return frozenset(normalized)


def _validate_missing_fact_result(result: MissingFactResult) -> None:
    if not result.issue_results:
        raise ClarificationError(ClarificationErrorCode.MALFORMED_MISSING_FACT_RESULT)

    issue_codes = tuple(issue.issue_code for issue in result.issue_results)
    if len(issue_codes) != len(set(issue_codes)):
        raise ClarificationError(ClarificationErrorCode.MALFORMED_MISSING_FACT_RESULT)

    expected_fields = _expected_fields_needed(result.issue_results)
    if result.fields_needed != expected_fields:
        raise ClarificationError(ClarificationErrorCode.MALFORMED_MISSING_FACT_RESULT)
    if result.critical_missing != any(issue.critical_missing for issue in result.issue_results):
        raise ClarificationError(ClarificationErrorCode.MALFORMED_MISSING_FACT_RESULT)
    conflict_codes = tuple(conflict.code for conflict in result.conflicts)
    if len(conflict_codes) != len(set(conflict_codes)):
        raise ClarificationError(ClarificationErrorCode.MALFORMED_MISSING_FACT_RESULT)


def _expected_fields_needed(
    issue_results: tuple[IssueMissingFactResult, ...],
) -> tuple[AggregatedFieldNeed, ...]:
    field_order: list[FactKey] = []
    required_by: dict[FactKey, list[IssueCode]] = {}
    critical_for: dict[FactKey, list[IssueCode]] = {}

    for issue in issue_results:
        _validate_issue_result(issue)
        for assessment in issue.requirements:
            if assessment.status is RequirementStatus.SATISFIED:
                continue
            if assessment.fact_key not in required_by:
                field_order.append(assessment.fact_key)
                required_by[assessment.fact_key] = []
                critical_for[assessment.fact_key] = []
            required_by[assessment.fact_key].append(issue.issue_code)
            if assessment.critical:
                critical_for[assessment.fact_key].append(issue.issue_code)

    return tuple(
        AggregatedFieldNeed(
            fact_key=fact_key,
            required_by_issues=tuple(required_by[fact_key]),
            critical_for_issues=tuple(critical_for[fact_key]),
        )
        for fact_key in field_order
    )


def _validate_issue_result(issue: IssueMissingFactResult) -> None:
    assessment_keys = tuple(assessment.fact_key for assessment in issue.requirements)
    if not assessment_keys or len(assessment_keys) != len(set(assessment_keys)):
        raise ClarificationError(ClarificationErrorCode.MALFORMED_MISSING_FACT_RESULT)

    satisfied = tuple(
        assessment.fact_key
        for assessment in issue.requirements
        if assessment.status is RequirementStatus.SATISFIED
    )
    missing = tuple(
        assessment.fact_key
        for assessment in issue.requirements
        if assessment.status is not RequirementStatus.SATISFIED
    )
    critical_missing = tuple(
        assessment.fact_key
        for assessment in issue.requirements
        if assessment.critical and assessment.status is not RequirementStatus.SATISFIED
    )
    if (
        issue.satisfied_fields != satisfied
        or issue.missing_fields != missing
        or issue.critical_missing_fields != critical_missing
        or issue.critical_missing != bool(critical_missing)
    ):
        raise ClarificationError(ClarificationErrorCode.MALFORMED_MISSING_FACT_RESULT)


def _build_question(
    priority: int,
    field_need: AggregatedFieldNeed,
    missing_facts: MissingFactResult,
) -> ClarificationQuestion:
    template = _QUESTION_TEMPLATES.get(field_need.fact_key)
    if template is None:
        raise ClarificationError(ClarificationErrorCode.MISSING_QUESTION_TEMPLATE)

    present_reasons = {
        reason
        for issue in missing_facts.issue_results
        if issue.issue_code in field_need.required_by_issues
        for assessment in issue.requirements
        if assessment.fact_key is field_need.fact_key
        and assessment.status is not RequirementStatus.SATISFIED
        for reason in assessment.gap_reasons
    }
    reasons = tuple(reason for reason in RequirementGapReason if reason in present_reasons)
    if not reasons:
        raise ClarificationError(ClarificationErrorCode.MALFORMED_MISSING_FACT_RESULT)

    return ClarificationQuestion(
        fact_key=field_need.fact_key,
        question=template,
        critical=bool(field_need.critical_for_issues),
        related_issue_codes=field_need.required_by_issues,
        requirement_reasons=reasons,
        priority=priority,
    )


def _build_conflict_questions(
    conflicts: tuple[FactConflict, ...],
    previous: frozenset[FactKey],
    max_questions: int,
) -> tuple[ClarificationQuestion, ...]:
    fields: list[tuple[FactKey, list[IssueCode]]] = []
    by_key: dict[FactKey, list[IssueCode]] = {}
    for conflict in conflicts:
        for fact_key in conflict.resolution_fact_keys:
            if fact_key in previous:
                continue
            if fact_key not in by_key:
                by_key[fact_key] = []
                fields.append((fact_key, by_key[fact_key]))
            if conflict.issue_code not in by_key[fact_key]:
                by_key[fact_key].append(conflict.issue_code)

    selected = fields[:max_questions]
    questions: list[ClarificationQuestion] = []
    for priority, (fact_key, issue_codes) in enumerate(selected, start=1):
        template = _CONFLICT_QUESTION_TEMPLATES.get(fact_key)
        if template is None:
            raise ClarificationError(ClarificationErrorCode.MISSING_QUESTION_TEMPLATE)
        questions.append(
            ClarificationQuestion(
                fact_key=fact_key,
                question=template,
                critical=True,
                related_issue_codes=tuple(issue_codes),
                requirement_reasons=(RequirementGapReason.CONFLICTING_FACTS,),
                priority=priority,
            )
        )
    return tuple(questions)
