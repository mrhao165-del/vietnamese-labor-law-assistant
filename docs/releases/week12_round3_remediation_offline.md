# Week 12 round-3 targeted offline verification

Status: `PASS`

The deterministic Agent, calculator, guardrail, public-mapper, and chat-API suite collected and
passed **154/154 tests** in 9.92 seconds. The only warning was the existing Starlette TestClient
httpx deprecation warning. Test duration is not live LLM latency and is not reported as such.

## Affected cases

| Parent case | Offline result | Verified behavior |
|---|---|---|
| `W12-R2-006` | PASS | `RETRIEVAL_ONLY` route remains traceable; outcome and verification are `CLARIFICATION_REQUIRED`; maximum three articles is explained; zero tools |
| `W12-R2-008` | PASS | complete Article 35 overview includes 45/30/03 working days, Government-regulation branch, no-notice cases, both clause citations, no calculator |
| `W12-R2-019` | PASS | ambiguous duration intent separates calendar duration, notice, and classification; asks correct inputs; zero tools; no false 12–36-month fixed-term definition |

## Generic alternative questions

The tests cover these independently of review IDs:

- General notice overview:
  - “Người lao động nghỉ việc phải báo trước bao lâu theo luật?”
  - “Các thời hạn báo trước khi nghỉ việc là gì?”
  - “Muốn nghỉ việc thì báo trước mấy ngày?”
- Ambiguous contract duration:
  - “Tính thời hạn hợp đồng giúp tôi.”
  - “Hợp đồng của tôi kéo dài bao lâu?”
  - “Tính số ngày của hợp đồng.”
- Personalized notice with missing facts:
  - “Tôi muốn biết mình phải báo trước bao lâu”
  - “Tính thời gian cần báo trước.”

The public mapping tests distinguish `CLARIFICATION_REQUIRED`, `INSUFFICIENT_CONTEXT`,
`ARTICLE_NOT_FOUND`, `OUT_OF_SCOPE`, `UNSUPPORTED`, and `OUTPUT_INVALID`. A production-source scan
found no round-2/round-3 review ID, original affected review ID, or fixture-specific branch.

Machine-readable evidence:
`evaluation/results/week12/round3_remediation_offline.json`.
