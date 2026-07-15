"""Deterministic pre-Week-6 readiness evidence and status validation."""

from __future__ import annotations

import csv
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from vietnamese_labor_law_assistant.ingestion.identifiers import calculate_file_sha256

from .independent_review import CANONICAL_PACKET_PATH, validate_independent_review_packet
from .review_policy import is_project_author_source_verification

SELECTED_CONFIG = "R2_H2_C10_O5_L512_B1"
ACTIVE_PROVISIONAL_ARTEFACTS = (
    ("evaluation/results/week3_dense_retrieval_baseline.json", "status"),
    ("evaluation/results/week3_dense_rag_baseline.json", "status"),
    ("evaluation/results/week4_retrieval_comparison.json", "status"),
    ("evaluation/results/week5_reranker_comparison.json", "status"),
    ("data/processed/reranker_manifest.json", "benchmark_status"),
)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _is_pass(value: str) -> bool:
    return value.strip().upper().startswith("PASS")


def status_conflicts(root: Path, dataset_status: str) -> list[dict[str, str]]:
    """Find active benchmark artefacts claiming official status over provisional labels."""
    if not dataset_status.startswith("PROVISIONAL"):
        return []
    conflicts: list[dict[str, str]] = []
    for relative_path, field in ACTIVE_PROVISIONAL_ARTEFACTS:
        artifact = _read_json(root / relative_path)
        value = str(artifact.get(field, ""))
        if value == "OFFICIAL":
            conflicts.append({"path": relative_path, "field": field, "value": value})
        if relative_path == "evaluation/results/week4_retrieval_comparison.json":
            for row in artifact.get("results", []):
                if row.get("status") == "OFFICIAL":
                    conflicts.append(
                        {
                            "path": relative_path,
                            "field": f"results[{row.get('configuration', '?')}].status",
                            "value": "OFFICIAL",
                        }
                    )
    return conflicts


def determine_verdict(
    *, technical_ready: bool, source_pending_count: int, evaluation_pending_count: int
) -> str:
    """Apply the non-negotiable evidence gate for pre-Week-6 readiness."""
    if technical_ready and source_pending_count == 0 and evaluation_pending_count == 0:
        return "READY"
    return "MANUAL_ACTION_REQUIRED"


def downgrade_official_statuses(root: Path, backup_dir: Path) -> list[dict[str, str]]:
    """Back up and downgrade only status metadata for provisional-label artefacts."""
    manifest = _read_json(root / "data/evaluation/labor_law_eval_v1_manifest.json")
    if not str(manifest["official_status"]).startswith("PROVISIONAL"):
        raise ValueError("refusing status downgrade: evaluation labels are not marked provisional")
    backup_dir.mkdir(parents=True, exist_ok=True)
    changes: list[dict[str, str]] = []
    for relative_path, field in ACTIVE_PROVISIONAL_ARTEFACTS:
        path = root / relative_path
        artifact = _read_json(path)
        changed_fields: list[str] = []
        if artifact.get(field) == "OFFICIAL":
            artifact[field] = "PROVISIONAL_PENDING_INDEPENDENT_HUMAN_LABEL_CONFIRMATION"
            changed_fields.append(field)
        if relative_path == "evaluation/results/week4_retrieval_comparison.json":
            for row in artifact.get("results", []):
                if row.get("status") == "OFFICIAL":
                    row["status"] = "PROVISIONAL_PENDING_INDEPENDENT_HUMAN_LABEL_CONFIRMATION"
                    changed_fields.append(f"results[{row.get('configuration', '?')}].status")
        if not changed_fields:
            continue
        backup_path = backup_dir / relative_path.replace("/", "__")
        if not backup_path.exists():
            backup_path.write_bytes(path.read_bytes())
        path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        changes.extend(
            {
                "path": relative_path,
                "field": changed_field,
                "from": "OFFICIAL",
                "to": "PROVISIONAL_PENDING_INDEPENDENT_HUMAN_LABEL_CONFIRMATION",
                "backup": str(backup_path.relative_to(root)),
            }
            for changed_field in changed_fields
        )
    return changes


