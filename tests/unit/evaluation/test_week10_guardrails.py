from __future__ import annotations

import hashlib
import json
import runpy
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from vietnamese_labor_law_assistant.evaluation.week10_guardrails import (
    CANONICAL_JSONL_SHA256_ALGORITHM,
    Week10Case,
    canonical_jsonl_sha256,
    coverage_summary,
    load_week10_cases,
    run_week10_cases,
    validate_provenance,
    validate_week10_cases,
    verify_week10_evidence,
    verify_week10_report,
    week10_metrics,
)
from vietnamese_labor_law_assistant.guardrails.service import CitationGuardrailService
from vietnamese_labor_law_assistant.guardrails.source_registry import CanonicalSourceRegistry

DATASET = Path("data/evaluation/week10_guardrail_cases.jsonl")
SOURCE = Path("data/processed/labor_law_clauses.jsonl")
METRICS = Path("evaluation/results/week10_guardrail_metrics.json")
MANIFEST = Path("evaluation/results/week10_guardrail_manifest.json")
ORPHAN_CHECKSUM = "e45b8c7b98670a4f9dd17635dd983794a013b901cca18c1b7fa6c9c42d4e534a"


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


def test_canonical_jsonl_checksum_is_cross_platform_and_preserves_utf8(tmp_path: Path) -> None:
    lf = tmp_path / "lf.jsonl"
    crlf = tmp_path / "crlf.jsonl"
    content = '{"text":"Điều 35","value":1}\n'
    lf.write_bytes(content.encode("utf-8"))
    crlf.write_bytes(content.replace("\n", "\r\n").encode("utf-8"))

    expected = hashlib.sha256(content.encode("utf-8")).hexdigest()
    assert canonical_jsonl_sha256(lf) == expected
    assert canonical_jsonl_sha256(crlf) == expected


def test_canonical_jsonl_checksum_detects_order_and_field_changes(tmp_path: Path) -> None:
    original = tmp_path / "original.jsonl"
    reordered = tmp_path / "reordered.jsonl"
    changed = tmp_path / "changed.jsonl"
    original.write_text('{"id":1,"text":"a"}\n{"id":2,"text":"b"}\n', encoding="utf-8")
    reordered.write_text('{"id":2,"text":"b"}\n{"id":1,"text":"a"}\n', encoding="utf-8")
    changed.write_text('{"id":1,"text":"changed"}\n{"id":2,"text":"b"}\n', encoding="utf-8")

    original_checksum = canonical_jsonl_sha256(original)
    assert canonical_jsonl_sha256(reordered) != original_checksum
    assert canonical_jsonl_sha256(changed) != original_checksum


def test_canonical_jsonl_checksum_rejects_malformed_jsonl(tmp_path: Path) -> None:
    malformed = tmp_path / "malformed.jsonl"
    malformed.write_text('{"id":1}\nnot-json\n', encoding="utf-8")

    with pytest.raises(ValueError, match="malformed JSONL at line 2"):
        canonical_jsonl_sha256(malformed)


def test_runner_and_verifier_share_the_canonical_checksum_contract() -> None:
    runner = runpy.run_path("scripts/run_week10_guardrail_evaluation.py")
    verifier = runpy.run_path("scripts/verify_week10_guardrail.py")

    assert runner["canonical_jsonl_sha256"] is canonical_jsonl_sha256
    assert verifier["verify_week10_evidence"] is verify_week10_evidence
    assert verify_week10_evidence.__globals__["canonical_jsonl_sha256"] is canonical_jsonl_sha256


def test_current_metrics_and_manifest_match_canonical_dataset_provenance() -> None:
    report, cases = verify_week10_evidence(DATASET, SOURCE, METRICS, MANIFEST)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    assert len(cases) == 40
    assert report["dataset_sha256"] == canonical_jsonl_sha256(DATASET)
    assert manifest["dataset_sha256"] == canonical_jsonl_sha256(DATASET)
    assert report["dataset_checksum_algorithm"] == CANONICAL_JSONL_SHA256_ALGORITHM
    assert manifest["dataset_checksum_algorithm"] == CANONICAL_JSONL_SHA256_ALGORITHM
    active_evidence = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            METRICS,
            MANIFEST,
            Path("evaluation/results/week10_guardrail_predictions.jsonl"),
            Path("evaluation/results/week10_guardrail_report.md"),
        )
    )
    assert ORPHAN_CHECKSUM not in active_evidence
    audit = Path("evaluation/results/week10_artifact_reconciliation.json").read_text(
        encoding="utf-8"
    )
    assert ORPHAN_CHECKSUM in audit


def test_verifier_detects_actual_dataset_content_change_without_rewriting_dataset(
    tmp_path: Path,
) -> None:
    records = raw_cases()
    records[0]["claim"]["text"] = f"{records[0]['claim']['text']} altered"
    modified_dataset = tmp_path / "week10_guardrail_cases.jsonl"
    modified_dataset.write_text(
        "".join(
            json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
            for record in records
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Week 10 dataset checksum mismatch"):
        verify_week10_evidence(modified_dataset, SOURCE, METRICS, MANIFEST)
