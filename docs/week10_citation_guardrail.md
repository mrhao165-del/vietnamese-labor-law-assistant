# Week 10 Citation Guardrail

## Scope and architecture

Week 10 verifies every atomic legal claim after generation and before a RAG or Agent response is
released. It does not change the locked retrieval configuration or calculator rules.

1. Syntax parses and normalizes Vietnamese `Điều`, `Khoản`, and `Điểm` citations.
2. Existence/membership resolves server-owned chunk IDs against the lazy, read-only canonical
   snapshot and the evidence retrieved for the current request.
3. Grounding applies legal-reference and numeric consistency, exact/deterministic support, an
   injectable semantic scorer, and only then an optional structured LLM judge for ambiguity.

An atomic claim has a stable ID, text, cited context IDs, parsed legal references, status, reason
codes, evidence IDs, and a bounded diagnostic score. Status is one of `SUPPORTED`,
`PARTIALLY_SUPPORTED`, `UNSUPPORTED`, or `INSUFFICIENT_CONTEXT`.

## Fail-closed behavior and route evidence

`SUPPORTED` preserves the answer. Partial support is projected with a warning and without asserting
unsupported material as certain. Unsupported or insufficient-context answers are replaced with a
safe insufficient-basis response. Invalid citations are never presented as valid citations.

The finite Agent flow is:

```text
route -> MCP tools -> answer -> structural verification -> claim guardrail -> final result
```

Retrieval-only evidence comes from canonical IDs returned by retrieval MCP. Calculator-only evidence
comes from the existing rule provenance `source_chunk_id`; no retrieval call is added. Combined
routes deduplicate retrieval and calculator evidence. Out-of-scope refusals make zero tool calls and
produce `INSUFFICIENT_CONTEXT` with `OUT_OF_SCOPE_REFUSAL`.

Tests create temporary canonical snapshots or inject the read-only registry; production validation
is never relaxed for fake IDs. The judge cannot override a nonexistent/not-retrieved citation, legal
reference mismatch, or numeric contradiction. Missing credentials, timeout, transport errors, and
invalid structured output fail closed. Live judge execution is optional and disabled offline.

## Dataset and verification

The 40-case dataset covers all 22 required categories: full support, missing/nonexistent/not-in-
context citations, wrong clause/point, numeric contradiction, partial compound claims, misleading
keyword overlap, empty/duplicate/malformed citations, calculator and combined routes, out-of-scope,
judge timeout/invalid output, mixed claims, external regulation, Unicode spacing, and semantic
non-support despite a matching legal reference.

The loader enforces closed enums, unique IDs, all four Agent routes/statuses, category completeness,
calculator/combined provenance, judge behavior, canonical membership, and the two intentional
negative membership cases. The verifier additionally enforces required reasons, protected canonical
checksum, zero provenance failures, zero false-supported results, and metric thresholds.

```powershell
uv run pytest tests/unit/guardrails tests/unit/evaluation/test_week10_guardrails.py
uv run pytest tests/integration/test_week10_guardrail_rag.py
uv run pytest tests/integration/test_week10_guardrail_agent.py
uv run pytest tests/end_to_end/test_week10_question_to_verified_answer.py
uv run python scripts/run_week10_guardrail_evaluation.py
uv run python scripts/verify_week10_guardrail.py
```

Final deterministic metrics: citation existence 1.0, retrieved membership 1.0, claim-status accuracy
1.0, macro F1 1.0, unsupported and insufficient-context recall 1.0, out-of-scope refusal accuracy
1.0, and false-supported rate 0.0. The calculator remains limited to Articles 20/35; frontend,
containers, and a live-LLM benchmark are outside Week 10.
