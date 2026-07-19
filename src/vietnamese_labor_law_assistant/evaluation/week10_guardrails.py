"""Typed Week 10 dataset, coverage validation, metrics, and offline runner."""

from __future__ import annotations

import json
import time
from collections import Counter
from enum import StrEnum
from pathlib import Path
from statistics import mean
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from vietnamese_labor_law_assistant.guardrails.enums import ReasonCode, VerificationStatus
from vietnamese_labor_law_assistant.guardrails.judge import (
    JudgeDecision,
    JudgeInvalidOutputError,
    JudgeUnavailableError,
)
from vietnamese_labor_law_assistant.guardrails.models import AtomicClaim, EvidenceContext
from vietnamese_labor_law_assistant.guardrails.service import CitationGuardrailService
from vietnamese_labor_law_assistant.guardrails.source_registry import CanonicalSourceRegistry


class Week10Category(StrEnum):
    VALID_FULL_SUPPORT = "valid_full_support"
    MISSING_CITATION = "missing_citation"
    NONEXISTENT_CHUNK = "nonexistent_chunk"
    CITATION_NOT_IN_CONTEXT = "citation_not_in_context"
    WRONG_CLAUSE = "wrong_clause"
    WRONG_POINT = "wrong_point"
    NUMERIC_CONTRADICTION = "numeric_contradiction"
    PARTIAL_COMPOUND_CLAIM = "partial_compound_claim"
    KEYWORD_OVERLAP_WRONG_MEANING = "keyword_overlap_wrong_meaning"
    EMPTY_CONTEXT = "empty_context"
    DUPLICATE_CITATION = "duplicate_citation"
    MALFORMED_CITATION = "malformed_citation"
    CALCULATOR_ONLY_SUPPORTED = "calculator_only_supported"
    CALCULATOR_NUMERIC_CONTRADICTION = "calculator_numeric_contradiction"
    RETRIEVAL_AND_CALCULATOR_SUPPORTED = "retrieval_and_calculator_supported"
    OUT_OF_SCOPE_REFUSAL = "out_of_scope_refusal"
    JUDGE_TIMEOUT = "judge_timeout"
    JUDGE_INVALID_OUTPUT = "judge_invalid_output"
    MIXED_CLAIM_STATUS = "mixed_claim_status"
    EXTERNAL_REGULATION_REQUIRED = "external_regulation_required"
    UNICODE_SPACING_VARIANT = "unicode_spacing_variant"
    LEGAL_REFERENCE_MATCH_BUT_SEMANTIC_UNSUPPORTED = (
        "legal_reference_match_but_semantic_unsupported"
    )


class Week10Route(StrEnum):
    RETRIEVAL_ONLY = "RETRIEVAL_ONLY"
    CALCULATOR_ONLY = "CALCULATOR_ONLY"
    RETRIEVAL_AND_CALCULATOR = "RETRIEVAL_AND_CALCULATOR"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    DIRECT_GUARDRAIL = "DIRECT_GUARDRAIL"


class JudgeBehavior(StrEnum):
    NOT_USED = "NOT_USED"
    SUPPORTED = "SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    INSUFFICIENT_CONTEXT = "INSUFFICIENT_CONTEXT"
    TIMEOUT = "TIMEOUT"
    INVALID_OUTPUT = "INVALID_OUTPUT"
    TRANSPORT_ERROR = "TRANSPORT_ERROR"
    UNAVAILABLE = "UNAVAILABLE"


class CaseProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")
    canonical_chunk_ids: list[str] = Field(default_factory=list)
    registry: str = "labor_law_clauses_snapshot"
    article: int | None = None
    clause: int | None = None
    point: str | None = None
    calculator_source_chunk_id: str | None = None


