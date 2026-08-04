# Final release-candidate manifest

`evaluation/results/week12/final_release_manifest.json` identifies the current post-round-3 release
candidate. It is versioned separately from two historical manifests:

- `release_manifest.json` records the original Week 12 portfolio-preparation phase;
- `remediation_manifest.json` records the pre-round-3 remediation phase and its then-current
  Compose checksum;
- `final_release_manifest.json` records the current release-candidate inputs, current Compose
  checksum, completed round-2/round-3 evidence checksums, branch, and source HEAD.

The historical files are not rewritten. Their own checksums are embedded in the final manifest so
the final validator can prove they remain unchanged. `scripts/validate_week12_release.py` accepts an
explicit `--manifest-phase` and, in `auto` mode, prefers the final manifest when present. Selecting
the remediation phase explicitly still applies its historical Compose checksum and is expected to
reject a later candidate; this prevents silent use of evidence from the wrong phase.

The final manifest identifies an uncommitted release candidate. It does not claim that manual
publication actions, GitHub Actions, a tag, or a GitHub Release have occurred.

The final validator selected this manifest in both explicit `final` and automatic modes. Round-3
review, frozen checksums, current Compose, V4 schema, documentation links, tracked-runtime policy,
and secret policy passed. The resulting release status is
`WEEK12_TECHNICAL_AND_REVIEW_COMPLETE_MANUAL_RELEASE_ACTIONS_REQUIRED`.
