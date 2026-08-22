"""Development dataset contracts, deterministic metrics, and runners for Case Intake."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from statistics import fmean

from pydantic import BaseModel, ConfigDict, Field, model_validator

from vietnamese_labor_law_assistant.common.settings import Settings
from vietnamese_labor_law_assistant.decision_support.intake import (
    OpenAIStructuredCaseIntakeExtractor,
    validate_case_intake_result,
)
from vietnamese_labor_law_assistant.decision_support.issues import IssueCode
from vietnamese_labor_law_assistant.decision_support.models import (
    CaseFact,
    CaseIntakeInput,
    CaseIntakeResult,
)
from vietnamese_labor_law_assistant.decision_support.protocols import CaseIntakeExtractor


class CaseIntakeEvaluationCase(BaseModel):
    """One human-reviewable development label for the Week-2 Case Intake contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=r"^dsi-dev-\d{3}$")
    dataset_version: str = Field(pattern=r"^v1_1_dev$")
    source_text: str = Field(min_length=1, max_length=16000)
    source_ref: str = Field(pattern=r"^user_message:[A-Za-z0-9_-]{1,80}$")
    expected_result: CaseIntakeResult
    critical_fact_ids: list[str] = Field(default_factory=list, max_length=50)
    date_fact_ids: list[str] = Field(default_factory=list, max_length=50)
    money_fact_ids: list[str] = Field(default_factory=list, max_length=50)
    critical_issue_codes: list[IssueCode] = Field(default_factory=list, max_length=2)
    tags: list[str] = Field(default_factory=list, max_length=12)
    human_validated: bool = False
    review_status: str = Field(pattern=r"^(PENDING|PASS|NEEDS_REVISION|REJECTED)$")
    review_notes: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def validate_labels(self) -> CaseIntakeEvaluationCase:
        validate_case_intake_result(
            CaseIntakeInput(source_text=self.source_text, source_ref=self.source_ref),
            self.expected_result,
        )
        fact_ids = {fact.fact_id for fact in self.expected_result.facts}
        for identifiers, name in (
            (self.critical_fact_ids, "critical_fact_ids"),
            (self.date_fact_ids, "date_fact_ids"),
            (self.money_fact_ids, "money_fact_ids"),
        ):
            if len(identifiers) != len(set(identifiers)) or not set(identifiers).issubset(fact_ids):
                raise ValueError(f"{name} must be unique expected fact IDs")
        expected_issues = {issue.issue_code for issue in self.expected_result.candidate_issues}
        if len(self.critical_issue_codes) != len(set(self.critical_issue_codes)) or not set(
            self.critical_issue_codes
        ).issubset(expected_issues):
            raise ValueError("critical_issue_codes must be unique expected candidate issues")
        if self.human_validated and self.review_status != "PASS":
            raise ValueError("human_validated cases require PASS review status")
        return self


class CaseIntakeMetrics(BaseModel):
    """Deterministic Case Intake metrics; ``None`` means a zero denominator."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    overall_fact_f1: float | None
    critical_field_recall: float | None
    date_exact_match: float | None
    money_exact_match: float | None
    source_span_accuracy: float | None
    hallucinated_fact_rate: float | None
    candidate_issue_macro_f1: float | None
    critical_issue_recall: float | None


class CaseIntakePrediction(BaseModel):
    """One sanitized prediction row, including a fail-closed extraction error when present."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    result: CaseIntakeResult | None = None
    error_type: str | None = None


