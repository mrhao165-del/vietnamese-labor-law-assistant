"""Validate and record declared independent human evaluation review evidence."""

from __future__ import annotations

import csv
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from vietnamese_labor_law_assistant.ingestion.identifiers import calculate_file_sha256

from .dataset import load_chunk_map, load_questions
from .review_policy import (
    AI_REVIEWER_MARKERS,
    HUMAN_DECISIONS,
    reviewer_is_independent_human,
    reviewer_role_is_independent,
)

CANONICAL_PACKET_PATH = "data/evaluation/labor_law_eval_v1_independent_review_packet.csv"
CANONICAL_VALIDATION_PATH = (
    "evaluation/results/labor_law_eval_v1_independent_review_packet_validation.json"
)
CORRECTED_FIELDS = (
    "corrected_articles",
    "corrected_clauses",
    "corrected_chunk_ids",
    "corrected_reference_answer",
    "corrected_evaluation_scope",
    "corrected_expected_behavior",
    "corrected_required_clarifications",
)
DATASET_FIELDS = (
    "split",
    "question",
    "evaluation_scope",
    "expected_behavior",
    "reference_answer",
)
JSON_DATASET_FIELDS = {
    "expected_articles": "expected_articles",
    "expected_clauses": "expected_clauses",
    "source_chunk_ids": "expected_chunk_ids",
    "reference_answer_source_chunk_ids": "reference_answer_source_chunk_ids",
    "required_clarifications": "required_clarifications",
}


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _json_value(row: Mapping[str, str], field: str, errors: list[str]) -> list[Any]:
    try:
        value = json.loads(row.get(field, ""))
    except json.JSONDecodeError:
        errors.append(f"{row.get('question_id', '<unknown>')}: invalid JSON in {field}")
        return []
    if not isinstance(value, list):
        errors.append(f"{row.get('question_id', '<unknown>')}: {field} must be a JSON list")
        return []
    return value


def _is_true(value: str) -> bool:
    return value.strip().casefold() == "true"


def _contains_machine_marker(value: str) -> bool:
    normalized = value.casefold()
    return any(marker in normalized for marker in AI_REVIEWER_MARKERS)


