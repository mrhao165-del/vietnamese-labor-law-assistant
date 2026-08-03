# Week 12 remediation baseline

Status: **PASS with one expected reviewed-packet contract mismatch**

The baseline was captured on branch `fix/week12-review-remediation` at
`3f659b6ad12235f8c804d14856c85cc4645cba34`. Existing modified and untracked Week 12 preparation
work was preserved. No Git history operation was performed.

## Frozen inputs

| Input | Observed result |
| --- | --- |
| Selected configuration | `R2_H2_C10_O5_L512_B1` |
| Corpus SHA-256 | `62d4f98ba376260231663c779824651f60b82c0f968244ace95e478d20dbbcd3` |
| Dataset SHA-256 | `19440059cf4c31a487b30db10b6d5eb8bb781290d642936b1ba25e8eb0697110` |
| Split-manifest SHA-256 | `08ceada3bb4a6bbd7c6a00ae0e007e8027d59acc5d0e63a563c2169f1cf5d5bd` |
| DEV / TEST | 42 / 18 |
| Split status | `FROZEN` |
| Guardrail thresholds | 0.35 / 0.75, unchanged |

All three checksums match the Week 12 release manifest.

## Environment

Windows 10.0.19045, Python 3.11.15, uv 0.10.11, Node 24.15.0, npm 11.12.1,
Docker 29.6.1, and Compose v5.3.0 were observed. Docker evidence remains CPU-only. No external
`APP_ENV_FILE` was configured; an existing ignored private `.env` was present and was neither read
into evidence nor modified.

## Baseline gates

| Check | Result |
| --- | --- |
| `git diff --check` | PASS |
| uv lock | PASS |
| Ruff format / lint | PASS / PASS |
| Pyright | PASS, 0 errors and 0 warnings |
| Full Python suite | PASS, 323 tests |
| Coverage | PASS, 86.21% against 82% |
| Production MCP stdio demos | PASS, 2 demos and 5 canonical checks |
| Week 9 verifier | PASS, 40-case offline contract suite |
| Week 10 verifier | PASS, 40 cases and 37/37 provenance |
| Week 12 benchmark and asset reproducibility | PASS |
| Frontend install / typecheck / lint / build | PASS |
| Production npm audit | PASS, 0 vulnerabilities |
| Compose config | PASS |
| Protected artefact scanner | PASS, CLEAR |
| Documentation links and tracked secret/runtime scan | PASS |

`npm ci` reported findings among development dependencies, while the explicitly required
production-only audit returned zero vulnerabilities.

The existing `scripts/validate_week12_release.py` command failed only because
`validate_review_rows` requires all reviewer fields to remain blank. That is the pre-review packet
contract and is incompatible with the newly completed, archived round-1 review. The reviewed CSV
was already validated independently and matches its immutable archive byte-for-byte. This is a
directly related remediation item, not an unrelated baseline regression.

No unrelated pre-existing baseline failure was found, so remediation may continue.

Machine-readable evidence: `evaluation/results/week12/remediation_baseline.json`.
