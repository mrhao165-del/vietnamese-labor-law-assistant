# Week 10 guardrail evaluation

Status: `PASS`

Cases: 40

## Category coverage

- `calculator_numeric_contradiction`: 1
- `calculator_only_supported`: 1
- `citation_not_in_context`: 3
- `duplicate_citation`: 1
- `empty_context`: 1
- `external_regulation_required`: 1
- `judge_invalid_output`: 1
- `judge_timeout`: 1
- `keyword_overlap_wrong_meaning`: 1
- `legal_reference_match_but_semantic_unsupported`: 1
- `malformed_citation`: 1
- `missing_citation`: 2
- `mixed_claim_status`: 1
- `nonexistent_chunk`: 5
- `numeric_contradiction`: 1
- `out_of_scope_refusal`: 1
- `partial_compound_claim`: 7
- `retrieval_and_calculator_supported`: 1
- `unicode_spacing_variant`: 1
- `valid_full_support`: 6
- `wrong_clause`: 1
- `wrong_point`: 1

## Metrics

```json
{
  "citation_existence_accuracy": 1,
  "retrieved_membership_accuracy": 1,
  "claim_status_accuracy": 1.0,
  "macro_f1": 1.0,
  "per_class": {
    "SUPPORTED": {
      "precision": 1.0,
      "recall": 1.0,
      "f1": 1.0
    },
    "PARTIALLY_SUPPORTED": {
      "precision": 1.0,
      "recall": 1.0,
      "f1": 1.0
    },
    "UNSUPPORTED": {
      "precision": 1.0,
      "recall": 1.0,
      "f1": 1.0
    },
    "INSUFFICIENT_CONTEXT": {
      "precision": 1.0,
      "recall": 1.0,
      "f1": 1.0
    }
  },
  "unsupported_detection_recall": 1.0,
  "insufficient_context_detection_recall": 1.0,
  "out_of_scope_refusal_accuracy": 1.0,
  "false_supported_rate": 0.0,
  "citation_support_rate": 0.25,
  "mean_verification_latency_ms": 0.05575749997888124,
  "p95_verification_latency_ms": 0.06859999984953902,
  "error_timeout_count": 0,
  "required_reason_misses": 0
}
```
