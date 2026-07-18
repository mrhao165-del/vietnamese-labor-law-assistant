---
name: verification-evidence-sync
description: Synchronize a requested verification-evidence artefact only from real, current quality-gate and protocol outputs in this repository. Use after the user explicitly asks to record completed verification. Do not use to create evidence prospectively, infer PASS, test counts, or coverage, or alter historical completed-week evidence without authorization.
---

# Verification Evidence Sync

Evidence records observed execution, not plans or assumptions.

1. Confirm explicit user authorization and a permitted target; apply `$protected-artifact-guard` for a
   completed-week target.
2. Run or read complete, current output from `$project-quality-gate` and required protocol, demo, or
   Inspector commands.
3. Map only observable status, tools, versions, test/coverage values, timestamps, and scope exclusions to
   the existing evidence schema.
4. Preserve schema and history. If output is incomplete, write no synthetic result; report what must run.
5. Re-read a permitted written artefact and compare it with captured output.

Never guess coverage, test counts, Inspector status, legal validation, or regression results.
