# Reproducibility

The Week 12 portfolio is an aggregation of checksum-aligned evidence, not a retrospective rewrite of
historical results. Start from the source commit and compare every checksum in
[`release_manifest.json`](../../evaluation/results/week12/release_manifest.json).

## Locked inputs

- Canonical clauses: `data/processed/labor_law_clauses.jsonl`.
- Frozen evaluation dataset: `data/evaluation/labor_law_eval_v1.jsonl` (42 DEV, 18 TEST).
- Dataset manifest: `data/evaluation/labor_law_eval_v1_manifest.json`.
- Selected retrieval configuration: `R2_H2_C10_O5_L512_B1`.
- Python and frontend lockfiles: `uv.lock` and `frontend/package-lock.json`.

TEST was not used for tuning. The V1–V3 portfolio comparison uses DEV throughout. The locked V3 TEST
run is preserved only in its original Week 5/6 source evidence.

## Reproduce automated artefacts

```powershell
uv sync --all-groups --frozen
uv run python scripts/generate_week12_portfolio.py
uv run python scripts/generate_portfolio_assets.py
uv run python scripts/generate_week12_portfolio.py --check
uv run python scripts/generate_portfolio_assets.py --check
```

The generation scripts read source JSON rather than embedding benchmark numbers. The release manifest
contains a generation timestamp by design; benchmark JSON/CSV and images are deterministic from their
inputs.

Live Agent behavior additionally requires the provider/model identifiers recorded in the manifest, a
valid private credential, network access, and the CPU-only Compose path. Credential values are never
part of provenance.