class Week10Case(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str = Field(pattern=r"^w10-\d{3}$")
    category: Week10Category
    route: Week10Route
    claim: AtomicClaim
    claims: list[AtomicClaim] = Field(default_factory=list)
    contexts: list[EvidenceContext] = Field(default_factory=list)
    retrieved_context_ids: list[str] = Field(default_factory=list)
    calculator_evidence: list[dict[str, Any]] = Field(default_factory=list)
    expected_status: VerificationStatus
    expected_reason_codes: list[ReasonCode] = Field(default_factory=list)
    provenance: CaseProvenance
    judge_behavior: JudgeBehavior = JudgeBehavior.NOT_USED
    tags: list[str] = Field(default_factory=list)
    out_of_scope_refusal: bool = False

    @model_validator(mode="after")
    def validate_route_evidence(self) -> Week10Case:
        if self.route is Week10Route.CALCULATOR_ONLY and not self.calculator_evidence:
            raise ValueError("calculator route requires calculator evidence")
        if self.route is Week10Route.RETRIEVAL_AND_CALCULATOR and (
            not self.calculator_evidence or not self.retrieved_context_ids
        ):
            raise ValueError("combined route requires retrieval and calculator evidence")
        if self.category in {
            Week10Category.JUDGE_TIMEOUT,
            Week10Category.JUDGE_INVALID_OUTPUT,
        } and (self.judge_behavior is JudgeBehavior.NOT_USED):
            raise ValueError("judge failure category requires judge behavior")
        if (
            self.expected_status is not VerificationStatus.SUPPORTED
            and not self.expected_reason_codes
        ):
            raise ValueError("non-supported case requires an expected reason code")
        if (
            self.route
            in {
                Week10Route.CALCULATOR_ONLY,
                Week10Route.RETRIEVAL_AND_CALCULATOR,
            }
            and not self.provenance.calculator_source_chunk_id
        ):
            raise ValueError("calculator route requires calculator provenance")
        return self

    @property
    def all_claims(self) -> list[AtomicClaim]:
        return self.claims or [self.claim]


def coverage_summary(cases: list[Week10Case]) -> dict[str, object]:
    categories = Counter(case.category.value for case in cases)
    routes = Counter(case.route.value for case in cases)
    statuses = Counter(case.expected_status.value for case in cases)
    judges = Counter(case.judge_behavior.value for case in cases)
    missing = sorted(set(item.value for item in Week10Category) - set(categories))
    return {
        "category_coverage": dict(sorted(categories.items())),
        "missing_categories": missing,
        "route_distribution": dict(sorted(routes.items())),
        "status_distribution": dict(sorted(statuses.items())),
        "judge_behavior_distribution": dict(sorted(judges.items())),
    }


def validate_provenance(
    cases: list[Week10Case], registry: CanonicalSourceRegistry
) -> dict[str, int]:
    checked = passed = failed = 0
    for case in cases:
        ids = list(dict.fromkeys(case.provenance.canonical_chunk_ids))
        if case.provenance.calculator_source_chunk_id:
            ids.append(case.provenance.calculator_source_chunk_id)
        for chunk_id in dict.fromkeys(ids):
            checked += 1
            exists = registry.get(chunk_id) is not None
            expected_missing = case.category is Week10Category.NONEXISTENT_CHUNK
            if exists != expected_missing:
                passed += 1
            else:
                failed += 1
        if case.category is Week10Category.CITATION_NOT_IN_CONTEXT:
            checked += 1
            valid = bool(ids) and all(registry.get(item) is not None for item in ids)
            valid = valid and not set(ids).issubset(case.retrieved_context_ids)
            passed += int(valid)
            failed += int(not valid)
    return {"checked": checked, "passed": passed, "failed": failed}


def load_week10_cases(
    path: Path, registry: CanonicalSourceRegistry | None = None
) -> list[Week10Case]:
    cases = [
        Week10Case.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    validate_week10_cases(cases, registry)
    return cases


def validate_week10_cases(
    cases: list[Week10Case], registry: CanonicalSourceRegistry | None = None
) -> None:
    identifiers = [case.case_id for case in cases]
    if len(cases) < 40 or len(identifiers) != len(set(identifiers)):
        raise ValueError("Week 10 dataset requires at least 40 unique cases")
    summary = coverage_summary(cases)
    if summary["missing_categories"]:
        raise ValueError(f"missing Week 10 categories: {summary['missing_categories']}")
    required_routes = {
        Week10Route.RETRIEVAL_ONLY.value,
        Week10Route.CALCULATOR_ONLY.value,
        Week10Route.RETRIEVAL_AND_CALCULATOR.value,
        Week10Route.OUT_OF_SCOPE.value,
    }
    if not required_routes.issubset(cast(dict[str, int], summary["route_distribution"])):
        raise ValueError("Week 10 dataset must cover all Agent routes")
    if set(case.expected_status for case in cases) != set(VerificationStatus):
        raise ValueError("Week 10 dataset must cover all verification statuses")
    if registry and validate_provenance(cases, registry)["failed"]:
        raise ValueError("Week 10 provenance validation failed")


def run_week10_cases(
    cases: list[Week10Case], service: CitationGuardrailService
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for case in cases:
        started = time.perf_counter()
        case_service = _service_for_judge_behavior(case, service)
        result = case_service.verify(
            case.all_claims, case.contexts, out_of_scope_refusal=case.out_of_scope_refusal
        )
        reasons = [code.value for claim in result.claims for code in claim.reason_codes]
        if not result.claims:
            reasons.extend(result.warnings)
        rows.append(
            {
                "case_id": case.case_id,
                "category": case.category.value,
                "route": case.route.value,
                "expected_status": case.expected_status.value,
                "status": result.status.value,
                "reason_codes": sorted(set(reasons)),
                "citation_existence_correct": (
                    (ReasonCode.CITATION_NOT_FOUND.value in reasons)
                    == (case.category is Week10Category.NONEXISTENT_CHUNK)
                ),
                "retrieved_membership_correct": (
                    (ReasonCode.CITATION_NOT_IN_RETRIEVED_CONTEXT.value in reasons)
                    == (case.category is Week10Category.CITATION_NOT_IN_CONTEXT)
                ),
                "latency_ms": (time.perf_counter() - started) * 1000,
            }
        )
    return rows


class _AmbiguousFixtureScorer:
    def score(self, claim: str, evidence: str) -> float:
        del claim, evidence
        return 0.5


class _JudgeFixture:
    def __init__(self, behavior: JudgeBehavior) -> None:
        self.behavior = behavior

    def judge(self, claim: AtomicClaim, evidence: list[EvidenceContext]) -> JudgeDecision:
        del claim, evidence
        if self.behavior is JudgeBehavior.INVALID_OUTPUT:
            raise JudgeInvalidOutputError(ReasonCode.JUDGE_INVALID_OUTPUT.value)
        if self.behavior in {
            JudgeBehavior.TIMEOUT,
            JudgeBehavior.TRANSPORT_ERROR,
            JudgeBehavior.UNAVAILABLE,
        }:
            raise JudgeUnavailableError(ReasonCode.JUDGE_UNAVAILABLE.value)
        return JudgeDecision(
            status=VerificationStatus(self.behavior.value),
            reason="deterministic fixture decision",
        )


def _service_for_judge_behavior(
    case: Week10Case, service: CitationGuardrailService
) -> CitationGuardrailService:
    if case.judge_behavior is JudgeBehavior.NOT_USED:
        return service
    return CitationGuardrailService(
        service.registry,
        _AmbiguousFixtureScorer(),
        judge=_JudgeFixture(case.judge_behavior),
        lower_threshold=service.lower_threshold,
        high_threshold=service.high_threshold,
    )


def week10_metrics(cases: list[Week10Case], rows: list[dict[str, object]]) -> dict[str, object]:
    by_id = {str(row["case_id"]): row for row in rows}
    if set(by_id) != {case.case_id for case in cases}:
        raise ValueError("predictions must match dataset cases")
    per_class: dict[str, dict[str, float]] = {}
    for status in VerificationStatus:
        tp = sum(
            row["status"] == status.value and row["expected_status"] == status.value for row in rows
        )
        fp = sum(
            row["status"] == status.value and row["expected_status"] != status.value for row in rows
        )
        fn = sum(
            row["status"] != status.value and row["expected_status"] == status.value for row in rows
        )
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        per_class[status.value] = {
            "precision": precision,
            "recall": recall,
            "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
        }
    latencies = sorted(float(cast(float, row["latency_ms"])) for row in rows)
    reason_misses = sum(
        any(
            code.value not in cast(list[str], by_id[case.case_id]["reason_codes"])
            for code in case.expected_reason_codes
        )
        for case in cases
    )
    accuracy = sum(
        by_id[case.case_id]["status"] == case.expected_status.value for case in cases
    ) / len(cases)
    return {
        "citation_existence_accuracy": mean(
            bool(row["citation_existence_correct"]) for row in rows
        ),
        "retrieved_membership_accuracy": mean(
            bool(row["retrieved_membership_correct"]) for row in rows
        ),
        "claim_status_accuracy": accuracy,
        "macro_f1": mean(item["f1"] for item in per_class.values()),
        "per_class": per_class,
        "unsupported_detection_recall": per_class[VerificationStatus.UNSUPPORTED.value]["recall"],
        "insufficient_context_detection_recall": per_class[
            VerificationStatus.INSUFFICIENT_CONTEXT.value
        ]["recall"],
        "out_of_scope_refusal_accuracy": 1.0
        if all(
            by_id[c.case_id]["status"] == c.expected_status.value
            for c in cases
            if c.route is Week10Route.OUT_OF_SCOPE
        )
        else 0.0,
        "false_supported_rate": sum(
            row["status"] == "SUPPORTED" and row["expected_status"] != "SUPPORTED" for row in rows
        )
        / len(rows),
        "citation_support_rate": sum(row["status"] == "SUPPORTED" for row in rows) / len(rows),
        "mean_verification_latency_ms": mean(latencies),
        "p95_verification_latency_ms": latencies[max(0, int(len(latencies) * 0.95) - 1)],
        "error_timeout_count": 0,
        "required_reason_misses": reason_misses,
    }


def verify_week10_report(report: dict[str, Any], cases: list[Week10Case]) -> None:
    metrics = report.get("metrics", {})
    provenance = report.get("provenance_validation", {})
    failures = [
        report.get("status") != "PASS",
        report.get("case_count") != len(cases),
        bool(report.get("missing_categories")),
        provenance.get("failed") != 0,
        metrics.get("citation_existence_accuracy") != 1.0,
        metrics.get("retrieved_membership_accuracy") != 1.0,
        metrics.get("out_of_scope_refusal_accuracy") != 1.0,
        metrics.get("false_supported_rate") != 0.0,
        metrics.get("unsupported_detection_recall") != 1.0,
        float(metrics.get("claim_status_accuracy", 0)) < 0.95,
        metrics.get("required_reason_misses") != 0,
    ]
    if any(failures):
        raise ValueError("Week 10 verification invariants failed")


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def write_jsonl_atomic(path: Path, rows: list[dict[str, object]]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
    )
    temporary.replace(path)
