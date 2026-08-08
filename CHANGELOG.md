# Changelog

All notable changes to this portfolio are documented here.

## [Unreleased]

- The Week 12 remediation PR was merged into `main`; the project owner confirms GitHub Actions are
  green.
- Release preparation removes non-functional attachment and dead-navigation controls. A frontend
  browser-test framework is deferred to v1.1 because adding its dependencies would change the
  checksum-locked package lockfile in the preserved Week 12 release manifest.
- The repository is now MIT licensed. The final local release-prep quality gate passed, and the
  portfolio-asset contract now permits only the documented real UI screenshot filenames alongside the
  four deterministic generated diagrams.
- The v1.0.0 demo video is intentionally omitted by the project owner. The three required genuine UI
  screenshots are captured and verified, and the repository is now MIT licensed; GitHub README
  rendering review, annotated tag, GitHub Release, and profile updates remain manual release actions.

## [1.0.0] - Unreleased portfolio release

### Added

- Week 12 pre-flight and checksum-backed release provenance manifest.
- V1–V4 benchmark portfolio with JSON/CSV outputs, metric definitions, provenance, schema validation,
  duplicate detection, missing-metric handling, and deterministic ordering.
- A 24-case stratified manual-review packet captured from live HTTP Agent responses, with reviewer
  fields intentionally blank.
- Reproducible architecture, RAG, Agent, and evaluation PNG assets plus Mermaid sources.
- GitHub Actions checks for backend, frontend, repository safety, benchmark, documentation, and asset
  reproducibility.
- Release notes, checklist, manual actions, reproducibility instructions, and demo shot list.

### Changed

- README rewritten to describe the current React/Nginx/FastAPI/SQLite/LangGraph/MCP-stdio
  architecture and evidence-backed limitations.
- Pillow added to the development dependency group only for deterministic portfolio image generation.
- Article 35 special circumstances now take precedence over ordinary notice periods, with structured
  outcomes and the Article 97(4) wage-delay qualification.
- Broad and multi-article lookups retain complete, target-scoped canonical evidence within a bounded
  20-context internal projection; provider-facing structured output remains separately bounded.
- Clarification and public fail-closed responses preserve distinct safe status contracts.
- General resignation-notice questions return the complete Article 35(1)-(2) overview; ambiguous
  contract-duration and over-limit article requests return explicit zero-tool clarification outcomes.

### Verified

- 361 Python tests at 85.92% coverage during final validation.
- Ruff format/lint, Pyright, frontend typecheck/lint/build, production npm audit, CPU-only Compose
  clean build/start, live Week 11 and multi-article smoke 27/27, round-1 PASS regression 15/15,
  round-2 PASS regression 18/18, round-3 matrix 27/27, and SQLite restart persistence.
- Round-1 evidence preserved (15 PASS, 8 FAIL, 1 NEEDS_DISCUSSION); affected live remediation matrix
  passed 23/23 and original PASS-row regression passed 15/15.
- Round-2 evidence preserved (6 PASS, 2 FAIL, 1 NEEDS_DISCUSSION); round-3 evidence preserved with
  3 PASS, 0 FAIL, and 0 NEEDS_DISCUSSION.

No canonical corpus, frozen evaluation labels/split, selected retrieval configuration, guardrail
threshold, legal rule, or historical result artefact was changed.
