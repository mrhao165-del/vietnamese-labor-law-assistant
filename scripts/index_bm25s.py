"""Build one persistent BM25S lexical index."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from vietnamese_labor_law_assistant.ingestion.identifiers import calculate_file_sha256
from vietnamese_labor_law_assistant.ingestion.writers import read_chunks_jsonl
from vietnamese_labor_law_assistant.retrieval.bm25_store import Bm25Store
from vietnamese_labor_law_assistant.retrieval.lexical_text import LEXICAL_TEXT_VERSION
from vietnamese_labor_law_assistant.retrieval.lexical_tokenizers import get_lexical_tokenizer

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--tokenizer", choices=["whitespace", "underthesea"], required=True)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--rebuild", action="store_true")
    a = p.parse_args()
    chunks = read_chunks_jsonl(ROOT / "data/processed/labor_law_clauses.jsonl")
    tok = get_lexical_tokenizer(a.tokenizer)
    path = ROOT / f"data/processed/lexical/bm25s_{a.tokenizer}"
    if a.dry_run:
        print({"chunks": len(chunks), "sample_tokens": tok.tokenize(chunks[0].content)[:8]})
        return 0
    if path.exists() and not a.rebuild:
        raise SystemExit("index exists; use --rebuild only when replacement is intentional")
    store = Bm25Store(path, tok, chunks)
    store.build()
    manifest = {
        "index_version": "week4-v1",
        "lexical_text_version": LEXICAL_TEXT_VERSION,
        "tokenizer_name": tok.name,
        "tokenizer_version": tok.version,
        "source_jsonl_sha256": calculate_file_sha256(
            ROOT / "data/processed/labor_law_clauses.jsonl"
        ),
        "chunk_count": len(chunks),
        "unique_chunk_count": len({c.chunk_id for c in chunks}),
        "created_at": datetime.now(UTC).isoformat(),
        "bm25s_version": "0.3.9",
    }
    store.save(manifest)
    store = Bm25Store(path, tok)
    store.load()
    print(
        json.dumps(
            {
                "count": store.count(),
                "path": str(path),
                "manifest_sha256": hashlib.sha256(
                    (path / "manifest.json").read_bytes()
                ).hexdigest(),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
