# Week 2 Dense RAG

Week 2 builds a dense-only Vietnamese legal QA MVP:

`JSONL -> embedding text -> BGE-M3 -> Qdrant -> DenseRetriever -> Gemini (OpenAI-compatible SDK) -> citation formatter -> FastAPI`.

It uses FlagEmbedding BGE-M3 dense vectors, Transformers tokenizer, Qdrant, FastAPI, structlog, and the direct OpenAI SDK. It does not use BM25, RRF, reranking, LangChain, LangGraph, MCP, or a human-validated Week 3 evaluation set.

## Setup

Copy `.env.example` to `.env` and configure only values available to you. Keep `.env` private and never commit it. Gemini uses the direct OpenAI Python SDK compatibility endpoint; the model is always read from `LLM_MODEL` and the endpoint from `OPENAI_BASE_URL`.

```dotenv
OPENAI_API_KEY=your-gemini-api-key
OPENAI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
LLM_MODEL=gemini-3.1-flash-lite
LLM_PROVIDER=gemini_openai_compatible
```

No key is hard-coded. `scripts/check_llm.py` reports only provider, model, success/failure and latency.

Check Torch and device policy:

```powershell
uv run python -c "import torch; print(torch.__version__, torch.cuda.is_available(), torch.version.cuda)"
```

`EMBEDDING_DEVICE=auto` selects CUDA only when Torch reports it. Set `cpu` to force CPU. Set `cuda` only when CUDA is available. FP16 defaults to CUDA only. On CUDA OOM, lower `EMBEDDING_BATCH_SIZE` to `2` or `1`; do not silently skip chunks.

The default development backend is persistent local Qdrant:

```dotenv
QDRANT_MODE=local
QDRANT_LOCAL_PATH=data/qdrant_local
```

It survives process exits and is shared by the indexer, CLI, evaluation and API factory. Do not run the indexer and API simultaneously against the same local path: local Qdrant can lock the storage. Local Qdrant does not create server payload indexes; the same payload schema and deterministic UUID point IDs are retained. `data/qdrant_local/` is ignored by Git.

If Docker is available, service mode remains supported:

```powershell
docker compose -f compose.qdrant.yml up -d
docker compose -f compose.qdrant.yml down
```

Set `QDRANT_MODE=remote` and `QDRANT_URL=http://127.0.0.1:6333` for that mode. Docker full-stack deployment is outside Week 2.

If Hugging Face cache is on a constrained volume, set `HF_HOME` in your local environment to a directory with free space before the first BGE-M3 load. To recover from an interrupted download, remove only `.incomplete` files or the clearly broken `models--BAAI--bge-m3` snapshot; do not clear unrelated Hugging Face models. BGE-M3 runs with `use_fp16=False` on CPU.

## Index and search

The 1024 setting is this project's operational latency/resource limit, not a claimed BGE-M3 hard limit. Token validation uses the BGE-M3 Transformers tokenizer and does not silently truncate legal text.

```powershell
uv run python scripts/index_dense.py --dry-run
uv run python scripts/index_dense.py
uv run python scripts/query_dense.py "Quy định về chấm dứt hợp đồng lao động là gì?" --top-k 5
uv run python scripts/create_week2_smoke_dataset.py
uv run python scripts/run_week2_dense_smoke.py
```

The index manifest and tokenizer report are written to `data/processed`. The original title-based
smoke evaluation is retained as historical evidence only. The current non-synthetic DEV baseline is:

```powershell
uv run python scripts/run_week2_current_dense_baseline.py
uv run python scripts/verify_week2_current_dense_baseline.py
```

It evaluates 42 frozen DEV questions (23 retrieval-eligible) against current corpus and dataset
checksums. BAAI/bge-m3, its tokenizer, Qdrant cosine vectors (1024 dimensions), and CPU produced
Hit@1 0.869565, Recall@5 1.0, MRR 0.921739, mean latency 620.181 ms and P95 263.689 ms. The
artefact explicitly records `synthetic=false`.

## API

After Qdrant is indexed and OpenAI settings are configured:

```powershell
uv run uvicorn vietnamese_labor_law_assistant.api.main:app --host 127.0.0.1 --port 8000
```

Open Swagger at `http://127.0.0.1:8000/docs`.

```powershell
curl -X POST http://127.0.0.1:8000/api/v1/query -H "Content-Type: application/json" -d '{"question":"Quy định liên quan đến hợp đồng lao động là gì?","top_k":5}'
```

Citation objects include `source_endpoint`; open it at `http://127.0.0.1:8000/api/v1/sources/{chunk_id}`. `/health` only confirms the process; `/ready` also checks Qdrant collection state and LLM configuration without calling OpenAI.

Logs are structured and include bounded question previews, chunk IDs, and latency. They do not log keys, vectors, full prompts, or full contexts by default.

Use `GET /api/v1/sources/{chunk_id}` from a returned citation to inspect the server-owned source metadata and content hash.

## Checks and limitations

```powershell
uv run ruff format .
uv run ruff check .
uv run pyright
uv run pytest
uv run pre-commit run --all-files
```

The ordinary test suite never calls Gemini or downloads BGE-M3. Real connectivity is an explicit manual `uv run python scripts/check_llm.py` step; keep it out of default tests.

This system supports legal lookup only and does not replace professional legal advice. It remains dense-only; citation support verification and the official 60-question evaluation belong to later work.