def _display_path(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _packet_excerpt_matches(
    row: Mapping[str, str], chunk_ids: Sequence[str], chunks: Mapping[str, Any]
) -> bool:
    excerpt = row.get("source_excerpt", "")
    return all(
        chunk_id in chunks and chunk_id in excerpt and chunks[chunk_id].content in excerpt
        for chunk_id in chunk_ids
    )


def validate_independent_review_packet(
    *,
    root: Path,
    packet_path: Path,
    project_author_name: str,
    expected_question_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Validate a full independent review packet against the immutable current dataset."""
    rows = _read_csv(packet_path)
    questions = {
        q.question_id: q for q in load_questions(root / "data/evaluation/labor_law_eval_v1.jsonl")
    }
    chunks = load_chunk_map(root / "data/processed/labor_law_clauses.jsonl")
    expected_ids = expected_question_ids or set(questions)
    errors: list[str] = []
    question_ids = [row.get("question_id", "") for row in rows]
    duplicate_ids = sorted(
        question_id for question_id, count in Counter(question_ids).items() if count > 1
    )
    missing_ids = sorted(expected_ids - set(question_ids))
    unexpected_ids = sorted(set(question_ids) - expected_ids)
    if len(rows) != len(expected_ids):
        errors.append(f"row count {len(rows)} does not match expected {len(expected_ids)}")
    if duplicate_ids:
        errors.append("duplicate question IDs")
    if missing_ids:
        errors.append("missing question IDs")
    if unexpected_ids:
        errors.append("unexpected question IDs")

    dataset_sha256 = calculate_file_sha256(root / "data/evaluation/labor_law_eval_v1.jsonl")
    source_chunks_sha256 = calculate_file_sha256(root / "data/processed/labor_law_clauses.jsonl")
    invalid_chunk_ids: set[str] = set()
    corrected_fields_populated: list[str] = []
    reviewer_names: set[str] = set()
    reviewer_roles: set[str] = set()
    reviewed_at_values: set[str] = set()
    decisions: Counter[str] = Counter()

    for row in rows:
        question_id = row.get("question_id", "")
        decision = row.get("independent_decision", "").strip().upper()
        decisions[decision] += 1
        reviewer_name = row.get("reviewer_name", "").strip()
        reviewer_role = row.get("reviewer_role", "").strip()
        reviewer_names.add(reviewer_name)
        reviewer_roles.add(reviewer_role)
        reviewed_at = row.get("reviewed_at", "").strip()
        reviewed_at_values.add(reviewed_at)
        if decision not in HUMAN_DECISIONS:
            errors.append(f"{question_id}: invalid or missing independent decision")
        if not reviewer_is_independent_human(reviewer_name) or _contains_machine_marker(
            reviewer_role
        ):
            errors.append(f"{question_id}: reviewer identifies AI or machine review")
        if not reviewer_role_is_independent(reviewer_role):
            errors.append(f"{question_id}: reviewer role is not independent")
        if not reviewer_name or reviewer_name.casefold() == project_author_name.strip().casefold():
            errors.append(f"{question_id}: reviewer is missing or matches project author")
        if not _is_true(row.get("independent_from_project_author", "")):
            errors.append(f"{question_id}: independent_from_project_author must be true")
        if row.get("used_ai_as_reviewer", "").strip().casefold() != "false":
            errors.append(f"{question_id}: used_ai_as_reviewer must be false")
        if not row.get("evidence_note", "").strip() or question_id not in row.get(
            "evidence_note", ""
        ):
            errors.append(f"{question_id}: evidence_note is missing or lacks the question ID")
        try:
            datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
        except ValueError:
            errors.append(f"{question_id}: reviewed_at is not ISO-8601")
        if row.get("dataset_sha256") != dataset_sha256:
            errors.append(f"{question_id}: dataset checksum mismatch")
        if row.get("source_chunks_sha256") != source_chunks_sha256:
            errors.append(f"{question_id}: source chunk checksum mismatch")
        if decision == "PASS" and any(row.get(field, "").strip() for field in CORRECTED_FIELDS):
            corrected_fields_populated.append(question_id)
            errors.append(f"{question_id}: PASS row has populated corrected fields")
        question = questions.get(question_id)
        if question is None:
            continue
        for field in DATASET_FIELDS:
            expected_value = getattr(question, field) or ""
            if row.get(field, "") != expected_value:
                errors.append(f"{question_id}: {field} differs from the current dataset")
        if row.get("question_type") != question.category:
            errors.append(f"{question_id}: question_type differs from current category")
        decoded: dict[str, list[Any]] = {
            field: _json_value(row, field, errors) for field in JSON_DATASET_FIELDS
        }
        for packet_field, model_field in JSON_DATASET_FIELDS.items():
            current_value = getattr(question, model_field)
            if model_field == "expected_clauses":
                current_value = [clause.model_dump() for clause in current_value]
            if decoded[packet_field] != current_value:
                errors.append(f"{question_id}: {packet_field} differs from the current dataset")
        source_chunk_ids = [str(value) for value in decoded["source_chunk_ids"]]
        reference_chunk_ids = [str(value) for value in decoded["reference_answer_source_chunk_ids"]]
        for chunk_id in source_chunk_ids + reference_chunk_ids:
            if chunk_id not in chunks:
                invalid_chunk_ids.add(chunk_id)
        if source_chunk_ids and not _packet_excerpt_matches(row, source_chunk_ids, chunks):
            errors.append(f"{question_id}: source_excerpt does not match current chunks")
        for clause in question.expected_clauses:
            if source_chunk_ids and not any(
                chunks[chunk_id].article_number == clause.article_number
                and chunks[chunk_id].clause_number == clause.clause_number
                for chunk_id in source_chunk_ids
                if chunk_id in chunks
            ):
                errors.append(
                    f"{question_id}: expected clause is not represented by a source chunk"
                )

    missing_decision_count = sum(
        1 for row in rows if not row.get("independent_decision", "").strip()
    )
    pass_count = decisions["PASS"]
    result = {
        "status": "PASS" if not errors else "FAIL",
        "packet_path": _display_path(packet_path, root),
        "packet_sha256": calculate_file_sha256(packet_path),
        "dataset_path": "data/evaluation/labor_law_eval_v1.jsonl",
        "dataset_sha256": dataset_sha256,
        "source_chunks_path": "data/processed/labor_law_clauses.jsonl",
        "source_chunks_sha256": source_chunks_sha256,
        "source_chunk_count": len(chunks),
        "total_rows": len(rows),
        "pass_count": pass_count,
        "corrected_count": decisions["CORRECTED"],
        "rejected_count": decisions["REJECTED"],
        "needs_discussion_count": decisions["NEEDS_DISCUSSION"],
        "pending_count": missing_decision_count,
        "duplicate_question_ids": duplicate_ids,
        "missing_question_ids": missing_ids,
        "unexpected_question_ids": unexpected_ids,
        "invalid_chunk_ids": sorted(invalid_chunk_ids),
        "corrected_fields_unexpectedly_populated": corrected_fields_populated,
        "reviewer_name": next(iter(reviewer_names), "") if len(reviewer_names) == 1 else None,
        "reviewer_role": next(iter(reviewer_roles), "") if len(reviewer_roles) == 1 else None,
        "reviewed_at": next(iter(reviewed_at_values), "") if len(reviewed_at_values) == 1 else None,
        "reviewer_independent_from_project_author": all(
            _is_true(row.get("independent_from_project_author", "")) for row in rows
        ),
        "reviewer_ai_or_machine": any(
            _contains_machine_marker(row.get("reviewer_name", ""))
            or _contains_machine_marker(row.get("reviewer_role", ""))
            or _is_true(row.get("used_ai_as_reviewer", ""))
            for row in rows
        ),
        "evidence_classification": "declared independent human review",
        "policy_requirement": "complete independent human review evidence",
        "policy_satisfied": not errors and pass_count == len(expected_ids),
        "validation_errors": errors,
    }
    return result


def record_independent_review_provenance(
    *, manifest_path: Path, validation: Mapping[str, Any], validation_path: str
) -> dict[str, Any]:
    """Update only manifest provenance after a passing independent review validation."""
    if validation.get("status") != "PASS" or not validation.get("policy_satisfied"):
        raise ValueError("refusing to record independent review provenance for a failing packet")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    previous_status = manifest.get("official_status")
    manifest.update(
        {
            "updated_at": datetime.now(UTC).isoformat(),
            "official_status": "INDEPENDENT_HUMAN_REVIEWED",
            "review_provenance": (
                "Repository-validated declared independent human review recorded; reviewer role "
                "is not evidence of licensed legal-professional status."
            ),
            "independent_review": {
                "packet_path": validation["packet_path"],
                "packet_sha256": validation["packet_sha256"],
                "validation_path": validation_path,
                "reviewer_name": validation["reviewer_name"],
                "reviewer_role": validation["reviewer_role"],
                "reviewed_at": validation["reviewed_at"],
                "evidence_classification": validation["evidence_classification"],
                "policy_satisfied": validation["policy_satisfied"],
                "project_author_packet_preserved": True,
            },
        }
    )
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return {"previous_status": previous_status, "current_status": manifest["official_status"]}