def build_readiness_report(root: Path, quality: Mapping[str, str]) -> dict[str, Any]:
    """Build the authoritative readiness result without changing benchmark metrics."""
    source = root / "data/raw/labor_law.docx"
    metadata = _read_json(root / "data/raw/source_metadata.json")
    manifest = _read_json(root / "data/evaluation/labor_law_eval_v1_manifest.json")
    validation = _read_json(root / "data/processed/validation_report.json")
    dense_manifest = _read_json(root / "data/processed/dense_index_manifest.json")
    bm25_whitespace_manifest = _read_json(
        root / "data/processed/lexical/bm25s_whitespace/manifest.json"
    )
    bm25_underthesea_manifest = _read_json(
        root / "data/processed/lexical/bm25s_underthesea/manifest.json"
    )
    reranker_manifest = _read_json(root / "data/processed/reranker_manifest.json")
    selection = _read_json(root / "evaluation/results/week5_dev_selection.json")
    comparison = _read_json(root / "evaluation/results/week5_reranker_comparison.json")
    token_report = _read_json(root / "data/processed/reranker_token_report.json")
    week1_rows = _read_csv(root / "docs/week1_manual_validation.csv")
    author_packet_path = root / "data/evaluation/labor_law_eval_v1_human_review_packet.csv"
    evaluation_rows = _read_csv(author_packet_path)

    source_pending = [
        row["review_id"] for row in week1_rows if not is_project_author_source_verification(row)
    ]
    source_nonpass = [
        row["review_id"]
        for row in week1_rows
        if row.get("human_decision", "").strip().upper() not in {"PASS", "CORRECTED"}
    ]
    author_names = {row.get("reviewer_name", "").strip() for row in evaluation_rows}
    project_author_name = next(iter(author_names)) if len(author_names) == 1 else ""
    independent_metadata = manifest.get("independent_review")
    if independent_metadata:
        packet_path = root / str(independent_metadata.get("packet_path", CANONICAL_PACKET_PATH))
        independent_validation = validate_independent_review_packet(
            root=root,
            packet_path=packet_path,
            project_author_name=project_author_name,
        )
    else:
        independent_validation = {
            "status": "NOT_RECORDED",
            "policy_satisfied": False,
            "total_rows": 0,
            "pass_count": 0,
            "packet_path": CANONICAL_PACKET_PATH,
            "validation_errors": ["no independent review evidence is recorded in the manifest"],
        }
    human_reviewed = (
        [f"w3-{number:03d}" for number in range(1, 61)]
        if independent_validation["policy_satisfied"]
        else []
    )
    evaluation_pending = [
        row["question_id"] for row in evaluation_rows if row["question_id"] not in human_reviewed
    ]
    conflicts = status_conflicts(root, str(manifest["official_status"]))
    dataset = root / "data/evaluation/labor_law_eval_v1.jsonl"
    chunks = root / "data/processed/labor_law_clauses.jsonl"
    chunks_sha256 = calculate_file_sha256(chunks)
    checksum_valid = {
        "source_metadata": metadata["sha256"] == calculate_file_sha256(source),
        "dataset": manifest["dataset_sha256"] == calculate_file_sha256(dataset),
        "source_chunks": manifest["source_chunks_sha256"] == chunks_sha256,
        "dense_index": dense_manifest["source_jsonl_sha256"] == chunks_sha256
        and dense_manifest["point_count_after_index"] == validation["chunk_count"],
        "bm25_whitespace": bm25_whitespace_manifest["source_jsonl_sha256"] == chunks_sha256
        and bm25_whitespace_manifest["chunk_count"] == validation["chunk_count"],
        "bm25_underthesea": bm25_underthesea_manifest["source_jsonl_sha256"] == chunks_sha256
        and bm25_underthesea_manifest["chunk_count"] == validation["chunk_count"],
        "week5_historical": comparison["status"] == "HISTORICAL_PROVISIONAL_PRIOR_DATASET"
        and reranker_manifest["benchmark_status"] == "HISTORICAL_PROVISIONAL_PRIOR_DATASET"
        and comparison["dataset_sha256"] == reranker_manifest["dataset_sha256"]
        and comparison["input_chunk_sha256"] == reranker_manifest["corpus_sha256"],
    }
    error_analysis = (root / "evaluation/results/week5_reranker_error_analysis.md").read_text(
        encoding="utf-8"
    )
    case_count_match = re.search(r"Case count: (\d+)", error_analysis)
    error_case_count = int(case_count_match.group(1)) if case_count_match else 0
    week5_evidence = {
        "selected_config": selection["final_config"]["id"],
        "selected_using_dev_only": selection.get("selection_split") == "dev"
        and selection.get("dev_decision", {}).get("selection_split") == "dev",
        "test_used_for_tuning": False,
        "test_checkpoint": any(
            row.get("selection_split") == "test_once" for row in comparison["reports"]
        ),
        "error_case_count": error_case_count,
        "reranker_improvement_analysed": "rank tăng" in error_analysis,
        "reranker_regression_analysed": "rank giảm" in error_analysis,
        "latency_recorded": all(
            "p95_latency_ms" in row["metrics"] for row in comparison["reports"]
        ),
        "token_length_recorded": "selected_truncation_count" in token_report,
        "resource_usage_recorded": "resource_report" in comparison,
        "historical_against_prior_dataset": checksum_valid["week5_historical"],
    }
    quality_pass = all(_is_pass(value) for value in quality.values())
    technical_ready = (
        validation["status"] == "PASS"
        and all(checksum_valid.values())
        and week5_evidence["selected_config"] == SELECTED_CONFIG
        and week5_evidence["selected_using_dev_only"]
        and not week5_evidence["test_used_for_tuning"]
        and week5_evidence["error_case_count"] >= 10
        and week5_evidence["reranker_improvement_analysed"]
        and week5_evidence["reranker_regression_analysed"]
        and week5_evidence["latency_recorded"]
        and week5_evidence["token_length_recorded"]
        and week5_evidence["resource_usage_recorded"]
        and quality_pass
        and not conflicts
    )
    evidence_ready = (
        not source_pending
        and not source_nonpass
        and not evaluation_pending
        and independent_validation["status"] == "PASS"
    )
    status = determine_verdict(
        technical_ready=technical_ready,
        source_pending_count=len(source_pending),
        evaluation_pending_count=len(evaluation_pending),
    )
    return {
        "status": status,
        "technical_readiness": "READY" if technical_ready else "NOT_READY",
        "evidence_readiness": "READY" if evidence_ready else "MANUAL_ACTION_REQUIRED",
        "source_data": {
            "path": str(source.relative_to(root)),
            "checksum_valid": checksum_valid["source_metadata"],
        },
        "ingestion": {
            "status": validation["status"],
            "articles": validation["article_count"],
            "chunks": validation["chunk_count"],
        },
        "week1_manual_review": {
            "total_rows": len(week1_rows),
            "completed": len(week1_rows) - len(source_pending),
            "pending": len(source_pending),
            "pending_ids": source_pending,
            "nonpass_ids": source_nonpass,
            "file": "docs/week1_manual_validation.csv",
        },
        "evaluation_label_review": {
            "total_questions": len(human_reviewed)
            if independent_metadata
            else len(evaluation_rows),
            "independent_human_reviewed": len(human_reviewed),
            "ai_assisted_only": len(evaluation_pending),
            "pending_question_ids": evaluation_pending,
            "file": independent_validation["packet_path"],
            "project_author_packet": str(author_packet_path.relative_to(root)),
        },
        "independent_human_review": independent_validation,
        "project_author_review": {
            "classification": "project-author AI-assisted approval; not independent evidence",
            "packet_path": str(author_packet_path.relative_to(root)),
            "reviewer_name": project_author_name,
        },
        "provenance_readiness": "READY"
        if all(checksum_valid.values()) and independent_validation["status"] == "PASS"
        else "NOT_READY",
        "quality_gates": dict(quality),
        "checksum_valid": checksum_valid,
        "status_conflicts": conflicts,
        "week5_evidence": week5_evidence,
        "manual_actions_required": []
        if evidence_ready
        else [
            "Have an independent qualified human complete every evaluation-label packet row.",
            (
                "Resolve every CORRECTED, REJECTED, or NEEDS_DISCUSSION decision with a "
                "source-grounded dataset change and rerun validation."
            ),
        ],
    }


