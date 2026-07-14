# Coverage audit after improvement

- Line coverage: 89.71%
- Statements: 1496
- Missed: 154
- Tests: 39
- Production source behavior changed: no
- Default tests call external services: no

## Module coverage

| Module | Statements | Missed | Coverage | Priority |
|---|---:|---:|---:|---|
| src\vietnamese_labor_law_assistant\__init__.py | 2 | 1 | 50.00% | P1 |
| src\vietnamese_labor_law_assistant\agent\__init__.py | 0 | 0 | 100.00% | P1 |
| src\vietnamese_labor_law_assistant\api\__init__.py | 0 | 0 | 100.00% | P1 |
| src\vietnamese_labor_law_assistant\api\dependencies.py | 33 | 18 | 45.45% | P1 |
| src\vietnamese_labor_law_assistant\api\main.py | 81 | 11 | 86.42% | P1 |
| src\vietnamese_labor_law_assistant\common\__init__.py | 0 | 0 | 100.00% | P1 |
| src\vietnamese_labor_law_assistant\common\logging.py | 10 | 0 | 100.00% | P1 |
| src\vietnamese_labor_law_assistant\common\settings.py | 56 | 3 | 94.64% | P1 |
| src\vietnamese_labor_law_assistant\evaluation\__init__.py | 0 | 0 | 100.00% | P1 |
| src\vietnamese_labor_law_assistant\evaluation\dataset.py | 20 | 1 | 95.00% | P1 |
| src\vietnamese_labor_law_assistant\evaluation\metrics.py | 53 | 3 | 94.34% | P1 |
| src\vietnamese_labor_law_assistant\evaluation\models.py | 67 | 6 | 91.04% | P1 |
| src\vietnamese_labor_law_assistant\generation\__init__.py | 0 | 0 | 100.00% | P1 |
| src\vietnamese_labor_law_assistant\generation\citations.py | 43 | 3 | 93.02% | P1 |
| src\vietnamese_labor_law_assistant\generation\llm.py | 34 | 2 | 94.12% | P1 |
| src\vietnamese_labor_law_assistant\generation\models.py | 56 | 0 | 100.00% | P1 |
| src\vietnamese_labor_law_assistant\generation\prompts.py | 31 | 5 | 83.87% | P1 |
| src\vietnamese_labor_law_assistant\generation\service.py | 42 | 5 | 88.10% | P1 |
| src\vietnamese_labor_law_assistant\guardrails\__init__.py | 0 | 0 | 100.00% | P1 |
| src\vietnamese_labor_law_assistant\ingestion\__init__.py | 0 | 0 | 100.00% | P1 |
| src\vietnamese_labor_law_assistant\ingestion\chunking.py | 41 | 2 | 95.12% | P1 |
| src\vietnamese_labor_law_assistant\ingestion\identifiers.py | 15 | 0 | 100.00% | P1 |
| src\vietnamese_labor_law_assistant\ingestion\models.py | 165 | 10 | 93.94% | P1 |
| src\vietnamese_labor_law_assistant\ingestion\normalize.py | 19 | 0 | 100.00% | P1 |
| src\vietnamese_labor_law_assistant\ingestion\parser.py | 166 | 9 | 94.58% | P1 |
| src\vietnamese_labor_law_assistant\ingestion\patterns.py | 49 | 3 | 93.88% | P1 |
| src\vietnamese_labor_law_assistant\ingestion\validation.py | 70 | 8 | 88.57% | P1 |
| src\vietnamese_labor_law_assistant\ingestion\writers.py | 32 | 3 | 90.62% | P1 |
| src\vietnamese_labor_law_assistant\retrieval\__init__.py | 0 | 0 | 100.00% | P1 |
| src\vietnamese_labor_law_assistant\retrieval\bm25_store.py | 33 | 0 | 100.00% | P1 |
| src\vietnamese_labor_law_assistant\retrieval\dense.py | 34 | 1 | 97.06% | P1 |
| src\vietnamese_labor_law_assistant\retrieval\embeddings.py | 62 | 18 | 70.97% | P1 |
| src\vietnamese_labor_law_assistant\retrieval\hybrid.py | 18 | 0 | 100.00% | P1 |
| src\vietnamese_labor_law_assistant\retrieval\lexical_normalization.py | 9 | 0 | 100.00% | P1 |
| src\vietnamese_labor_law_assistant\retrieval\lexical_text.py | 11 | 0 | 100.00% | P1 |
| src\vietnamese_labor_law_assistant\retrieval\lexical_tokenizers.py | 24 | 3 | 87.50% | P1 |
| src\vietnamese_labor_law_assistant\retrieval\models.py | 61 | 2 | 96.72% | P1 |
| src\vietnamese_labor_law_assistant\retrieval\qdrant_store.py | 79 | 31 | 60.76% | P1 |
| src\vietnamese_labor_law_assistant\retrieval\rrf.py | 13 | 0 | 100.00% | P1 |
| src\vietnamese_labor_law_assistant\retrieval\sparse.py | 18 | 0 | 100.00% | P1 |
| src\vietnamese_labor_law_assistant\retrieval\text_builder.py | 26 | 4 | 84.62% | P1 |
| src\vietnamese_labor_law_assistant\retrieval\tokenization.py | 23 | 2 | 91.30% | P1 |

## Regression protection

The official dataset and Week 3/4 artifact SHA-256 values match the baseline values recorded before coverage work.
