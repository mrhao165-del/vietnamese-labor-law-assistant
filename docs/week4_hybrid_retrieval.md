# Week 4 hybrid retrieval

L1 uses whitespace tokenisation; L2 uses Underthesea segmentation over the same NFC-normalised lexical text. BM25S is persistent and separate from Qdrant; FastEmbed BM25 and Qdrant sparse vectors are not used. Custom RRF uses `sum(1/(60 + rank))`, never adds cosine and BM25 scores directly.

Run `uv run python scripts/index_bm25s.py --tokenizer whitespace`, repeat with `underthesea`, then `uv run python scripts/run_week4_retrieval_benchmark.py`. The stored results match the canonical dataset and chunk checksums, but remain PROVISIONAL until independent human legal review of Week 3 labels completes. There is no reranker.
