# Remaining manual release actions

Technical validation and independent round-3 review are complete. Perform these actions manually and
in order; automation in this worktree did not commit, push, tag, or publish anything.

1. **Select and add a license.** Review corpus rights, model/dependency licenses, and intended reuse
   with the repository owner or counsel. Add the chosen standard license text as `LICENSE`, update the
   README license statement, and do not imply rights the owner has not granted.
2. **Run the final real CPU application.** Set a valid credential in a private `.env` or external
   `APP_ENV_FILE`, run `docker compose --env-file <path> config --quiet`, then
   `docker compose --env-file <path> up -d --build --wait`. Confirm `/health`, `/ready`, and the React
   root at `http://localhost:8080/`.
3. **Capture genuine screenshots and an optional GIF.** Use the running React application, show real
   citations and clarification behavior, redact personal data and credentials, save approved media
   under `docs/images/`, and update README links.
4. **Record the genuine 3–5 minute demo.** Follow `demo_recording_guide.md` and
   `demo_shot_list.md`; show readiness, retrieval/citations, calculator behavior, a fail-closed case,
   and SQLite persistence. State that Docker evidence is CPU-only.
5. **Upload the video and add the real URL.** Publish to the owner-selected service, verify access in
   a signed-out browser, and replace any placeholder with that exact URL in README/release notes.
6. **Review README rendering on GitHub.** Push only after local review, then inspect headings, tables,
   links, PNG scaling, video URL, license link, and Vietnamese text in GitHub’s renderer.
7. **Stage and review all changes.** Run `git status --short`, `git diff --check`,
   `git diff --stat`, `git diff`, then stage only intended files with `git add <paths>`. Inspect
   `git diff --cached --check`, `git diff --cached --stat`, and `git diff --cached`; confirm no `.env`,
   database, cache, `node_modules`, `dist`, secret, or unrelated file is staged.
8. **Commit and push the release candidate.** After owner approval, create one intentional release
   preparation commit, push the current branch, and open or update the review PR. Record the actual
   release-candidate commit SHA in current evidence without rewriting historical evidence.
9. **Wait for GitHub Actions.** Require every release-commit workflow to finish successfully. If any
   check fails, fix it in a new commit and wait again; do not tag a failing or superseded commit.
10. **Create annotated tag `v1.0.0`.** From the exact reviewed green release commit, run
    `git tag -a v1.0.0 -m "v1.0.0 portfolio release"`, inspect with `git show v1.0.0`, then
    `git push origin v1.0.0`.
11. **Publish the GitHub Release.** Create it from `v1.0.0`, use `docs/releases/v1.0.0.md`, link the
    genuine media, attach only approved artifacts, and verify the public page. Do not claim GPU,
    authentication, legal advice, or unsupported metrics.
12. **Update CV and LinkedIn with verified claims only.** Link the actual repository/release/video and
    use the recorded architecture, 361-test/85.92%-coverage result, 87/87 live targeted result, and
    CPU latency classification with their scope. Do not present targeted or contract metrics as a
    general legal-accuracy guarantee.