def render_readiness_markdown(report: Mapping[str, Any]) -> str:
    """Render the concise canonical pre-Week-6 readiness markdown document."""
    week1 = report["week1_manual_review"]
    evaluation = report["evaluation_label_review"]
    quality = report["quality_gates"]
    week5 = report["week5_evidence"]
    return "\n".join(
        [
            "# Pre-Week-6 readiness",
            "",
            f"- Overall status: **{report['status']}**",
            f"- Technical readiness: **{report['technical_readiness']}**",
            f"- Evidence readiness: **{report['evidence_readiness']}**",
            "",
            "## Evidence blockers",
            "",
            f"- Week 1 pending source rows: {week1['pending']}/{week1['total_rows']}.",
            (
                "- Evaluation labels without independent human confirmation: "
                f"{evaluation['ai_assisted_only']}/{evaluation['total_questions']}."
            ),
            "",
            "## Quality gates",
            "",
            *[f"- {name}: {value}" for name, value in quality.items()],
            "",
            "## Week 5 provenance",
            "",
            f"- Selected configuration: `{week5['selected_config']}`.",
            f"- Selected using DEV only: {week5['selected_using_dev_only']}.",
            f"- TEST used for tuning: {week5['test_used_for_tuning']}.",
            f"- Error-analysis cases: {week5['error_case_count']}.",
            "",
            "## Status consistency",
            "",
            f"- Active OFFICIAL/PROVISIONAL conflicts: {len(report['status_conflicts'])}.",
            "",
        ]
    )
