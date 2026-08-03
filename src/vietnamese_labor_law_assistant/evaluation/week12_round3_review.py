"""Build and validate the bounded Week 12 round-3 human-review packet."""

from __future__ import annotations

import csv
import html
import json
from datetime import datetime
from pathlib import Path

REVIEW_FIELDS = [
    "reviewer_decision",
    "reviewer_name",
    "reviewer_role",
    "reviewed_at",
    "evidence_note",
]
FIELDNAMES = [
    "round3_review_id",
    "parent_round2_review_id",
    "original_round1_review_id",
    "round2_human_decision",
    "round2_human_evidence_note",
    "question",
    "round2_answer",
    "round2_route",
    "round2_outcome",
    "round2_tools",
    "round2_verification",
    "round3_root_cause",
    "round3_fix_summary",
    "corrected_answer",
    "corrected_router_decision",
    "corrected_route",
    "corrected_outcome",
    "corrected_planned_tools",
    "corrected_observed_tools",
    "corrected_citations",
    "corrected_verification",
    "corrected_warnings",
    "corrected_latency",
    "live_provenance",
    *REVIEW_FIELDS,
]


def build_rows(
    review_csv: Path,
    analysis_json: Path,
    live_json: Path,
    targets: dict[str, str],
) -> list[dict[str, str]]:
    """Project immutable review decisions and current live attempts into three rows."""

    with review_csv.open(encoding="utf-8-sig", newline="") as handle:
        reviews = {row["round2_review_id"]: row for row in csv.DictReader(handle)}
    analysis = json.loads(analysis_json.read_text(encoding="utf-8"))
    analyses = {item["round2_review_id"]: item for item in analysis["cases"]}
    live = json.loads(live_json.read_text(encoding="utf-8"))
    attempts = {
        item["parent_round2_review_id"]: item
        for item in live["attempts"]
        if item["case_id"].endswith("primary") and item["run_index"] == 1
    }
    rows: list[dict[str, str]] = []
    for parent_id, round3_id in targets.items():
        source = reviews[parent_id]
        case = analyses[parent_id]
        attempt = attempts[parent_id]
        row: dict[str, str] = {
            "round3_review_id": round3_id,
            "parent_round2_review_id": parent_id,
            "original_round1_review_id": source["original_review_id"],
            "round2_human_decision": source["reviewer_decision"],
            "round2_human_evidence_note": source["evidence_note"],
            "question": source["question"],
            "round2_answer": source["corrected_answer"],
            "round2_route": source["corrected_route"],
            "round2_outcome": case["current_outcome"],
            "round2_tools": source["corrected_tool_calls"],
            "round2_verification": source["corrected_verification"],
            "round3_root_cause": case["root_cause"],
            "round3_fix_summary": case["generic_correction"],
            "corrected_answer": attempt["answer"],
            "corrected_router_decision": attempt["router_decision"],
            "corrected_route": attempt["route"],
            "corrected_outcome": attempt["outcome_status"],
            "corrected_planned_tools": json.dumps(attempt["planned_tools"], ensure_ascii=False),
            "corrected_observed_tools": json.dumps(attempt["observed_tools"], ensure_ascii=False),
            "corrected_citations": json.dumps(attempt["citations"], ensure_ascii=False),
            "corrected_verification": json.dumps(attempt["verification"], ensure_ascii=False),
            "corrected_warnings": json.dumps(attempt["warnings"], ensure_ascii=False),
            "corrected_latency": str(attempt["latency_ms"]),
            "live_provenance": json.dumps(
                {
                    "provenance": live["provenance"],
                    "request_id": attempt["request_id"],
                    "source_commit": attempt["source_commit"],
                    "runtime_configuration": attempt["runtime_configuration"],
                },
                ensure_ascii=False,
            ),
            **dict.fromkeys(REVIEW_FIELDS, ""),
        }
        rows.append(row)
    validate_rows(rows)
    return rows


