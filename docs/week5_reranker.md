# Week 5 reranker

`R2_H2_C10_O5_L512_B1` is the DEV-selected configuration. TEST was run once only for that selected configuration. The official comparison distinguishes Week 4 baseline provenance from real reranker checkpoints.

## Final configuration

- `FINAL_RETRIEVAL_PIPELINE=R2_H2_RERANK`
- `FINAL_CANDIDATE_K=10`
- `FINAL_RERANK_OUTPUT_K=5`
- `FINAL_RERANKER_MAX_LENGTH=512`
- `FINAL_RERANKER_BATCH_SIZE=1`

Reranking is not made the application default by this benchmark. Production FastAPI supports only `RETRIEVAL_MODE=dense`; benchmark-only hybrid/reranker modes fail fast until Week 6 wires them into the production path. The stored Week 5 test checkpoint matches the canonical dataset and chunk checksums, but its official designation remains provisional pending independent human legal review of the evaluation labels.
