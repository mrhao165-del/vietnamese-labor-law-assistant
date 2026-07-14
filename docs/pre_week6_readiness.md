# Pre-Week-6 readiness report

## 1. Scope

This audit stabilizes and verifies Week 1–5 implementation, data provenance, benchmark provenance, and production API honesty. It does not implement Week 6 retrieval wiring, MCP, an agent, a calculator, or citation-verification guardrails.

## 2. Repository version

`git status --branch --short` reports `No commits yet on main`; the repository has no Git commit to attribute to historical artefacts. Every provenance row therefore records Git commit as `UNKNOWN (no commits in repository)`.

## 3. Source data provenance

- Source: `data/raw/labor_law.docx`
- SHA-256: `1386441b1f513defdd55186d7e65b8432dcac87c2e0d78676de25facb9c5e6ff`
- Metadata: `data/raw/source_metadata.json`, valid against `SourceMetadata`; its SHA-256 matches the DOCX.
- Stable identity: `labor_law`. This intentionally preserves the existing deterministic chunk IDs; optional legal metadata is `null` rather than guessed.

The malformed placeholder JSON previously nested under `data/raw/Get-FileHash data/raw/` was moved to the required path and corrected from the actual DOCX checksum. Its snapshot date was corrected to the source file date (`2026-07-10`), which preserves the canonical corpus checksum.

## 4. Ingestion validation

The rerun produces 220 articles, 643 clauses, 284 points, and 680 chunks. `validation_report.json` is `PASS`, with no warnings or errors.

The report retains 11 inspectable informational findings:

- Ten source preamble blocks/lists are outside articles by design.
- Article 219 is an amendment article that quotes provisions of other laws; embedded clause and point numbering restarts inside quotations. The parser preserves every source block and chunk and reports `EMBEDDED_AMENDMENT_NUMBERING` rather than false duplicate/non-monotonic findings.

Two independent ingestion runs produced matching hashes:

- Articles: `03a11738f9796cb1664a0959d6d21235f5cde3adbbf2eaf6d75d4a185d22b822`
- Chunks: `3ce4672b64f0928796693ac8e1f1836acb043d380d9fa4e7e4c9d718835317b7`

The validation-report file hash changes only because `generated_at` is runtime metadata. Its content excluding that field is identical between the two runs.

`docs/week1_manual_validation.csv` contains 21 intentionally pending source-review selections, including Articles 1, 219, and 220. It was not falsely marked PASS; a qualified reviewer must complete it.

## 5. Evaluation dataset status

- Dataset: `data/evaluation/labor_law_eval_v1.jsonl`
- SHA-256: `56975dfcfc05b8f952e96637c27ceb8d5e48c5fcb3e7ccebb8f67c164bfe14c4`
- Questions: 60, with unique IDs; dev/test split is frozen at 42/18 with no overlap.
- Source chunks: `3ce4672b64f0928796693ac8e1f1836acb043d380d9fa4e7e4c9d718835317b7`.
- Reference validation: every expected chunk ID exists in the canonical corpus.

The manifest had a stale dataset hash (`2ed52…`) and a stale rereview status. It now records the actual checksum, frozen split, and 60 PASS review rows. However, 49 rows identify `ChatGPT_AI_PRE_REVIEW` and 11 identify `ChatGPT_ASSISTED_REREVIEW`; these are AI-assisted evidence, not independent human legal confirmation. The canonical candidate is therefore correctly marked `PROVISIONAL_AI_REVIEW_ONLY`, not finalized or official.

## 6. Week 3 baseline status

| Pipeline | Dataset / chunks | Index / models | Config / split | Run / Git | Readiness status |
|---|---|---|---|---|---|
| Dense retrieval | `labor_law_eval_v1.jsonl` / `56975…`; `labor_law_clauses.jsonl` / `3ce467…` | `dense_index_manifest.json`; BAAI/bge-m3 | `L0_DENSE`, top-k 10; dev/test metrics | `2026-07-13T14:23:21Z`; UNKNOWN | PROVISIONAL: checksums match, labels await human confirmation |
| Dense RAG | `labor_law_eval_v1.jsonl` / `56975…`; `labor_law_clauses.jsonl` / `3ce467…` | local Qdrant dense index; BAAI/bge-m3; Gemini OpenAI-compatible generator | Dense top-k 5; historical run | `2026-07-13T14:26:05Z`; UNKNOWN | PROVISIONAL: labels await human confirmation; historical LLM run is not replayed offline |

## 7. Week 4 hybrid retrieval status

