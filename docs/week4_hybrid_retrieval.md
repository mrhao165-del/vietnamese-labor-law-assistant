# Week 4 hybrid retrieval

L1 uses whitespace tokenisation; L2 uses Underthesea segmentation over the same NFC-normalised lexical text. BM25S is persistent and separate from Qdrant; FastEmbed BM25 and Qdrant sparse vectors are not used. Custom RRF uses `sum(1/(60 + rank))`, never adds cosine and BM25 scores directly.

Historical provisional results remain archived. The current aligned comparison is generated and
strictly recomputed with:

```powershell
uv run python scripts/run_week4_current_retrieval_benchmark.py
uv run python scripts/verify_week4_current_retrieval.py
```

All four pipelines use the same 42 frozen DEV IDs and current checksums. Hit@1/MRR are: Dense
0.869565/0.921739; whitespace BM25S 0.391304/0.644928; Underthesea BM25S
0.652174/0.800725; Dense+Underthesea custom RRF 0.782609/0.884058. Recall@5 is 1.0 for all.
Per-question predictions prove deduplication; no current artefact has a provisional status.