def validate_rows(rows: list[dict[str, str]]) -> None:
    """Reject packet drift or pre-populated reviewer fields."""

    if len(rows) != 3 or len({row["round3_review_id"] for row in rows}) != 3:
        raise ValueError("round-3 packet must contain three unique rows")
    if any(row[field] for row in rows for field in REVIEW_FIELDS):
        raise ValueError("round-3 reviewer fields must be blank")
    if any(set(row) != set(FIELDNAMES) for row in rows):
        raise ValueError("round-3 packet schema mismatch")


def validate_completed_review(
    blank_rows: list[dict[str, str]],
    reviewed_rows: list[dict[str, str]],
    required_ids: set[str],
    ai_rows: list[dict[str, str]] | None = None,
) -> dict[str, object]:
    """Validate a completed review without normalizing reviewer evidence."""

    if len(reviewed_rows) != 3:
        raise ValueError("round-3 reviewed packet must contain exactly three rows")
    reviewed_by_id = {row.get("round3_review_id", ""): row for row in reviewed_rows}
    if set(reviewed_by_id) != required_ids or len(reviewed_by_id) != len(reviewed_rows):
        raise ValueError("round-3 reviewed packet ID set mismatch")
    blank_by_id = {row.get("round3_review_id", ""): row for row in blank_rows}
    if set(blank_by_id) != required_ids:
        raise ValueError("round-3 blank packet ID set mismatch")

    for review_id in sorted(required_ids):
        reviewed = reviewed_by_id[review_id]
        blank = blank_by_id[review_id]
        if reviewed.get("reviewer_decision") != "PASS":
            raise ValueError(f"round-3 decision is not PASS: {review_id}")
        for field in REVIEW_FIELDS[1:]:
            if not reviewed.get(field, "").strip():
                raise ValueError(f"round-3 reviewer field is blank: {review_id}.{field}")
        try:
            datetime.fromisoformat(reviewed["reviewed_at"].replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"invalid reviewed_at: {review_id}") from exc
        for field, blank_value in blank.items():
            if field not in REVIEW_FIELDS and reviewed.get(field) != blank_value:
                raise ValueError(f"round-3 immutable field differs: {review_id}.{field}")

    if ai_rows is not None:
        ai_by_id = {row.get("round3_review_id", ""): row for row in ai_rows}
        if set(ai_by_id) != required_ids:
            raise ValueError("round-3 AI-assisted packet ID set mismatch")
        for review_id in sorted(required_ids):
            for field, value in ai_by_id[review_id].items():
                if field not in REVIEW_FIELDS and reviewed_by_id[review_id].get(field) != value:
                    raise ValueError(f"round-3 AI-assisted field differs: {review_id}.{field}")

    return {
        "row_count": len(reviewed_rows),
        "case_ids": sorted(required_ids),
        "decision_counts": {"PASS": 3, "FAIL": 0, "NEEDS_DISCUSSION": 0},
        "reviewer_metadata_complete": True,
        "immutable_fields_match": True,
        "ai_assisted_validation": "PASS" if ai_rows is not None else "NOT_APPLICABLE",
    }


def write_packet(rows: list[dict[str, str]], csv_path: Path, html_path: Path) -> None:
    """Write a spreadsheet-safe CSV and a route/outcome-visible HTML table."""

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    headers = "".join(f"<th>{html.escape(field)}</th>" for field in FIELDNAMES)
    body = "".join(
        "<tr>" + "".join(f"<td>{html.escape(row[field])}</td>" for field in FIELDNAMES) + "</tr>"
        for row in rows
    )
    html_path.write_text(
        "<!doctype html><html lang='vi'><meta charset='utf-8'><title>Week 12 round-3 review</title>"
        "<style>body{font-family:Arial,sans-serif;margin:24px}table{border-collapse:collapse}"
        "th,td{border:1px solid #bbb;padding:8px;vertical-align:top;min-width:140px}"
        "th{position:sticky;top:0;background:#eee}.route{font-weight:bold}</style>"
        "<h1>Week 12 round-3 independent human review</h1>"
        "<p>Review route and outcome as distinct fields. "
        "Enter only the five blank reviewer fields.</p>"
        f"<div style='overflow:auto'><table><thead><tr>{headers}</tr></thead>"
        f"<tbody>{body}</tbody></table></div>"
        "</html>",
        encoding="utf-8",
    )
