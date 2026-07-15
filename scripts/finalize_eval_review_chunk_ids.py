#!/usr/bin/env python
"""Resolve review-packet chunk-ID placeholders from the repository chunk JSONL.

Run from the repository root:
    uv run python scripts/finalize_eval_review_chunk_ids.py ^
      --input data/evaluation/labor_law_eval_v1_human_review_packet.csv

The script creates a timestamped backup, replaces every
REQUIRES_REPOSITORY_CHUNK_LOOKUP:<article>:<clause> token with the real
chunk ID(s) found in data/processed/labor_law_clauses.jsonl, validates the
packet, and writes it back in CSV UTF-8 format.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

PLACEHOLDER_RE = re.compile(r"^REQUIRES_REPOSITORY_CHUNK_LOOKUP:(?P<article>\d+):(?P<clause>\d+)$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/evaluation/labor_law_eval_v1_human_review_packet.csv"),
    )
    parser.add_argument(
        "--chunks",
        type=Path,
        default=Path("data/processed/labor_law_clauses.jsonl"),
    )
    return parser.parse_args()


def pick(record: dict[str, Any], name: str) -> Any:
    if name in record:
        return record[name]
    metadata = record.get("metadata")
    if isinstance(metadata, dict):
        return metadata.get(name)
    return None


def load_chunk_map(path: Path) -> dict[tuple[int, int], list[str]]:
    if not path.exists():
        raise FileNotFoundError(path)

    mapping: dict[tuple[int, int], list[str]] = defaultdict(list)
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON at {path}:{line_number}") from exc

            article = pick(record, "article_number")
            clause = pick(record, "clause_number")
            chunk_id = pick(record, "chunk_id") or record.get("id")

            if article is None or clause is None or not chunk_id:
                continue

            key = (int(article), int(clause))
            chunk_id = str(chunk_id)
            if chunk_id not in mapping[key]:
                mapping[key].append(chunk_id)

    return dict(mapping)


def main() -> None:
    args = parse_args()
    input_path: Path = args.input
    chunks_path: Path = args.chunks

    if not input_path.exists():
        raise FileNotFoundError(input_path)

    chunk_map = load_chunk_map(chunks_path)

    with input_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        rows = list(reader)

    if len(rows) != 60:
        raise ValueError(f"Expected 60 review rows, found {len(rows)}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = input_path.with_name(f"{input_path.stem}.before_chunk_resolution_{timestamp}.csv")
    shutil.copy2(input_path, backup)

    unresolved: list[str] = []
    changed_rows: list[str] = []

    for row in rows:
        raw = row.get("corrected_source_chunk_ids", "").strip()
        if not raw:
            continue

        try:
            values = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"{row['question_id']}: corrected_source_chunk_ids is not valid JSON"
            ) from exc

        if not isinstance(values, list):
            raise ValueError(
                f"{row['question_id']}: corrected_source_chunk_ids must be a JSON list"
            )

        resolved: list[str] = []
        changed = False

        for value in values:
            value = str(value)
            match = PLACEHOLDER_RE.match(value)
            if not match:
                if value not in resolved:
                    resolved.append(value)
                continue

            key = (int(match.group("article")), int(match.group("clause")))
            ids = chunk_map.get(key, [])
            if not ids:
                unresolved.append(f"{row['question_id']}: Điều {key[0]} Khoản {key[1]}")
                continue

            changed = True
            for chunk_id in ids:
                if chunk_id not in resolved:
                    resolved.append(chunk_id)

        row["corrected_source_chunk_ids"] = json.dumps(resolved, ensure_ascii=False)
        if changed:
            changed_rows.append(row["question_id"])

    if unresolved:
        details = "\n".join(f"- {item}" for item in unresolved)
        raise RuntimeError("Could not resolve all chunk IDs. No output was written.\n" + details)

    remaining = [
        row["question_id"]
        for row in rows
        if "REQUIRES_REPOSITORY_CHUNK_LOOKUP" in row.get("corrected_source_chunk_ids", "")
    ]
    if remaining:
        raise RuntimeError(f"Placeholders remain: {remaining}")

    invalid_decisions = [
        row["question_id"] for row in rows if row.get("human_decision") not in {"PASS", "CORRECTED"}
    ]
    if invalid_decisions:
        raise RuntimeError(f"Invalid decisions: {invalid_decisions}")

    missing_review_fields = [
        row["question_id"]
        for row in rows
        if not all(
            row.get(field, "").strip()
            for field in (
                "reviewer_name",
                "reviewer_role",
                "reviewed_at",
                "evidence_note",
            )
        )
    ]
    if missing_review_fields:
        raise RuntimeError(f"Missing review evidence: {missing_review_fields}")

    with input_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    print("Chunk-ID resolution complete.")
    print(f"Input updated: {input_path}")
    print(f"Backup: {backup}")
    print(f"Rows changed: {len(changed_rows)}")
    print("Changed question IDs:", ", ".join(changed_rows) or "none")
    print("Remaining placeholders: 0")


if __name__ == "__main__":
    main()
