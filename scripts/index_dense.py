"""Validate, embed, and idempotently index Week 1 chunks into Qdrant."""

from __future__ import annotations

import argparse
import json
import platform
import sys
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

from vietnamese_labor_law_assistant.common.settings import Settings
from vietnamese_labor_law_assistant.ingestion.identifiers import calculate_file_sha256
from vietnamese_labor_law_assistant.ingestion.writers import read_chunks_jsonl
from vietnamese_labor_law_assistant.retrieval.embeddings import BgeM3EmbeddingProvider
from vietnamese_labor_law_assistant.retrieval.qdrant_store import VECTOR_NAME, QdrantStore
from vietnamese_labor_law_assistant.retrieval.text_builder import (
    EMBEDDING_TEXT_VERSION,
    build_embedding_text,
)
from vietnamese_labor_law_assistant.retrieval.tokenization import (
    TokenCount,
    build_token_report,
    count_embedding_tokens,
    load_tokenizer,
)

ROOT = Path(__file__).resolve().parents[1]


def _write_json(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", type=Path, default=Path("data/processed/labor_law_clauses.jsonl")
    )
    parser.add_argument("--collection")
    parser.add_argument("--qdrant-mode", choices=["remote", "local"])
    parser.add_argument("--qdrant-local-path", type=Path)
    parser.add_argument("--batch-size", type=int)
    parser.add_argument("--max-length", type=int)
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"])
    parser.add_argument("--recreate", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    overrides = {
        key: value
        for key, value in {
            "qdrant_collection": args.collection,
            "qdrant_mode": args.qdrant_mode,
            "qdrant_local_path": args.qdrant_local_path,
            "embedding_batch_size": args.batch_size,
            "embedding_max_length": args.max_length,
            "embedding_device": args.device,
        }.items()
        if value is not None
    }
    settings = Settings(**overrides)
    chunks = read_chunks_jsonl(args.input)
    if args.limit is not None:
        chunks = chunks[: args.limit]
    if not chunks:
        print("No chunks available for indexing.", file=sys.stderr)
        return 2
    texts = [build_embedding_text(chunk) for chunk in chunks]
    tokenizer = load_tokenizer(settings.embedding_model)
    counts = [
        TokenCount(
            chunk.chunk_id,
            chunk.article_number,
            chunk.clause_number,
            chunk.source_block_start,
            count_embedding_tokens(tokenizer, text),
        )
        for chunk, text in zip(chunks, texts, strict=True)
    ]
    report = build_token_report(counts, settings.embedding_max_length, settings.embedding_model)
    _write_json(ROOT / "data/processed/embedding_validation_report.json", report)
    if report["over_limit_count"] and settings.long_chunk_policy == "error":
        print("Token validation failed; no legal content was truncated.", file=sys.stderr)
        return 1
    if args.dry_run:
        print(f"Validated {len(chunks)} chunks; token report written to data/processed.")
        return 0
    import FlagEmbedding
    import torch
    import transformers

    provider = BgeM3EmbeddingProvider(settings)
    vectors = provider.embed_documents(texts)
    source_sha256 = calculate_file_sha256(args.input)
    store = QdrantStore(settings)
    point_count_before_index = store.count_points() if store.collection_exists() else 0
    sample_chunk_ids = [chunk.chunk_id for chunk in chunks[:3]]
    point_ids_before = {
        chunk_id: store.get_point_id_by_chunk_id(chunk_id)
        for chunk_id in sample_chunk_ids
        if store.collection_exists()
    }
    store.ensure_collection(provider.dimension, recreate=args.recreate)
    store.create_payload_indexes()
    store.upsert_points(chunks, vectors, source_sha256)
    point_count_after_index = store.count_points()
    point_ids_after = {
        chunk_id: store.get_point_id_by_chunk_id(chunk_id) for chunk_id in sample_chunk_ids
    }
    idempotence_checked = bool(point_ids_before) and not args.recreate
    manifest = {
        "pipeline_version": "week2-v1",
        "embedding_text_version": EMBEDDING_TEXT_VERSION,
        "source_jsonl": args.input.as_posix(),
        "source_jsonl_sha256": source_sha256,
        "embedding_model": settings.embedding_model,
        "tokenizer_name": settings.embedding_model,
        "embedding_device": provider.device,
        "use_fp16": provider.use_fp16,
        "batch_size": settings.embedding_batch_size,
        "max_length": settings.embedding_max_length,
        "vector_name": VECTOR_NAME,
        "vector_dimension": provider.dimension,
        "distance": "Cosine",
        "qdrant_collection": store.collection_name,
        "qdrant_mode": settings.qdrant_mode,
        "chunk_count_input": len(chunks),
        "point_count_before_index": point_count_before_index,
        "point_count_after_index": point_count_after_index,
        "failed_chunk_count": 0,
        "idempotence": {
            "checked": idempotence_checked,
            "point_count_unchanged": (
                point_count_before_index == point_count_after_index if idempotence_checked else None
            ),
            "sample_chunk_ids": sample_chunk_ids,
            "sample_point_uuids_unchanged": (
                point_ids_before == point_ids_after if idempotence_checked else None
            ),
        },
        "indexed_at": datetime.now(UTC).isoformat(),
        "python_version": platform.python_version(),
        "torch_version": torch.__version__,
        "torch_cuda_version": torch.version.cuda,
        "cuda_available": torch.cuda.is_available(),
        "flagembedding_version": getattr(FlagEmbedding, "__version__", "unknown"),
        "transformers_version": transformers.__version__,
        "qdrant_client_version": version("qdrant-client"),
    }
    _write_json(ROOT / "data/processed/dense_index_manifest.json", manifest)
    print(
        json.dumps(
            {
                "chunks": len(chunks),
                "points": manifest["point_count_after_index"],
                "dimension": provider.dimension,
                "device": provider.device,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
