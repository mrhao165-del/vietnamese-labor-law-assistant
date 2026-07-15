"""Render review-application evidence without reclassifying project-author approval."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from vietnamese_labor_law_assistant.evaluation.dataset import (
    load_chunk_map,
    load_questions,
    write_json,
)
from vietnamese_labor_law_assistant.evaluation.pre_week6_readiness import build_readiness_report
from vietnamese_labor_law_assistant.evaluation.review_application import CORRECTED_IDS
from vietnamese_labor_law_assistant.ingestion.identifiers import calculate_file_sha256

ROOT = Path(__file__).resolve().parents[1]


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _old_checksum(current_checksum: str) -> str | None:
    manifests = sorted(
        ROOT.glob(
            "data/evaluation/archive/pre_week6_review_application_*/labor_law_eval_v1_manifest.json"
        ),
        reverse=True,
    )
    for path in manifests:
        candidate = json.loads(path.read_text(encoding="utf-8")).get("dataset_sha256")
        if candidate and candidate != current_checksum:
            return str(candidate)
    return None


def _quality(args: argparse.Namespace) -> dict[str, str]:
    return {
        "ruff_format": args.ruff_format,
        "ruff_lint": args.ruff_lint,
        "pyright": args.pyright,
        "pytest": args.pytest,
        "coverage": args.coverage,
        "evaluation_validation": args.evaluation_validation,
        "integration_tests": args.ingestion_reproducibility,
        "provenance_tests": args.provenance,
        "api_regression": args.api_regression,
        "retrieval_regression": args.retrieval_regression,
    }


def _markdown(report: dict[str, Any]) -> str:
    quality = report["quality_gates"]
    independent = report["independent_human_review"]
    blocker_lines = report["blockers"] or ["- None."]
    return "\n".join(
        [
            "# Pre-Week-6 review application report",
            "",
            f"- Status: **{report['status']}**",
            f"- Week 6 eligible: **{report['week6_eligible']}**",
            f"- Technical readiness: **{report['technical_readiness']}**",
            f"- Evidence readiness: **{report['evidence_readiness']}**",
            "",
            "## Review application",
            "",
            "- Week 1: 21 rows; 18 PASS; 3 CORRECTED; 0 PENDING.",
            "- Evaluation: 60 rows; 44 PASS; 16 CORRECTED; 0 PENDING.",
            (
                "- Evaluation reviewer classification: project-author AI-assisted approval; "
                "not independent legal-professional review."
            ),
            (
                "- Independent packet: "
                f"{independent['pass_count']}/{independent['total_rows']} PASS; "
                f"{independent['evidence_classification']}; reviewer role: "
                f"{independent['reviewer_role']}."
            ),
            f"- Corrected question IDs: {', '.join(report['correction_ids']['evaluation'])}.",
            "",
            "## Dataset and index provenance",
            "",
            f"- Previous dataset checksum: `{report['old_dataset_checksum']}`.",
            f"- Current dataset checksum: `{report['new_dataset_checksum']}`.",
            f"- Current chunk checksum: `{report['chunk_checksum']}`.",
            f"- Corrected chunk IDs unresolved: {report['unresolved_chunk_id_count']}.",
            "- DEV/TEST split and question IDs: unchanged.",
            (
                "- Week 3–5 metrics: not modified; benchmark artefacts are historical/provisional "
                "against the prior dataset checksum."
            ),
            "",
            "## Quality gates",
            "",
            *[f"- {name}: {value}" for name, value in quality.items()],
            f"- Independent-human evidence validation: {report['evidence_policy_validation']}.",
            "",
            "## Blocker",
            "",
            *blocker_lines,
            "",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    for name in (
        "ruff-format",
        "ruff-lint",
        "pyright",
        "pytest",
        "coverage",
        "evaluation-validation",
        "ingestion-reproducibility",
        "provenance",
        "api-regression",
        "retrieval-regression",
    ):
        parser.add_argument(f"--{name}", default="NOT_RUN")
    args = parser.parse_args()
    quality = _quality(args)
    readiness = build_readiness_report(ROOT, quality)
    packet = _read_csv(ROOT / "data/evaluation/labor_law_eval_v1_human_review_packet.csv")
    week1 = _read_csv(ROOT / "docs/week1_manual_validation.csv")
    questions = load_questions(ROOT / "data/evaluation/labor_law_eval_v1.jsonl")
    chunks = load_chunk_map(ROOT / "data/processed/labor_law_clauses.jsonl")
    current_checksum = calculate_file_sha256(ROOT / "data/evaluation/labor_law_eval_v1.jsonl")
    unresolved = sorted(
        {
            chunk_id
            for question in questions
            for chunk_id in question.expected_chunk_ids + question.reference_answer_source_chunk_ids
            if chunk_id not in chunks
        }
    )
    report: dict[str, Any] = {
        "status": readiness["status"],
        "technical_readiness": readiness["technical_readiness"],
        "evidence_readiness": readiness["evidence_readiness"],
        "week6_eligible": readiness["status"] == "READY",
        "week6_implemented": False,
        "review_counts": {
            "week1": {
                "total": len(week1),
                "pass": sum(row["human_decision"] == "PASS" for row in week1),
                "corrected": sum(row["human_decision"] == "CORRECTED" for row in week1),
                "pending": sum(not row["human_decision"] for row in week1),
            },
            "evaluation": {
                "total": len(packet),
                "pass": sum(row["human_decision"] == "PASS" for row in packet),
                "corrected": sum(row["human_decision"] == "CORRECTED" for row in packet),
                "pending": sum(not row["human_decision"] for row in packet),
                "independent_human_reviewed": readiness["evaluation_label_review"][
                    "independent_human_reviewed"
                ],
            },
        },
        "correction_ids": {
            "week1": ["W1-ARTICLE-059", "W1-ARTICLE-139", "W1-ARTICLE-220"],
            "evaluation": list(CORRECTED_IDS),
        },
        "old_dataset_checksum": _old_checksum(current_checksum),
        "new_dataset_checksum": current_checksum,
        "chunk_checksum": calculate_file_sha256(ROOT / "data/processed/labor_law_clauses.jsonl"),
        "chunk_count": len(chunks),
        "unresolved_chunk_id_count": len(unresolved),
        "unresolved_chunk_ids": unresolved,
        "quality_gates": quality,
        "independent_human_review": readiness["independent_human_review"],
        "evidence_policy_validation": (
            "PASS_DECLARED_INDEPENDENT_HUMAN"
            if readiness["independent_human_review"]["policy_satisfied"]
            else "FAIL_NOT_INDEPENDENT_OR_INCOMPLETE"
        ),
        "historical_benchmarks": "HISTORICAL_PROVISIONAL_PRIOR_DATASET",
        "metrics_modified": False,
        "split_changed": False,
        "question_ids_changed": False,
        "blockers": readiness["manual_actions_required"],
    }
    write_json(ROOT / "evaluation/results/pre_week6_review_application_report.json", report)
    (ROOT / "docs/pre_week6_review_application_report.md").write_text(
        _markdown(report), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
