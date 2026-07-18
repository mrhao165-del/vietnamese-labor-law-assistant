---
name: git-week-checkpoint
description: Prepare a safe weekly Git checkpoint by inspecting the diff and quality status before any stage, commit, tag, or push operation. Use when the user explicitly asks to checkpoint, commit, tag, or publish a completed week. Do not use to perform write actions without explicit user authorization or to bypass protected-artifact and quality failures.
---

# Git Week Checkpoint

Separate inspection from Git writes.

1. Read `git status --short`, staged and unstaged diffs, and target branch context.
2. Invoke `$protected-artifact-guard`; stop on unauthorized protected changes, coverage regression, or new
   skipped tests.
3. Invoke `$project-quality-gate` when code, tests, dependencies, or scripts changed. Record actual result
   and each check not run.
4. Confirm scope with user: files, commit message, tag, and push/PR intent. Never include `.env`, secrets,
   unrelated work, or protected artefacts by assumption.

Only after explicit authorization, stage agreed files, re-review the staged diff, commit, optionally tag,
and push only if requested. Do not use destructive Git commands or claim a remote operation without output.
