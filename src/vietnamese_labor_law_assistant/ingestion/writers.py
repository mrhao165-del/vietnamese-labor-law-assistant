"""Deterministic UTF-8 JSONL readers and writers backed by Pydantic schemas."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from .models import LegalArticle, LegalChunk

ModelT = TypeVar("ModelT", bound=BaseModel)


def write_jsonl(path: Path, records: Sequence[BaseModel]) -> None:
    """Write ordered records as deterministic UTF-8 JSONL with a final newline."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(
                json.dumps(
                    record.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":")
                )
            )
            handle.write("\n")


def _read_jsonl(path: Path, model: type[ModelT]) -> list[ModelT]:
    records: list[ModelT] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if line.strip():
                try:
                    records.append(model.model_validate_json(line))
                except ValueError as exc:
                    raise ValueError(f"Invalid JSONL in {path} line {line_number}: {exc}") from exc
    return records


def write_articles_jsonl(path: Path, articles: Sequence[LegalArticle]) -> None:
    """Write legal articles."""
    write_jsonl(path, articles)


def write_chunks_jsonl(path: Path, chunks: Sequence[LegalChunk]) -> None:
    """Write retrieval chunks."""
    write_jsonl(path, chunks)


def read_articles_jsonl(path: Path) -> list[LegalArticle]:
    """Read and schema-validate article JSONL."""
    return _read_jsonl(path, LegalArticle)


def read_chunks_jsonl(path: Path) -> list[LegalChunk]:
    """Read and schema-validate chunk JSONL."""
    return _read_jsonl(path, LegalChunk)
