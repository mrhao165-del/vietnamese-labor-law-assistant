# Week 1 Manual Validation

The CSV template is intentionally pending. It is not evidence of a completed legal review.

1. Open `data/raw/labor_law.docx` and locate the selected article.
2. Find the matching object in `data/processed/labor_law_articles.jsonl` by `article_number`.
3. Compare the Chapter, Mục, article title, and every clause count with the DOCX.
4. Compare every point label, including `đ`, and verify that no sentence or table heading is missing.
5. Check every clause chunk for the article in `data/processed/labor_law_clauses.jsonl`.
6. Verify `source_block_start`, `source_block_end`, and `source_paragraph_indexes` against `data/processed/docx_inventory.tsv`.
7. Set `review_status` to `PASS` or `FAIL`, identify the reviewer, and record any mismatch in `notes`.

Do not change the source DOCX during this review. Parser findings should be recorded in the CSV and then addressed by changing the parser or its tests.
