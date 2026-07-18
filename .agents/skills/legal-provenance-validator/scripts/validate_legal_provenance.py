"""Validate a legal basis only against the fixed canonical clause JSONL snapshot."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _repository_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "pyproject.toml").is_file():
            return candidate
    raise RuntimeError("could not locate repository root")


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--article", type=int)
    parser.add_argument("--clause", type=int)
    parser.add_argument("--point")
    parser.add_argument("--chunk-id")
    status = parser.add_mutually_exclusive_group()
    status.add_argument("--external-regulation-required", action="store_true")
    status.add_argument("--out-of-scope", action="store_true")
    arguments = parser.parse_args()
    if arguments.clause is not None and arguments.article is None:
        parser.error("--clause requires --article")
    if arguments.point is not None and arguments.clause is None:
        parser.error("--point requires --clause")
    return arguments


def _matches(record: dict[str, Any], arguments: argparse.Namespace) -> bool:
    if arguments.article is not None and record.get("article_number") != arguments.article:
        return False
    if arguments.clause is not None and record.get("clause_number") != arguments.clause:
        return False
    if arguments.chunk_id is not None and record.get("chunk_id") != arguments.chunk_id:
        return False
    labels = record.get("point_labels")
    return arguments.point is None or (isinstance(labels, list) and arguments.point in labels)


def main() -> int:
    arguments = _parse_arguments()
    if arguments.out_of_scope:
        print(json.dumps({"status": "OUT_OF_SCOPE", "matches": 0}, ensure_ascii=False))
        return 0
    path = _repository_root() / "data" / "processed" / "labor_law_clauses.jsonl"
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    matches = [record for record in records if _matches(record, arguments)]
    status = (
        "EXTERNAL_REGULATION_REQUIRED" if arguments.external_regulation_required else "SUPPORTED"
    )
    print(
        json.dumps(
            {
                "status": status if matches else "OUT_OF_SCOPE",
                "matches": len(matches),
                "canonical_source": "data/processed/labor_law_clauses.jsonl",
                "chunk_ids": [record["chunk_id"] for record in matches],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if matches else 1


if __name__ == "__main__":
    sys.exit(main())
