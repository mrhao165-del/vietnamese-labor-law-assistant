# Week 5 reranker error analysis

All examples are completed checkpoint/provenance records; no synthetic cases.

| Type | Actual case |
|---|---|
| rank tăng | `w3-001` (direct): expected rank 2 → 1. |
| rank giảm | `w3-032` (ambiguous): expected rank 1 → 2. |
| không đổi | `w3-002` (direct): expected rank giữ ở 1. |
| Dense và H2 khác nhau | `w3-001` (direct): top-5 Dense và H2 khác nhau. |
| keyword sai ngữ cảnh | `w3-023` (legal_keyword): kiểm tra keyword; expected 2 → 1. |
| paraphrase | `w3-011` (natural_paraphrase): paraphrase giữ/đổi expected rank 1 → 1. |
| query Điều/Khoản | `w3-001` (direct): có expected clause; expected rank 2 → 1. |
| rank tăng | `w3-001` (direct): expected rank 2 → 1. |
| candidate pool thiếu expected chunk | `w3-037`: L1 BM25 candidate pool thiếu expected chunk; selected H2 has 0/60 such cases. |
| truncation | Selected 512 truncates 5/300 measured pairs. |

Case count: 10.
