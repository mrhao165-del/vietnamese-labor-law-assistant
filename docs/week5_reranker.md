# Week 5 reranker

`R2_H2_C10_O5_L512_B1` is the DEV-selected configuration. TEST was run once only for that selected configuration. The official comparison distinguishes Week 4 baseline provenance from real reranker checkpoints.

## Final configuration

- `FINAL_RETRIEVAL_PIPELINE=R2_H2_RERANK`
- `FINAL_CANDIDATE_K=10`
- `FINAL_RERANK_OUTPUT_K=5`
- `FINAL_RERANKER_MAX_LENGTH=512`
- `FINAL_RERANKER_BATCH_SIZE=1`

Historical provisional checkpoints remain immutable. The current atomic/resumable benchmark is:

```powershell
uv run python scripts/run_week5_current_reranker_benchmark.py
uv run python scripts/verify_week5_current_reranker.py
```

Ten DEV configurations cover Dense/Hybrid candidates 10/20/30, output 5/8, max length 512/768,
batch 1, and CPU fallback. DEV alone selects `R2_H2_C10_O5_L512_B1`; TEST is run once. Locked
DEV Hit@1/Recall@5/MRR is 0.956522/1.0/0.978261 with mean/P95 3706.07/4999.47 ms. TEST is
1.0/1.0/1.0 with mean/P95 3633.57/4532.19 ms. Per-question output and ten diagnostic rows are
stored in the current report.
