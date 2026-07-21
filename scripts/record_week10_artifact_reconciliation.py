"""Record the approved Week 10 evidence reconciliation from current outputs."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from vietnamese_labor_law_assistant.evaluation.week10_guardrails import (
    canonical_jsonl_sha256,
    load_week10_cases,
    raw_file_sha256,
    write_json_atomic,
)
from vietnamese_labor_law_assistant.guardrails.source_registry import CanonicalSourceRegistry

APPROVAL_TOKEN = "APPROVE_WEEK10_HEAD_DATASET_AS_CANONICAL"
APPROVED_COMMIT = "0eea899"
PREVIOUS_CHECKPOINT = "997a8f4"
ORPHAN_DECLARED_CHECKSUM = "e45b8c7b98670a4f9dd17635dd983794a013b901cca18c1b7fa6c9c42d4e534a"
DATASET = Path("data/evaluation/week10_guardrail_cases.jsonl")
SOURCE = Path("data/processed/labor_law_clauses.jsonl")
RESULTS = Path("evaluation/results")
EVIDENCE_PATHS = (
    RESULTS / "week10_guardrail_metrics.json",
    RESULTS / "week10_guardrail_manifest.json",
    RESULTS / "week10_guardrail_predictions.jsonl",
    RESULTS / "week10_guardrail_report.md",
)


def _git_blob_checksum(revision: str, path: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", f"{revision}:{path.as_posix()}"],
        capture_output=True,
        check=True,
        text=True,
    ).stdout.strip()


def main() -> int:
    verification = subprocess.run(
        [sys.executable, "scripts/verify_week10_guardrail.py"],
        capture_output=True,
        text=True,
    )
    if verification.returncode:
        raise SystemExit(verification.stderr or verification.stdout)
    cases = load_week10_cases(DATASET, CanonicalSourceRegistry(SOURCE))
    record = {
        "decision": APPROVAL_TOKEN,
        "owner_approval_token": APPROVAL_TOKEN,
        "approved_dataset_path": DATASET.as_posix(),
        "approved_commit": APPROVED_COMMIT,
        "previous_checkpoint": PREVIOUS_CHECKPOINT,
        "orphan_declared_checksum": ORPHAN_DECLARED_CHECKSUM,
        "approved_dataset_git_checksum": _git_blob_checksum(APPROVED_COMMIT, DATASET),
        "approved_dataset_raw_worktree_checksum": raw_file_sha256(DATASET),
        "canonical_dataset_checksum": canonical_jsonl_sha256(DATASET),
        "canonical_source_checksum": raw_file_sha256(SOURCE),
        "dataset_case_count": len(cases),
        "affected_case_ids": ["w10-002", "w10-033", "w10-036", "w10-037"],
        "reason_for_reconciliation": (
            "Owner approved the HEAD Week 10 dataset; official evidence was regenerated with a "
            "cross-platform canonical JSONL checksum."
        ),
        "review_packet": "docs/week10_artifact_reconciliation_review.md",
        "official_runner_command": "uv run python scripts/run_week10_guardrail_evaluation.py",
        "official_verifier_command": "uv run python scripts/verify_week10_guardrail.py",
        "generated_evidence": [
            {"path": path.as_posix(), "sha256": raw_file_sha256(path)} for path in EVIDENCE_PATHS
        ],
        "verifier_result": {
            "exit_code": verification.returncode,
            "stdout": verification.stdout.strip(),
        },
        "generated_at": datetime.now(UTC).isoformat(),
    }
    write_json_atomic(RESULTS / "week10_artifact_reconciliation.json", record)
    print(json.dumps(record, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
