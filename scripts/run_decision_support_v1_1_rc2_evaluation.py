"""Run the write-once v1.1 RC2 release evaluation entirely offline."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_rc2 import (
    RC2ArtifactPaths,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_rc2_release import (
    evaluate_registered_rc2_release,
)

OFFLINE_CONFIRMATION = "V1_1_RC2_OFFLINE_EVALUATION"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--confirm-write-once")
    args = parser.parse_args(argv)
    if args.confirm_write_once != OFFLINE_CONFIRMATION:
        parser.error(f"--confirm-write-once must equal {OFFLINE_CONFIRMATION}")

    terminal = evaluate_registered_rc2_release(RC2ArtifactPaths.from_root(args.repo_root))
    print(json.dumps(terminal.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0 if terminal.final_result == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
