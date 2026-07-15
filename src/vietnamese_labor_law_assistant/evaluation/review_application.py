"""Apply explicit project-author evaluation corrections with provenance safeguards."""

from __future__ import annotations

import csv
import json
import shutil
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from vietnamese_labor_law_assistant.evaluation.dataset import (
    load_chunk_map,
    load_questions,
    write_json,
    write_questions,
)
from vietnamese_labor_law_assistant.evaluation.models import ExpectedClause
from vietnamese_labor_law_assistant.ingestion.identifiers import calculate_file_sha256

PACKET_FIELDS = (
    "corrected_evaluation_scope",
    "corrected_expected_behavior",
    "corrected_required_clarifications",
    "calculator_convention_metadata",
)
CORRECTED_IDS = (
    "w3-019",
    "w3-031",
    "w3-032",
    "w3-033",
    "w3-035",
    "w3-036",
    "w3-037",
    "w3-038",
    "w3-041",
    "w3-042",
    "w3-044",
    "w3-045",
    "w3-046",
    "w3-047",
    "w3-048",
    "w3-049",
)
OVERRIDES: dict[str, dict[str, Any]] = {
    "w3-033": {
        "required_clarifications": [
            "loại công việc",
            "công việc có thuộc danh mục công việc nhẹ hay không",
            "điều kiện hợp đồng",
            "thời giờ",
            "sức khỏe",
            "an toàn",
        ]
    },
    "w3-045": {
        "evaluation_scope": "rag",
        "expected_behavior": "clarification_needed",
        "required_clarifications": [
            "điểm/lý do cụ thể thuộc Khoản 1 Điều 36",
            "có thuộc ngành/nghề/công việc đặc thù hay không",
        ],
    },
    "w3-046": {"evaluation_scope": "rag", "expected_behavior": "answer_with_citations"},
    "w3-047": {"evaluation_scope": "retrieval", "expected_behavior": "answer_with_citations"},
    "w3-048": {
        "evaluation_scope": "rag",
        "expected_behavior": "clarification_needed",
        "required_clarifications": ["quy tắc làm tròn áp dụng cho số ngày nghỉ tỷ lệ"],
    },
    "w3-049": {"evaluation_scope": "retrieval", "expected_behavior": "answer_with_citations"},
    "w3-041": {
        "calculator_convention": {
            "inclusive_start": True,
            "end_date": "start_date + duration_days - 1",
        }
    },
    "w3-042": {
        "calculator_convention": {
            "inclusive_start": True,
            "end_date": "start_date + duration_days - 1",
        }
    },
}


def create_review_application_backups(root: Path, timestamp: str) -> dict[str, str]:
    """Copy every artefact that review application or rebuilding can replace."""
    groups = {
        "docs": ["docs/week1_manual_validation.csv"],
        "evaluation": [
            "data/evaluation/labor_law_eval_v1_human_review_packet.csv",
            "data/evaluation/labor_law_eval_v1.jsonl",
            "data/evaluation/labor_law_eval_v1_manifest.json",
        ],
        "processed": [
            "data/processed/labor_law_articles.jsonl",
            "data/processed/labor_law_clauses.jsonl",
            "data/processed/validation_report.json",
            "data/processed/docx_inventory.tsv",
            "data/processed/dense_index_manifest.json",
            "data/processed/reranker_manifest.json",
        ],
    }
    copied: dict[str, str] = {}
    for group, paths in groups.items():
        destination = (
            root
            / ("docs/archive" if group == "docs" else f"data/{group}/archive")
            / f"pre_week6_review_application_{timestamp}"
        )
        destination.mkdir(parents=True, exist_ok=True)
        for relative in paths:
            source = root / relative
            if source.exists():
                target = destination / source.name
                shutil.copy2(source, target)
                copied[relative] = str(target.relative_to(root))
    lexical_destination = (
        root / "data/processed/archive" / f"pre_week6_review_application_{timestamp}"
    )
    for tokenizer in ("whitespace", "underthesea"):
        source = root / f"data/processed/lexical/bm25s_{tokenizer}"
        if source.exists():
            target = lexical_destination / source.name
            shutil.copytree(source, target)
            copied[str(source.relative_to(root))] = str(target.relative_to(root))
    return copied


