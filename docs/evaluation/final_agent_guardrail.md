# Final Agent and guardrail evaluation (V4)

The post-remediation V4 evaluation passed all 87 live CPU Docker attempts. The targeted set combines the Week 11 and multi-article smoke matrix, all fifteen round-1 PASS cases, the six round-2 PASS cases over eighteen attempts, and the three round-3 behaviors plus alternative Vietnamese phrasings over twenty-seven attempts. V1-V3 retrieval metrics remain unchanged.

| Metric | Result |
|---|---:|
| Sample count | 87 |
| Route/tool-selection accuracy | 87/87 (100%) |
| Parameter accuracy | 22/22 (100%) on explicitly asserted parameters |
| Tool-call success | 90/90 (100%) expected observed calls |
| Clarification accuracy | 19/19 (100%) |
| Out-of-scope accuracy | 2/2 (100%) |
| Insufficient-context accuracy | 5/5 (100%) |
| Citation existence | 61/61 (100%) where citations were expected |
| Citation validity | 61/61 (100%) |
| Citation support | 59/61 fully supported (96.72%); 2/61 correctly classified partially supported |
| Timeout rate | 0/87 (0%) |
| Error rate | 0/87 (0%) |
| Mean latency | 11.632 s |
| P95 latency | 25.848 s |

Provenance is **LIVE_DOCKER_CPU_LLM**. Latency is real end-to-end Docker/LLM CPU latency, not offline, mock, or contract latency. Complex requests may take several or tens of seconds.

Machine-readable reports: [`final_agent_guardrail.json`](../../evaluation/results/week12/final_agent_guardrail.json), [`final_agent_guardrail.csv`](../../evaluation/results/week12/final_agent_guardrail.csv), and [`final_live_validation.json`](../../evaluation/results/week12/final_live_validation.json).
