from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from vietnamese_labor_law_assistant.evaluation.week10_guardrails import (
    Week10Case,
    coverage_summary,
    load_week10_cases,
    run_week10_cases,
    validate_provenance,
    validate_week10_cases,
    verify_week10_report,
    week10_metrics,
)
from vietnamese_labor_law_assistant.guardrails.service import CitationGuardrailService
from vietnamese_labor_law_assistant.guardrails.source_registry import CanonicalSourceRegistry

DATASET = Path("data/evaluation/week10_guardrail_cases.jsonl")
SOURCE = Path("data/processed/labor_law_clauses.jsonl")


def raw_cases() -> list[dict[str, Any]]:
    return [json.loads(line) for line in DATASET.read_text(encoding="utf-8").splitlines()]


def test_real_dataset_has_complete_matrix_and_passes_verification() -> None:
    registry = CanonicalSourceRegistry(SOURCE)
    cases = load_week10_cases(DATASET, registry)
    rows = run_week10_cases(cases, CitationGuardrailService(registry))
    summary = coverage_summary(cases)
    provenance = validate_provenance(cases, registry)
    report = {
        "status": "PASS",
        "case_count": len(cases),
        **summary,
        "provenance_validation": provenance,
        "metrics": week10_metrics(cases, rows),
    }
    verify_week10_report(report, cases)
    assert summary["missing_categories"] == []
    assert provenance["failed"] == 0


def test_loader_rejects_missing_category_and_duplicate_id() -> None:
    rows = raw_cases()
    unique_category = next(row for row in rows if row["category"] == "wrong_point")
    unique_category["category"] = "valid_full_support"
    cases = [Week10Case.model_validate(row) for row in rows]
    with pytest.raises(ValueError, match="missing Week 10 categories"):
        validate_week10_cases(cases)

    cases = load_week10_cases(DATASET)
    cases[-1] = cases[-1].model_copy(update={"case_id": cases[0].case_id})
    with pytest.raises(ValueError, match="40 unique cases"):
        validate_week10_cases(cases)


def test_contract_rejects_invalid_route_and_missing_evidence_metadata() -> None:
    calculator = next(row for row in raw_cases() if row["route"] == "CALCULATOR_ONLY")
    calculator["route"] = "UNKNOWN"
    with pytest.raises(ValidationError):
        Week10Case.model_validate(calculator)

    calculator = next(row for row in raw_cases() if row["route"] == "CALCULATOR_ONLY")
    calculator["calculator_evidence"] = []
    with pytest.raises(ValidationError, match="calculator route requires calculator evidence"):
        Week10Case.model_validate(calculator)

    combined = next(row for row in raw_cases() if row["route"] == "RETRIEVAL_AND_CALCULATOR")
    combined["retrieved_context_ids"] = []
    with pytest.raises(ValidationError, match="combined route requires"):
        Week10Case.model_validate(combined)


def test_contract_rejects_missing_judge_behavior_and_calculator_provenance() -> None:
    judge = next(row for row in raw_cases() if row["category"] == "judge_timeout")
    judge["judge_behavior"] = "NOT_USED"
    with pytest.raises(ValidationError, match="judge failure category"):
        Week10Case.model_validate(judge)

    calculator = next(row for row in raw_cases() if row["route"] == "CALCULATOR_ONLY")
    calculator["provenance"]["calculator_source_chunk_id"] = None
    with pytest.raises(ValidationError, match="calculator provenance"):
        Week10Case.model_validate(calculator)


def test_loader_rejects_invalid_canonical_provenance_and_missing_status() -> None:
    rows = raw_cases()
    supported = next(row for row in rows if row["category"] == "valid_full_support")
    supported["provenance"]["canonical_chunk_ids"] = ["ll_missing_fixture"]
    cases = [Week10Case.model_validate(row) for row in rows]
    with pytest.raises(ValueError, match="provenance validation failed"):
        validate_week10_cases(cases, CanonicalSourceRegistry(SOURCE))

    rows = raw_cases()
    for row in rows:
        if row["expected_status"] == "PARTIALLY_SUPPORTED":
            row["expected_status"] = "UNSUPPORTED"
    cases = [Week10Case.model_validate(row) for row in rows]
    with pytest.raises(ValueError, match="all verification statuses"):
        validate_week10_cases(cases)


def test_verifier_rejects_false_supported_rate() -> None:
    registry = CanonicalSourceRegistry(SOURCE)
    cases = load_week10_cases(DATASET, registry)
    rows = run_week10_cases(cases, CitationGuardrailService(registry))
    report = {
        "status": "PASS",
        "case_count": len(cases),
        **coverage_summary(cases),
        "provenance_validation": validate_provenance(cases, registry),
        "metrics": week10_metrics(cases, rows),
    }
    report["metrics"]["false_supported_rate"] = 0.1
    with pytest.raises(ValueError, match="verification invariants"):
        verify_week10_report(report, cases)
