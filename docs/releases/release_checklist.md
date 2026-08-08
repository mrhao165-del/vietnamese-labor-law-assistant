# v1.0.0 release checklist

| Item | Status | Evidence / next action |
| --- | --- | --- |
| Frozen corpus/dataset/split/config verified | COMPLETE | `week12/preflight.json`, release manifest |
| V1–V4 JSON/CSV benchmark with provenance | COMPLETE | `evaluation/results/week12/` |
| 24-case packet generated with blank reviewer fields | COMPLETE | `evaluation/review/` |
| Portfolio README and release documentation | COMPLETE | README, this release folder |
| Reproducible Mermaid/PNG assets | COMPLETE | `docs/diagrams`, `docs/images` |
| Backend/frontend/repository CI definition | COMPLETE | `.github/workflows/ci.yml` |
| Final local quality and release verification | COMPLETE | 361 tests, 85.92% coverage; final live CPU aggregate 87/87 |
| Release-prep final local gate (2026-08-08) | COMPLETE | 378 Python tests, 86.05% coverage; lint/type/MCP demos, frozen evidence, Week 9/10, assets, release validator, frontend, audit, and Compose config passed |
| Week 12 remediation merged into `main` | COMPLETE | Project owner confirmed merge and green GitHub Actions |
| Browser-level frontend smoke suite | DEFERRED_V1_1 | Adding a test framework changes the checksum-locked package lockfile in the preserved Week 12 manifest; existing typecheck/lint/build remain required |
| Round-1 independent review | COMPLETE_WITH_FINDINGS | 15 PASS, 8 FAIL, 1 NEEDS_DISCUSSION; immutable archive preserved |
| Generic review remediation | COMPLETE | Affected live matrix 23/23; original PASS regression 15/15 |
| Round-2 review of nine affected rows | COMPLETE_WITH_FINDINGS | 6 PASS, 2 FAIL, 1 NEEDS_DISCUSSION; immutable archive preserved |
| Generic round-3 remediation | COMPLETE | Targeted offline and 27-attempt live matrix passed; three-row packet generated |
| Round-3 review of three affected rows | COMPLETE | 3 PASS, 0 FAIL, 0 NEEDS_DISCUSSION; immutable archive preserved |
| Required real UI screenshots | COMPLETE | `ui-chat-citation.png`, `ui-calculator-trace.png`, and `ui-guardrail-or-clarification.png` verified in `docs/images/`; optional GIF is not required |
| Real 3–5 minute demo video | INTENTIONALLY_OMITTED | Project owner excluded video from v1.0.0; no video or URL is claimed |
| License choice and `LICENSE` file | COMPLETE | MIT License selected by the project owner; canonical `LICENSE` added |
| Review README rendering on GitHub | MANUAL_ACTION_REQUIRED | Verify links, tables, and PNG scale after push |
| Annotated `v1.0.0` tag and push | MANUAL_ACTION_REQUIRED | Commands in `manual_actions.md` |
| GitHub Release publication | MANUAL_ACTION_REQUIRED | Create only after all release gates pass |
| CV update | MANUAL_ACTION_REQUIRED | Add evidence-backed project summary |
| LinkedIn update | MANUAL_ACTION_REQUIRED | Publish only accurate claims |
| GPU Docker support | NOT_APPLICABLE | No evidence; not claimed |
| Streamlit frontend | NOT_APPLICABLE | React officially replaced it |
| Network MCP services | NOT_APPLICABLE | Production MCP transport is stdio |

No automated item authorizes commit, push, tag, or release publication.

Current status: `V1_0_RELEASE_PREP_MANUAL_ACTION_REQUIRED`. Technical, human-review, merge, GitHub
Actions, the required UI screenshot gates, the MIT License gate, and the final local release gate are
complete. Git review/owner approval, final GitHub rendering review, tag, and GitHub Release publication
still prevent publication. The demo video is intentionally omitted and is not a release requirement.