| Pipeline group | Dataset / chunks | Index / models | Config / split | Run / Git | Readiness status |
|---|---|---|---|---|---|
| Dense, BM25S sparse, and RRF hybrid | `labor_law_eval_v1.jsonl` / `56975…`; `labor_law_clauses.jsonl` / `3ce467…` | `dense_index_manifest.json`; BM25S indexes `bm25s_whitespace` and `bm25s_underthesea`; BAAI/bge-m3 | `L0`, `L1`, `H1`, `L2`, `H2`; RRF k=60; dev/test metrics | `2026-07-13T14:41:47Z`; UNKNOWN | PROVISIONAL: checksum-matched; `H2` uses Underthesea as required; labels await human confirmation |

## 8. Week 5 reranker status

| Pipeline | Dataset / chunks | Index / models | Config / split | Run / Git | Readiness status |
|---|---|---|---|---|---|
| Reranker DEV selection | `labor_law_eval_v1.jsonl` / `56975…`; `labor_law_clauses.jsonl` / `3ce467…` | dense index + BM25S Underthesea; BAAI/bge-m3; BAAI/bge-reranker-v2-m3 | staged DEV; deterministic policy: Recall@5, MRR, Hit@1, P95, RSS, smaller tie-break | selection updated `2026-07-14T04:43:32Z`; UNKNOWN | PROVISIONAL: complete checkpoint evidence, labels await human confirmation |
| Reranker TEST | same canonical dataset / chunks | same as DEV | selected config only; TEST once, 18 questions | checkpoint `2026-07-14T04:47:17Z`; UNKNOWN | PROVISIONAL: complete selected TEST checkpoint, labels await human confirmation |
| Comparison, resource/token/error reports | same canonical dataset / chunks | report records BAAI/bge-reranker-v2-m3 and CPU resource scope | B0/B1 provenance, R1 DEV, R2 TEST | report timestamped historical artifact; UNKNOWN | PROVISIONAL: file says `OFFICIAL`, but this audit does not uphold that designation before human label confirmation |

The stored error analysis contains 10 actual checkpoint cases. No benchmark metric, prediction, or historical report was hand-edited during this audit.

## 9. Selected configuration

`R2_H2_C10_O5_L512_B1` is verified from `week5_dev_selection.json`:

- R2 / H2: hybrid dense + BM25S with Underthesea, then BAAI/bge-reranker-v2-m3.
- C10: 10 candidates.
- O5: 5 output contexts.
- L512: reranker max length 512.
- B1: batch size 1.

Its selection split is DEV; the stored TEST checkpoint uses only this selected configuration.

## 10. Test and quality results

- `uv sync --frozen`: completed from the existing environment; no model download.
- `uv run ruff format --check .`: pass (94 files already formatted).
- `uv run ruff check .`: pass.
- `uv run pyright`: 0 errors, 0 warnings, 0 information.
- `uv run pytest --cov=vietnamese_labor_law_assistant --cov-report=term-missing`: 71 passed, 1 third-party deprecation warning; total coverage 85.82% (threshold 82%).
- Secret scan: versionable source/configuration files contain only test fake credential values. A local `.env` exists, is Git-ignored and untracked, and was neither printed nor modified.

The tests are offline: mocks/fakes cover the LLM and model wrappers. No network API or model download was invoked by this stabilization work.

## 11. Known limitations

- FastAPI production is dense-only. `RETRIEVAL_MODE` values other than `dense` now fail clearly at app creation; they cannot silently fall back to `DenseRetriever`.
- The historical Week 3 Dense RAG result depends on an LLM and was not replayed.
- The source worksheet and evaluation labels still need independent human legal review.
- The repository has no Git commits, so historical run commit IDs cannot be reconstructed.

## 12. Deferred Week 6 work

- LegalRetriever facade/service.
- Unified dense/sparse/hybrid/rerank interface.
- Metadata filters.
- Query embedding cache.
- Complete structured retrieval logging.
- Direct search API.
- Production wiring of Hybrid + Reranker.
- Unit tests for the Retrieval Engine API.

## 13. Blocking issues

1. The 21 selected Week 1 source-review rows remain pending; they cannot be represented as completed manual review without an actual qualified review.
2. The 60 evaluation records are AI-assisted review records, not independently human-confirmed legal ground truth. Therefore the dataset cannot be finalized and Week 3–5 results cannot be called official.

## 14. Final readiness decision

**NOT READY.** Technical source, ingestion, checksum, split, configuration, API-honesty, and quality checks pass. The two review-evidence blockers above directly affect the legal correctness and official status required for Week 1–5 closure.
