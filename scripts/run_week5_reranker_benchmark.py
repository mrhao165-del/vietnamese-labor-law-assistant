"""Checkpointable command-line interface for the Week 5 reranker benchmark."""

from __future__ import annotations

import argparse
import json

from vietnamese_labor_law_assistant.evaluation.week5_reranker_runner import (
    execute_week5_command,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the thin CLI surface; benchmark work lives in evaluation."""
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)

    subcommands.add_parser("plan", help="write the staged DEV benchmark plan")
    subcommands.add_parser("status", help="show checkpoint progress")

    run_dev = subcommands.add_parser("run-dev", help="run one DEV checkpoint slice")
    run_dev.add_argument("--resume", action="store_true", help="continue an existing checkpoint")
    run_dev.add_argument("--time-budget-seconds", type=int, default=300)
    run_dev.add_argument("--max-questions-per-run", type=int)
    run_dev.add_argument("--config-id", help="planned configuration to run")

    subcommands.add_parser("select-dev", help="advance staged DEV selection")

    run_test = subcommands.add_parser("run-test", help="run the selected TEST checkpoint")
    run_test.add_argument("--resume", action="store_true", help="continue an existing checkpoint")
    run_test.add_argument("--time-budget-seconds", type=int, default=300)
    run_test.add_argument("--max-questions-per-run", type=int)

    subcommands.add_parser("validate", help="validate checkpoint and selection integrity")
    subcommands.add_parser("finalize", help="write final Week 5 artifacts after completion")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    arguments = vars(args).copy()
    command = arguments.pop("command")
    try:
        result = execute_week5_command(command, **arguments)
    except (RuntimeError, ValueError) as exc:
        print(json.dumps({"status": "ERROR", "message": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
