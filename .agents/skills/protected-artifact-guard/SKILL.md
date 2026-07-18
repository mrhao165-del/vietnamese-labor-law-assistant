---
name: protected-artifact-guard
description: Inspect a Git diff for prohibited changes to protected data, historical verification evidence, the locked retrieval configuration, and test-quality safeguards. Use before implementation handoff, evidence updates, staging, or committing in this repository. Do not use to approve intentional protected changes without the user's explicit authorization or to modify files.
---

# Protected Artifact Guard

Run `python .agents/skills/protected-artifact-guard/scripts/scan_protected_diff.py` from the repository
root. It inspects staged and unstaged diffs without changing the worktree.

- Treat protected-path, locked-config, and test-quality findings as blockers unless the user expressly
  authorized the precise change.
- Inspect renames and deletions as well as modifications. Untracked paths are scope information because
  Git has no diff for them.

Protect `data/raw/`, `data/processed/`, `data/evaluation/`, completed-week `evaluation/results/`, and
`R2_H2_C10_O5_L512_B1`. The script flags changes to `coverage.fail_under`, coverage exclusions, and new
skip/skipif markers. It detects risk, not justification; do not edit files while performing this guard.
