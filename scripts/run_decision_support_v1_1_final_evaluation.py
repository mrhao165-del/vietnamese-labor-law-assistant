"""Run the final v1.1 evaluation offline from canonical frozen artifacts."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_artifacts import (
    V11ArtifactPaths,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_release import (
    V11ReleasePaths,
    evaluate_frozen_v1_1_release,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--evaluate-frozen-v1-1", action="store_true")
    args = parser.parse_args(argv)
    if not args.evaluate_frozen_v1_1:
        parser.error("--evaluate-frozen-v1-1 is required")

    manifest = evaluate_frozen_v1_1_release(
        V11ArtifactPaths.from_root(args.repo_root),
        V11ReleasePaths.from_root(args.repo_root),
    )
    payload = (
        manifest.model_dump(mode="json") if hasattr(manifest, "model_dump") else vars(manifest)
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
