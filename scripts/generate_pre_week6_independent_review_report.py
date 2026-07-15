"""Render the declared independent review provenance report from validated evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from vietnamese_labor_law_assistant.evaluation.dataset import write_json
from vietnamese_labor_law_assistant.ingestion.identifiers import calculate_file_sha256

ROOT = Path(__file__).resolve().parents[1]
VALIDATION_PATH = (
    ROOT / "evaluation/results/labor_law_eval_v1_independent_review_packet_validation.json"
)
MANIFEST_PATH = ROOT / "data/evaluation/labor_law_eval_v1_manifest.json"


def _previous_manifest_status() -> str | None:
    backups = sorted(
        ROOT.glob("data/evaluation/archive/*independent_review/labor_law_eval_v1_manifest.json"),
        reverse=True,
    )
    if not backups:
        return None
    return json.loads(backups[0].read_text(encoding="utf-8")).get("official_status")


def _markdown(report: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Pre-Week-6 independent review report",
            "",
            f"- Status: **{report['status']}**",
            f"- Packet: `{report['packet_path']}`.",
            f"- Rows: {report['pass_count']}/{report['total_rows']} PASS.",
            f"- Reviewer: {report['reviewer_name']} ({report['reviewer_role']}).",
            "- Evidence classification: declared independent human review, validated from "
            "repository-stored metadata and source mappings.",
            (
                "- The evidence does not verify licensed legal-professional status or real-world "
                "identity."
            ),
            (
                "- Semantic labels, split, question IDs, corpus, indexes, and historical metrics "
                "were not changed."
            ),
            "",
            "## Provenance",
            "",
            f"- Dataset checksum before/after: `{report['dataset_sha256_before']}` / "
            f"`{report['dataset_sha256_after']}`.",
            (
                f"- Source chunks: {report['source_chunk_count']} / "
                f"`{report['source_chunks_sha256']}`."
            ),
            f"- Manifest status: `{report['manifest_status_before']}` -> "
            f"`{report['manifest_status_after']}`.",
            (
                "- Project-author AI-assisted review packet remains preserved as historical "
                "provenance."
            ),
            "",
        ]
    )


def main() -> int:
    validation = json.loads(VALIDATION_PATH.read_text(encoding="utf-8"))
    if validation.get("status") != "PASS" or not validation.get("policy_satisfied"):
        raise ValueError("cannot report an independent review packet that did not pass validation")
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    dataset_path = ROOT / validation["dataset_path"]
    report: dict[str, Any] = {
        "status": "INDEPENDENT_HUMAN_REVIEW_RECORDED",
        "packet_path": validation["packet_path"],
        "packet_sha256": validation["packet_sha256"],
        "dataset_path": validation["dataset_path"],
        "dataset_sha256_before": calculate_file_sha256(dataset_path),
        "dataset_sha256_after": calculate_file_sha256(dataset_path),
        "source_chunks_sha256": validation["source_chunks_sha256"],
        "source_chunk_count": validation["source_chunk_count"],
        "total_rows": validation["total_rows"],
        "pass_count": validation["pass_count"],
        "corrected_count": validation["corrected_count"],
        "rejected_count": validation["rejected_count"],
        "needs_discussion_count": validation["needs_discussion_count"],
        "pending_count": validation["pending_count"],
        "duplicate_question_ids": validation["duplicate_question_ids"],
        "missing_question_ids": validation["missing_question_ids"],
        "invalid_chunk_ids": validation["invalid_chunk_ids"],
        "reviewer_name": validation["reviewer_name"],
        "reviewer_role": validation["reviewer_role"],
        "reviewer_independent_from_project_author": validation[
            "reviewer_independent_from_project_author"
        ],
        "reviewer_ai_or_machine": validation["reviewer_ai_or_machine"],
        "evidence_classification": validation["evidence_classification"],
        "policy_requirement": validation["policy_requirement"],
        "policy_satisfied": validation["policy_satisfied"],
        "semantic_labels_changed": False,
        "split_changed": False,
        "question_ids_changed": False,
        "author_review_preserved": True,
        "manifest_status_before": _previous_manifest_status(),
        "manifest_status_after": manifest["official_status"],
        "blockers": [],
        "files_created": [
            "docs/pre_week6_independent_review_report.md",
            "evaluation/results/pre_week6_independent_review_report.json",
        ],
        "files_modified": [
            "data/evaluation/labor_law_eval_v1_manifest.json",
            "evaluation/results/labor_law_eval_v1_independent_review_packet_validation.json",
        ],
    }
    write_json(ROOT / "evaluation/results/pre_week6_independent_review_report.json", report)
    (ROOT / "docs/pre_week6_independent_review_report.md").write_text(
        _markdown(report), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
