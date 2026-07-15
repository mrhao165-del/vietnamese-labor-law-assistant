"""CLI adapter for the frozen post-independent-review Week 6 verification."""

from __future__ import annotations

import argparse
import json

from vietnamese_labor_law_assistant.evaluation.week6_locked_verification import run


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=("dev", "test"), required=True)
    parser.add_argument("--max-questions", type=int)
    args = parser.parse_args()
    # Keep the PowerShell adapter ASCII-safe; the canonical result file remains UTF-8.
    print(json.dumps(run(args.split, args.max_questions), ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
