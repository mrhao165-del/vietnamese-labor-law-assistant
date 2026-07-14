# Week 1 Ingestion

This pipeline turns `data/raw/labor_law.docx` into traceable article and clause JSONL. It preserves Vietnamese spelling and legal punctuation, and does not create embeddings or retrieval indexes.

## Inputs and metadata

Place the source at `data/raw/labor_law.docx`. Metadata belongs at `data/raw/source_metadata.json` and follows `SourceMetadata`: `document_id`, `document_name`, `source_file`, `data_snapshot_date`, and the DOCX SHA-256. Optional legal metadata remains `null` when unknown; do not use placeholder values. The current stable identity is filename-derived (`labor_law`) so historical chunk IDs and benchmark provenance remain valid.

Inspect source order with:

```powershell
uv run python scripts/inspect_docx.py
```

Run ingestion with:

```powershell
uv run python scripts/run_ingestion.py
```

`labor_law_articles.jsonl` has one complete article per line. `labor_law_clauses.jsonl` has one clause per line, or one whole-article chunk where no clauses exist. `validation_report.json` lists all parser findings and status. `docx_inventory.tsv` maps block indices back to the source.

Review the selections in `docs/week1_manual_validation.csv` using `docs/week1_manual_validation_guide.md`; do not mark rows PASS without inspecting their source blocks. The parser reports source preamble text as informational and preserves it outside legal articles. Article 219 contains quoted amendments to other laws that restart clause/point numbering; this is reported as `EMBEDDED_AMENDMENT_NUMBERING` information while retaining every source block and chunk.

Run checks with:

```powershell
uv run ruff format .
uv run ruff check .
uv run pyright
uv run pytest
uv run pre-commit run --all-files
```

Week 1 is complete only when source parsing, JSONL validation, repeatable output, automated checks, and the pending human review are all available. The CSV must not be treated as a completed legal review until a reviewer fills it in.
