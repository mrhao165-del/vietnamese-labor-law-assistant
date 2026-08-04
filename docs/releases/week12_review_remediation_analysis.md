# Week 12 review remediation analysis

Status: **root-cause analysis complete; implementation not yet applied**

This analysis uses the immutable reviewed packet at SHA-256
`2a03422784aa3586ace61f3ee9243bc2a27f6c6d3c29ee35848bbe542ca4a8f7` and the canonical
processed JSONL only. The legal provenance validator confirmed Article 35(2)(b), Article 35(2)(d),
Article 97(4), and all target Articles 20, 34, 35, 43, and 169. No Internet source or personal legal
knowledge was used to fill a gap.

The packet contains public traces rather than complete internal RouterOutput/MCP/claim payloads.
Where a claim is described below, it is reconstructed from the captured public answer and is not
represented as an unavailable internal trace.

## W12-001

Question: “Điều 20, Điều 35 và Điều 169 quy định gì?”  
Decision: FAIL.

The route and all three `get_article` calls were correct. Canonical retrieval contains 2 Article 20
chunks, 2 Article 35 chunks, and 5 Article 169 chunks. A read-only diagnostic of the current
projection retains all nine, including one seed per target. The reviewed live response nevertheless
ended as `INSUFFICIENT_CONTEXT` with no claims or citations.

Root cause: the failure is in the LLM answer/guardrail handoff, not MCP retrieval or canonical-ID
deduplication. The existing deterministic tests prove two-target fairness but do not prove that a
complete three-target request survives generation and verified fallback.

Generic strategy: preserve target identity through projection, reject cross-target citations, and
make verified broad-article fallback available for answer-generation as well as guardrail failures.

## W12-003

Question: “Điều 34 và Điều 43 quy định gì?”  
Decision: FAIL.

Both `get_article` calls returned complete sources: 13 Article 34 chunks and 3 Article 43 chunks.
Only ten contexts reached the public answer: Article 34 clauses 1–9 and Article 43 clause 1. The
answer also changed Article 43(1)’s direct reference to Article 44 into a self-reference to
Article 43, yet verification reported `SUPPORTED`.

Root cause: the generic context/citation bound truncates this sixteen-chunk broad lookup. Separately,
Agent claims disable inline-reference matching, and numeric validation accepts the target article
number from metadata, so the wrong generated self-reference is not rejected.

Generic strategy: increase broad-article capacity without article-specific branches, require material
clause coverage, and reject generated source cross-references absent from the cited source text.

## W12-006

Question: four distinct article lookups with a configured maximum of three.  
Decision: FAIL.

The workflow correctly selected zero tools and `CLARIFICATION_REQUIRED`. The claim guardrail then
treated the intentional no-claim terminal response as an invalid claim contract, replaced the
narrowing question with the internal insufficient-evidence sentinel, and the API mapped that to the
generic sentence.

Generic strategy: do not run claim verification over non-legal clarification text; preserve the
configured limit and a concrete narrowing question.

## W12-008

Question: “Người lao động nghỉ việc phải báo trước bao lâu theo luật?”  
Decision: FAIL.

No tool ran and the public result was generic insufficient context. The router contract currently
requires clarification for every notice question without explicit contract type. It has no
distinction between a general Article 35 overview and a personalized calculation. The same terminal
status overwrite as W12-006 then removed any useful clarification.

Generic strategy: route a general overview to Article 35 retrieval and explain the conditional
matrix; for a personalized result, ask exactly for missing contract/special-circumstance data and do
not call the calculator.

## W12-010

Question: “Quy định về hợp đồng xác định thời hạn?”  
Decision: NEEDS_DISCUSSION.

The retrieval call returned the two directly relevant Article 20 chunks plus Article 35 and Article
36 material. The answer correctly described the definition, 36-month maximum, and post-expiration
handling, then generalized Article 36 employer-termination illness conditions as though they were a
property of fixed-term contracts.

Root cause: the guardrail proves that a claim has support, but does not prove that it is relevant to
the user’s requested scope or that an actor-specific rule remains scoped. The answer prompt allowed
tangential retrieved context to become a broad claim.

Generic strategy: prioritize defining/source contexts, suppress tangential claims, and preserve actor
and condition scope when a termination rule is genuinely requested.

## W12-011

Question: unpaid wages plus a 24-month contract.  
Decision: FAIL.

The observed plan called calculator then retrieval, but the router preserved only the
24-month contract type and omitted `UNPAID_OR_LATE_WAGES`. The MCP input defaulted
`special_case=NONE`; the deterministic calculator then correctly selected the ordinary 30-day rule
for the incomplete parameters. Only Article 35(1) reached the answer.

Canonical provenance confirms Article 35(2)(b) at
`ll_610e9077fc973dabc980978eb3f3da54` and Article 97(4) at
`ll_637097a07e629f3154a38864853c6790`.

Generic strategy: preserve a closed special-circumstance enum through routing and MCP arguments,
give Article 35(2) precedence over duration, and expose the Article 97(4) qualification in the
calculator’s structured outcome and canonical basis.

## W12-012

Question: workplace sexual harassment, notice requirement, and legal basis.  
Decision: FAIL.

The system called only semantic retrieval and returned definition/prohibition/dismissal material
from Articles 3, 8, and 125. It never answered the affected worker’s notice right. The router lacks
a closed `WORKPLACE_SEXUAL_HARASSMENT` mapping, while the current calculator-call schema always
requires contract type even though Article 35(2) special cases do not depend on it.

Generic strategy: allow Article 35(2) special cases without contract type, plan calculator plus
Article 35 clause retrieval when basis is requested, and scope the answer to the worker’s notice
question.

## W12-015

Question: “Điều 34 quy định gì?”  
Decision: FAIL.

`get_article` returned all 13 canonical clauses. The Agent and semantic guardrail accept at most ten
contexts/citations, so clauses 11–13 were necessarily dropped before generation. Verification then
correctly supported the incomplete claim against only the retained subset.

Generic strategy: raise context/citation capacity for broad articles generally and make `get_article`
summaries coverage-aware. The locked retrieval candidate/reranker limits and guardrail thresholds
remain untouched.

## W12-019

Question: “Tôi cần tính thời hạn hợp đồng.”  
Decision: FAIL.

The router correctly withheld the calculator because required contract and date inputs were absent.
As with W12-006, the claim guardrail overwrote the concrete clarification contract and the API
returned generic insufficient context.

Generic strategy: preserve `CLARIFICATION_REQUIRED`, identify each missing field, and execute no
calculator until parameters validate.

## Architecture ownership

- Calculator owns Article 35 outcome/exception structure and legal provenance.
- Retrieval remains unchanged because `get_article` already returns complete canonical articles.
- Agent owns routing, parameter preservation, fair projection, relevance, and finite orchestration.
- Guardrails own cross-article isolation and source cross-reference fidelity.
- FastAPI owns distinct browser-safe public status/warning mapping.
- Evaluation owns remediation evidence, round-2 review, and post-remediation V4 metrics.

No case-ID, question-ID, Article 34-only, or exact-question branch is required.

Machine-readable trace:
`evaluation/results/week12/review_remediation_analysis.json`.