def _json_list(row: Mapping[str, str], field: str) -> list[Any]:
    value = row.get(field, "")
    parsed = json.loads(value) if value else []
    if not isinstance(parsed, list):
        raise ValueError(f"{row['question_id']}: {field} must be a JSON list")
    return parsed


def apply_project_author_review(root: Path, packet_path: Path) -> dict[str, Any]:
    """Apply only explicit structured correction fields; never infer from notes."""
    with packet_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    if len(rows) != 60 or {
        row["question_id"] for row in rows if row["human_decision"] == "CORRECTED"
    } != set(CORRECTED_IDS):
        raise ValueError(
            "review packet count or corrected question IDs do not match the approved review"
        )
    if any(
        "REQUIRES_REPOSITORY_CHUNK_LOOKUP" in row.get("corrected_source_chunk_ids", "")
        for row in rows
    ):
        raise ValueError("review packet still contains unresolved chunk-ID placeholders")
    questions = {
        q.question_id: q for q in load_questions(root / "data/evaluation/labor_law_eval_v1.jsonl")
    }
    chunk_map = load_chunk_map(root / "data/processed/labor_law_clauses.jsonl")
    old_hash = calculate_file_sha256(root / "data/evaluation/labor_law_eval_v1.jsonl")
    applied: list[str] = []
    for row in rows:
        decision = row["human_decision"].strip().upper()
        question = questions[row["question_id"]]
        if decision not in {"PASS", "CORRECTED"}:
            raise ValueError(f"{question.question_id}: unresolved review decision")
        values: dict[str, Any] = {
            "review_status": "PASS",
            "human_validated": False,
            "reviewer": row["reviewer_name"],
            "review_notes": row["evidence_note"],
        }
        if decision == "CORRECTED":
            chunk_ids = [str(item) for item in _json_list(row, "corrected_source_chunk_ids")]
            clauses = [
                ExpectedClause.model_validate(item) for item in _json_list(row, "corrected_clauses")
            ]
            articles = [int(item) for item in _json_list(row, "corrected_articles")]
            if any(chunk_id not in chunk_map for chunk_id in chunk_ids):
                raise ValueError(f"{question.question_id}: corrected source chunk does not exist")
            values.update(
                expected_chunk_ids=chunk_ids,
                expected_clauses=clauses,
                expected_articles=articles,
                primary_article=articles[0],
                reference_answer=row.get("corrected_reference_answer") or None,
                reference_answer_source_chunk_ids=chunk_ids
                if row.get("corrected_reference_answer")
                else [],
            )
            values.update(OVERRIDES.get(question.question_id, {}))
            applied.append(question.question_id)
        questions[question.question_id] = question.model_copy(update=values)
    write_questions(
        root / "data/evaluation/labor_law_eval_v1.jsonl",
        [questions[f"w3-{i:03d}"] for i in range(1, 61)],
    )
    new_hash = calculate_file_sha256(root / "data/evaluation/labor_law_eval_v1.jsonl")
    manifest_path = root / "data/evaluation/labor_law_eval_v1_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update(
        {
            "updated_at": datetime.now(UTC).isoformat(),
            "dataset_sha256": new_hash,
            "source_chunks_sha256": calculate_file_sha256(
                root / "data/processed/labor_law_clauses.jsonl"
            ),
            "review_status_counts": {"PASS": 60, "CORRECTED_APPLIED": 16},
            "review_provenance": (
                "Project-author approval of AI-assisted review applied; not independent "
                "legal-professional confirmation."
            ),
            "official_status": "PROVISIONAL_PROJECT_AUTHOR_AI_ASSISTED_APPROVAL",
        }
    )
    write_json(manifest_path, manifest)
    return {
        "old_dataset_sha256": old_hash,
        "new_dataset_sha256": new_hash,
        "applied_question_ids": applied,
    }
