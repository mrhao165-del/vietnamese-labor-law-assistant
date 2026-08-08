# Remaining manual release actions

Technical validation and independent round-3 review are complete. Perform these actions manually and
in order; automation in this worktree did not commit, push, tag, or publish anything.

The required UI evidence is complete: `docs/images/ui-chat-citation.png`,
`docs/images/ui-calculator-trace.png`, and `docs/images/ui-guardrail-or-clarification.png` were
captured from the running application and manually verified. No GIF or demo video is required.

1. **MIT License is complete.** The project owner selected MIT; the canonical `LICENSE` and README
   statement are present. The license does not change third-party dependency, model, or source-corpus
   rights.
2. **Real CPU application evidence is complete.** The required screenshots were captured from the
   running application, and the final release-prep gate passed Compose configuration. Keep credentials
   private; no secret or local runtime state is stored in this repository.
3. **Required screenshot evidence is complete.** The three verified PNGs are linked from README and
   recorded in `ui_screenshot_checklist.md`. Do not replace them with mock or generated UI images.
4. **Do not record or publish a demo video for v1.0.0.** The project owner intentionally omitted the
   video from this release scope. Do not add a placeholder URL or imply that a video exists.
5. **Review README rendering on GitHub.** Push only after local review, then inspect headings, tables,
   links, PNG scaling, license link, and Vietnamese text in GitHub’s renderer.
6. **Stage and review all changes.** Run `git status --short`, `git diff --check`,
   `git diff --stat`, `git diff`, then stage only intended files with `git add <paths>`. Inspect
   `git diff --cached --check`, `git diff --cached --stat`, and `git diff --cached`; confirm no `.env`,
   database, cache, `node_modules`, `dist`, secret, or unrelated file is staged.
7. **Commit and push the release candidate.** After owner approval, create one intentional release
   preparation commit, push the current branch, and open or update the review PR. Record the actual
   release-candidate commit SHA in current evidence without rewriting historical evidence.
8. **Wait for GitHub Actions.** Require every release-commit workflow to finish successfully. If any
   check fails, fix it in a new commit and wait again; do not tag a failing or superseded commit.
9. **Create annotated tag `v1.0.0`.** From the exact reviewed green release commit, run
   `git tag -a v1.0.0 -m "v1.0.0 portfolio release"`, inspect with `git show v1.0.0`, then
   `git push origin v1.0.0`.
10. **Publish the GitHub Release.** Create it from `v1.0.0`, use
    `docs/releases/v1.0.0_release_notes.md`, attach only approved artifacts, and verify the public
   page. Do not claim GPU,
   authentication, legal advice, or unsupported metrics.
11. **Update CV and LinkedIn with verified claims only.** Link the actual repository/release and
   use the recorded architecture, 361-test/85.92%-coverage result, 87/87 live targeted result, and
   CPU latency classification with their scope. Do not present targeted or contract metrics as a
   general legal-accuracy guarantee.
