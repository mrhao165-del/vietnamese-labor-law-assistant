"""Discover and validate frozen artifacts protected by raw-byte SHA-256 evidence."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class FrozenEvidence:
    """One artifact and the authoritative field that protects its exact bytes."""

    path: str
    expected_sha256: str
    source_field: str


@dataclass(frozen=True)
class FrozenEvidenceResult:
    """Raw-checksum validation result for one frozen artifact."""

    evidence: FrozenEvidence
    actual_sha256: str

    @property
    def matches(self) -> bool:
        return self.actual_sha256 == self.evidence.expected_sha256


def _read_json(root: Path, relative_path: str) -> dict[str, Any]:
    value = json.loads((root / relative_path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {relative_path}")
    return value


def discover_frozen_evidence(root: Path) -> list[FrozenEvidence]:
    """Read active authoritative reports and return their raw-checksum targets."""
    discovered: dict[str, FrozenEvidence] = {}

    def add(path: object, expected: object, source_field: str) -> None:
        if not isinstance(path, str) or not isinstance(expected, str):
            raise ValueError(f"invalid frozen evidence reference: {source_field}")
        evidence = FrozenEvidence(path, expected, source_field)
        previous = discovered.get(path)
        if previous and previous.expected_sha256 != expected:
            raise ValueError(f"conflicting frozen evidence checksums for {path}")
        if previous is None:
            discovered[path] = evidence

    metadata = _read_json(root, "data/raw/source_metadata.json")
    add(metadata["source_file"], metadata["sha256"], "data/raw/source_metadata.json:sha256")

    validation = _read_json(root, "data/processed/validation_report.json")
    add(
        "docs/week1_manual_validation.csv",
        validation["manual_review_evidence_sha256"],
        "data/processed/validation_report.json:manual_review_evidence_sha256",
    )

    dataset_manifest_path = "data/evaluation/labor_law_eval_v1_manifest.json"
    dataset_manifest = _read_json(root, dataset_manifest_path)
    add(
        "data/evaluation/labor_law_eval_v1.jsonl",
        dataset_manifest["dataset_sha256"],
        f"{dataset_manifest_path}:dataset_sha256",
    )
    add(
        "data/processed/labor_law_clauses.jsonl",
        dataset_manifest["source_chunks_sha256"],
        f"{dataset_manifest_path}:source_chunks_sha256",
    )
    independent = dataset_manifest["independent_review"]
    add(
        independent["packet_path"],
        independent["packet_sha256"],
        f"{dataset_manifest_path}:independent_review.packet_sha256",
    )

    week4_path = "evaluation/results/week4_current_retrieval_comparison.json"
    week4 = _read_json(root, week4_path)
    add(
        "evaluation/results/week4_current_retrieval_predictions.jsonl",
        week4["predictions_sha256"],
        f"{week4_path}:predictions_sha256",
    )

    week5_path = "evaluation/results/week5_current_reranker_comparison.json"
    week5 = _read_json(root, week5_path)
    for result in week5["dev_results"]:
        configuration_id = result["configuration"]["id"]
        add(
            f"evaluation/results/week5_current_checkpoints/dev/{configuration_id}/predictions.jsonl",
            result["predictions_sha256"],
            f"{week5_path}:dev_results[{configuration_id}].predictions_sha256",
        )
    test_result = week5["test_result"]
    test_configuration_id = test_result["configuration"]["id"]
    add(
        "evaluation/results/week5_current_checkpoints/"
        f"test/{test_configuration_id}/predictions.jsonl",
        test_result["predictions_sha256"],
        f"{week5_path}:test_result[{test_configuration_id}].predictions_sha256",
    )

    final_manifest_path = "evaluation/results/week12/final_release_manifest.json"
    final_manifest = _read_json(root, final_manifest_path)
    for path, expected in final_manifest["checksums"].items():
        add(path, expected, f"{final_manifest_path}:checksums[{path}]")
    for name, expected in final_manifest["historical_manifests"].items():
        path = f"evaluation/results/week12/{name}"
        add(path, expected, f"{final_manifest_path}:historical_manifests[{name}]")

    for round_number in (1, 2, 3):
        report_path = f"evaluation/results/week12/review_round{round_number}_validation.json"
        report = _read_json(root, report_path)
        for field in (
            "source",
            "reviewed_packet",
            "blank_packet",
            "ai_pre_review_packet",
            "ai_assisted_packet",
            "archive",
        ):
            reference = report.get(field)
            if isinstance(reference, dict) and reference.get("sha256") is not None:
                add(reference.get("path"), reference.get("sha256"), f"{report_path}:{field}.sha256")

    live_path = "evaluation/results/week12/final_live_validation.json"
    live = _read_json(root, live_path)
    for matrix in live["matrices"]:
        add(
            matrix["path"],
            matrix["sha256"],
            f"{live_path}:matrices[{matrix['name']}].sha256",
        )

    return [discovered[path] for path in sorted(discovered)]


def validate_frozen_evidence(
    root: Path, evidence: list[FrozenEvidence]
) -> list[FrozenEvidenceResult]:
    """Hash exact file bytes without rewriting or normalizing any artifact."""
    results: list[FrozenEvidenceResult] = []
    for item in evidence:
        path = root / item.path
        actual = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "MISSING"
        results.append(FrozenEvidenceResult(item, actual))
    return results
