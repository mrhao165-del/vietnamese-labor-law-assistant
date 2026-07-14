"""Dataset I/O, normalisation and source-grounded lookup helpers."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from pathlib import Path

from vietnamese_labor_law_assistant.ingestion.models import LegalChunk
from vietnamese_labor_law_assistant.ingestion.writers import read_chunks_jsonl

from .models import EvaluationQuestion


def normalise_question(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold()).strip()


def load_questions(path: Path) -> list[EvaluationQuestion]:
    return [
        EvaluationQuestion.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_questions(path: Path, questions: Iterable[EvaluationQuestion]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(question.model_dump_json() + "\n" for question in questions), encoding="utf-8"
    )


def load_chunk_map(path: Path) -> dict[str, LegalChunk]:
    return {chunk.chunk_id: chunk for chunk in read_chunks_jsonl(path)}


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
