# Week 4 official retrieval comparison

| Pipeline | Hit@1 | Recall@5 | MRR | Mean ms | P95 ms |
|---|---:|---:|---:|---:|---:|
| L0_DENSE | 0.8750 | 1.0000 | 0.9281 | 389.33 | 266.51 |
| L1_BM25_WHITESPACE | 0.4062 | 0.9688 | 0.6432 | 0.28 | 0.34 |
| H1_DENSE_WHITESPACE_RRF | 0.6875 | 0.9688 | 0.8274 | 233.68 | 261.17 |
| L2_BM25_UNDERTHESEA | 0.5938 | 1.0000 | 0.7734 | 7.15 | 1.54 |
| H2_DENSE_UNDERTHESEA_RRF | 0.8125 | 1.0000 | 0.9010 | 234.72 | 259.10 |

Best dev configuration: `L0_DENSE`.
