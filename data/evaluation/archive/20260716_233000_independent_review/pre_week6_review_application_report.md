# Pre-Week-6 review application report

- Status: **MANUAL_ACTION_REQUIRED**
- Week 6 eligible: **False**
- Technical readiness: **READY**
- Evidence readiness: **MANUAL_ACTION_REQUIRED**

## Review application

- Week 1: 21 rows; 18 PASS; 3 CORRECTED; 0 PENDING.
- Evaluation: 60 rows; 44 PASS; 16 CORRECTED; 0 PENDING.
- Evaluation reviewer classification: project-author AI-assisted approval; not independent legal-professional review.
- Corrected question IDs: w3-019, w3-031, w3-032, w3-033, w3-035, w3-036, w3-037, w3-038, w3-041, w3-042, w3-044, w3-045, w3-046, w3-047, w3-048, w3-049.

## Dataset and index provenance

- Previous dataset checksum: `56975dfcfc05b8f952e96637c27ceb8d5e48c5fcb3e7ccebb8f67c164bfe14c4`.
- Current dataset checksum: `19440059cf4c31a487b30db10b6d5eb8bb781290d642936b1ba25e8eb0697110`.
- Current chunk checksum: `62d4f98ba376260231663c779824651f60b82c0f968244ace95e478d20dbbcd3`.
- Corrected chunk IDs unresolved: 0.
- DEV/TEST split and question IDs: unchanged.
- Week 3–5 metrics: not modified; benchmark artefacts are historical/provisional against the prior dataset checksum.

## Quality gates

- ruff_format: PASS
- ruff_lint: PASS
- pyright: PASS
- pytest: PASS
- coverage: PASS
- evaluation_validation: PASS
- integration_tests: PASS
- provenance_tests: PASS
- api_regression: PASS
- retrieval_regression: PASS
- Independent-human evidence validation: EXPECTED_FAIL (60/60 evaluation rows are project-author AI-assisted approvals).

## Blocker

An independent qualified human/legal reviewer must confirm all 60 evaluation-label rows in `data/evaluation/labor_law_eval_v1_human_review_packet.csv`. The policy was not relaxed.
