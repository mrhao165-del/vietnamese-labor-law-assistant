"""Run a dense semantic retrieval query against the configured Qdrant collection."""

from __future__ import annotations

import argparse
import sys

from vietnamese_labor_law_assistant.common.settings import get_settings
from vietnamese_labor_law_assistant.retrieval.dense import DenseRetriever
from vietnamese_labor_law_assistant.retrieval.embeddings import BgeM3EmbeddingProvider
from vietnamese_labor_law_assistant.retrieval.qdrant_store import QdrantStore


def main() -> int:
    reconfigure_stdout = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure_stdout):
        reconfigure_stdout(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--article", type=int)
    parser.add_argument("--clause", type=int)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    retriever = DenseRetriever(BgeM3EmbeddingProvider(settings), QdrantStore(settings), settings)
    result = retriever.search(args.question, args.top_k, args.article, args.clause)
    if args.json:
        print(result.model_dump_json(indent=2))
        return 0
    print(f"Query: {result.query}\n")
    for item in result.results:
        clause = f", Khoản {item.clause_number}" if item.clause_number else ""
        print(f"{item.rank}. Score: {item.score:.4f}")
        print(f"   Điều {item.article_number}{clause}; Chunk ID: {item.chunk_id}")
        print(f"   Source blocks: {item.source_block_start}-{item.source_block_end}")
        print(f"   Source file: {item.source_file}")
        print(f"   Content preview: {item.content[:280]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
