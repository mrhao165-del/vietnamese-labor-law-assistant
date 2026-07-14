"""Persistent BM25S index with explicit document-position mapping."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import bm25s

from vietnamese_labor_law_assistant.ingestion.models import LegalChunk

from .lexical_text import build_lexical_text
from .lexical_tokenizers import LexicalTokenizer


class Bm25Store:
    def __init__(
        self, path: Path, tokenizer: LexicalTokenizer, chunks: list[LegalChunk] | None = None
    ) -> None:
        self.path, self.tokenizer, self.chunks = path, tokenizer, chunks or []
        self.index: Any | None = None

    def build(self) -> None:
        self.index = bm25s.BM25()
        self.index.index([self.tokenizer.tokenize(build_lexical_text(c)) for c in self.chunks])

    def save(self, manifest: dict[str, Any]) -> None:
        if self.index is None:
            raise RuntimeError("BM25 index is not built")
        self.path.mkdir(parents=True, exist_ok=True)
        self.index.save(str(self.path))
        (self.path / "chunks.json").write_text(
            json.dumps([c.model_dump(mode="json") for c in self.chunks], ensure_ascii=False),
            encoding="utf-8",
        )
        (self.path / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def load(self) -> None:
        self.index = bm25s.BM25.load(str(self.path))
        from vietnamese_labor_law_assistant.ingestion.models import LegalChunk as C

        self.chunks = [
            C.model_validate(x)
            for x in json.loads((self.path / "chunks.json").read_text(encoding="utf-8"))
        ]

    def search(self, query: str, k: int) -> list[tuple[LegalChunk, float]]:
        if self.index is None:
            raise RuntimeError("BM25 index is not loaded")
        results, scores = self.index.retrieve(
            [self.tokenizer.tokenize(query)], k=k, show_progress=False
        )
        return [(self.chunks[int(i)], float(s)) for i, s in zip(results[0], scores[0], strict=True)]

    def count(self) -> int:
        return len(self.chunks)
