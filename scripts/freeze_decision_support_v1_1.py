"""Freeze the reviewed v1.1 evaluation set at canonical write-once paths."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_artifacts import (
    V11ArtifactPaths,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_freeze import (
    freeze_v1_1_evaluation,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--project-author-name", required=True)
    parser.add_argument("--freeze-reviewed-v1-1", action="store_true")
    args = parser.parse_args(argv)
    if not args.freeze_reviewed_v1_1:
        parser.error("--freeze-reviewed-v1-1 is required")

    manifest = freeze_v1_1_evaluation(
        V11ArtifactPaths.from_root(args.repo_root),
        project_author_name=args.project_author_name,
    )
    print(json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
