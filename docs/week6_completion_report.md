# Week 6 completion report

## Verdict

**WEEK6_COMPLETE.** Pre-Week-6 remained `READY`; no Week 7 implementation was made.

## Delivered

- `LegalRetriever` is an LLM-independent production service with dense, Underthesea BM25S,
  hybrid RRF, dense rerank and hybrid rerank modes.
- The production default is `hybrid_underthesea_rerank` using locked
  `R2_H2_C10_O5_L512_B1` (C10/O5/L512/B1).
- Metadata filters have identical dense/sparse/hybrid semantics; BM25 applies deterministic
  filtering before top-k selection.
- Bounded thread-safe query embedding LRU, structured latency logging, typed errors,
  mode-specific readiness, direct search/article/clause endpoints and RAG alias are present.
- `RagService` uses a retrieval protocol; legacy `DenseRagService` and dense factory remain
  compatible for historic scripts.

## Locked configuration verification

The independently reviewed dataset SHA-256 is
`19440059cf4c31a487b30db10b6d5eb8bb781290d642936b1ba25e8eb0697110`; corpus SHA-256 is
`62d4f98ba376260231663c779824651f60b82c0f968244ace95e478d20dbbcd3` (682 chunks).

| Split | Questions | Recall@5 | MRR | Hit@1 | Mean / p95 latency | Errors |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| DEV | 42 | 1.0 | 0.9782608696 | 0.9565217391 | 4459.48 / 9062.63 ms | 0 |
| TEST (one locked run) | 18 | 1.0 | 1.0 | 1.0 | 4066.13 / 8514.33 ms | 0 |

TEST was not used for tuning; historical Week 3–5 metrics were not changed.

## Quality evidence

- `uv sync`: PASS.
- Ruff format/lint: PASS.
- Pyright: 0 errors.
- `uv run pytest --cov`: 95 passed, coverage 82.38% (threshold 82%).
- Independent review and evaluation validation: PASS (60 rows/questions, 0 errors).
- Ingestion reproducibility and pre-Week-6 provenance integration: PASS.
- API regression: 3 passed; retrieval/Week 5 regression group: 41 passed.
- Real locked verification: PASS on DEV and one TEST pass.

## Scope and next step

`.gitignore`, `handover.md`, `coverage.json`, independent-review evidence, evaluation labels,
corpus/index artifacts and historical benchmark metrics were not changed by Week 6. Existing user
changes were preserved. The next roadmap item is Week 7 — MCP Legal Retrieval Server; it is not
implemented here.