class CaseIntakeEvaluationRun(BaseModel):
    """Offline or explicitly live run output; metrics never use an LLM judge."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    predictions: list[CaseIntakePrediction]
    metrics: CaseIntakeMetrics


FactSignature = tuple[str, str, str]


def load_case_intake_evaluation_cases(path: Path) -> list[CaseIntakeEvaluationCase]:
    """Load and validate the unfrozen Week-2 development dataset."""

    cases = [
        CaseIntakeEvaluationCase.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    validate_case_intake_evaluation_cases(cases)
    return cases


def validate_case_intake_evaluation_cases(cases: Sequence[CaseIntakeEvaluationCase]) -> None:
    """Require coverage instead of an arbitrary development-set size."""

    identifiers = [case.case_id for case in cases]
    if not cases or len(identifiers) != len(set(identifiers)):
        raise ValueError("Case Intake evaluation cases require unique non-empty IDs")
    issue_coverage = {
        issue.issue_code for case in cases for issue in case.expected_result.candidate_issues
    }
    missing_issues = set(IssueCode) - issue_coverage
    if missing_issues:
        missing_values = sorted(item.value for item in missing_issues)
        raise ValueError(f"missing implemented issue coverage: {missing_values}")
    if not any(len(case.expected_result.candidate_issues) > 1 for case in cases):
        raise ValueError("Case Intake development dataset requires a multi-issue case")
    if not any(not case.expected_result.candidate_issues for case in cases):
        raise ValueError("Case Intake development dataset requires a no-supported-issue case")
    if not any(case.date_fact_ids for case in cases):
        raise ValueError("Case Intake development dataset requires a date fact")
    if not any(case.money_fact_ids for case in cases):
        raise ValueError("Case Intake development dataset requires a money fact")
    if not any("adversarial" in case.tags for case in cases):
        raise ValueError("Case Intake development dataset requires an adversarial case")


def case_intake_dataset_summary(cases: Sequence[CaseIntakeEvaluationCase]) -> dict[str, object]:
    """Return review and issue coverage metadata without fabricating a model score."""

    issue_coverage = {
        issue.value: sum(
            issue in {candidate.issue_code for candidate in case.expected_result.candidate_issues}
            for case in cases
        )
        for issue in IssueCode
    }
    return {
        "record_count": len(cases),
        "issue_coverage": issue_coverage,
        "human_validated_count": sum(case.human_validated for case in cases),
        "frozen_final": False,
    }


def case_intake_metrics(
    cases: Sequence[CaseIntakeEvaluationCase],
    predictions: Mapping[str, CaseIntakeResult | None],
) -> CaseIntakeMetrics:
    """Compute deterministic fact, source, and candidate-issue metrics.

    Fact F1 matches ``(fact_key, fact_type, raw_value)`` within the same case. Normalized values
    and source spans are deliberately scored separately. A missing prediction is an empty result.
    Every metric with a zero denominator returns ``None`` rather than a perfect score.
    """

    unknown_prediction_ids = set(predictions) - {case.case_id for case in cases}
    if unknown_prediction_ids:
        raise ValueError("predictions contain unknown case IDs")

    expected_fact_keys: set[tuple[str, FactSignature]] = set()
    predicted_fact_keys: set[tuple[str, FactSignature]] = set()
    critical_expected = critical_found = 0
    date_total = date_exact = money_total = money_exact = 0
    span_total = span_correct = 0
    predicted_fact_count = hallucinated_facts = 0
    critical_issue_total = critical_issue_found = 0
    issue_scores: list[float] = []

    for case in cases:
        prediction = predictions.get(case.case_id)
        predicted_facts = prediction.facts if prediction is not None else []
        expected_by_signature = {_fact_signature(fact): fact for fact in case.expected_result.facts}
        predicted_by_signature = {_fact_signature(fact): fact for fact in predicted_facts}
        expected_fact_keys.update((case.case_id, signature) for signature in expected_by_signature)
        predicted_fact_keys.update(
            (case.case_id, signature) for signature in predicted_by_signature
        )
        predicted_fact_count += len(predicted_facts)
        hallucinated_facts += sum(
            signature not in expected_by_signature for signature in predicted_by_signature
        )

        expected_by_id = {fact.fact_id: fact for fact in case.expected_result.facts}
        for fact_id in case.critical_fact_ids:
            critical_expected += 1
            critical_found += _fact_signature(expected_by_id[fact_id]) in predicted_by_signature
        for fact_id in case.date_fact_ids:
            date_total += 1
            date_exact += _normalized_value_matches(expected_by_id[fact_id], predicted_by_signature)
        for fact_id in case.money_fact_ids:
            money_total += 1
            money_exact += _normalized_value_matches(
                expected_by_id[fact_id], predicted_by_signature
            )
        for expected in case.expected_result.facts:
            span_total += 1
            actual = predicted_by_signature.get(_fact_signature(expected))
            span_correct += actual is not None and actual.source_span == expected.source_span

        predicted_issue_codes = (
            {issue.issue_code for issue in prediction.candidate_issues} if prediction else set()
        )
        for issue_code in case.critical_issue_codes:
            critical_issue_total += 1
            critical_issue_found += issue_code in predicted_issue_codes

    for issue_code in IssueCode:
        true_positive = false_positive = false_negative = 0
        for case in cases:
            prediction = predictions.get(case.case_id)
            expected = issue_code in {
                item.issue_code for item in case.expected_result.candidate_issues
            }
            actual = (
                issue_code in {item.issue_code for item in prediction.candidate_issues}
                if prediction
                else False
            )
            true_positive += int(expected and actual)
            false_positive += int(not expected and actual)
            false_negative += int(expected and not actual)
        score = _f1(true_positive, false_positive, false_negative)
        if score is not None:
            issue_scores.append(score)

    true_positive = len(expected_fact_keys & predicted_fact_keys)
    false_positive = len(predicted_fact_keys - expected_fact_keys)
    false_negative = len(expected_fact_keys - predicted_fact_keys)
    return CaseIntakeMetrics(
        overall_fact_f1=_f1(true_positive, false_positive, false_negative),
        critical_field_recall=_ratio(critical_found, critical_expected),
        date_exact_match=_ratio(date_exact, date_total),
        money_exact_match=_ratio(money_exact, money_total),
        source_span_accuracy=_ratio(span_correct, span_total),
        hallucinated_fact_rate=_ratio(hallucinated_facts, predicted_fact_count),
        candidate_issue_macro_f1=fmean(issue_scores) if issue_scores else None,
        critical_issue_recall=_ratio(critical_issue_found, critical_issue_total),
    )


async def run_case_intake_evaluation(
    cases: Sequence[CaseIntakeEvaluationCase], extractor: CaseIntakeExtractor
) -> CaseIntakeEvaluationRun:
    """Run an injected extractor; offline fakes keep unit tests entirely local."""

    rows: list[CaseIntakePrediction] = []
    by_case: dict[str, CaseIntakeResult | None] = {}
    for case in cases:
        try:
            result = await extractor.extract(
                CaseIntakeInput(source_text=case.source_text, source_ref=case.source_ref)
            )
            rows.append(CaseIntakePrediction(case_id=case.case_id, result=result))
            by_case[case.case_id] = result
        except Exception as exc:
            rows.append(CaseIntakePrediction(case_id=case.case_id, error_type=type(exc).__name__))
            by_case[case.case_id] = None
    return CaseIntakeEvaluationRun(
        predictions=rows,
        metrics=case_intake_metrics(cases, by_case),
    )


async def run_live_case_intake_evaluation(
    cases: Sequence[CaseIntakeEvaluationCase], settings: Settings
) -> CaseIntakeEvaluationRun:
    """Explicit live-only profile; callers must opt in and supply configured Settings."""

    if not settings.llm_configured:
        raise RuntimeError("LIVE_EVAL_NOT_CONFIGURED")
    return await run_case_intake_evaluation(cases, OpenAIStructuredCaseIntakeExtractor(settings))


def _fact_signature(fact: CaseFact) -> FactSignature:
    return fact.fact_key, fact.fact_type, fact.raw_value


def _normalized_value_matches(
    expected: CaseFact, predicted_by_signature: Mapping[FactSignature, CaseFact]
) -> bool:
    actual = predicted_by_signature.get(_fact_signature(expected))
    return actual is not None and actual.normalized_value == expected.normalized_value


def _f1(true_positive: int, false_positive: int, false_negative: int) -> float | None:
    return _ratio(2 * true_positive, 2 * true_positive + false_positive + false_negative)


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None
