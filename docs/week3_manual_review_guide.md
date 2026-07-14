# Week 3 manual review

Review CSV: `data/evaluation/labor_law_eval_v1_review.csv`.

For each row, open its source chunk with the API source endpoint or JSONL; confirm the Điều/Khoản, naturalness, ambiguity/out-of-scope behavior, and that the short reference does not exceed the source. Set `review_status` to `PASS`, `NEEDS_REVISION`, or `REJECTED`, add reviewer/notes, then run `uv run python scripts/apply_week3_manual_review.py` and `uv run python scripts/validate_week3_evaluation_dataset.py --require-human-reviewed`.

All 60 current records have AI-assisted review/rereview evidence, but the dataset remains `PROVISIONAL_AI_REVIEW_ONLY` until an independent human legal reviewer confirms the labels. Do not change expected labels after inspecting benchmark results.
