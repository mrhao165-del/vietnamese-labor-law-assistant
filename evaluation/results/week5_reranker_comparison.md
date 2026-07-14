# Week 5 official reranker comparison

| Pipeline | Split | Recall@5 | MRR | Hit@1 | Mean ms | P95 ms |
|---|---|---:|---:|---:|---:|---:|
| B0_DENSE_NO_RERANK | week4_provenance_all | 1.0000 | 0.9281 | 0.8750 | 389.33 | 266.51 |
| B1_H2_NO_RERANK | week4_provenance_all | 1.0000 | 0.9010 | 0.8125 | 234.72 | 259.10 |
| R1_DENSE_RERANK | dev | 1.0000 | 0.9773 | 0.9545 | 6171.73 | 9873.11 |
| R2_H2_RERANK | test_once | 1.0000 | 1.0000 | 1.0000 | 6565.83 | 14116.50 |

B0/B1 are checksum-matched Week 4 provenance; R1/R2 are real reranker model checkpoints.
