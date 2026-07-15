"""Create the Week 1 and evaluation human-review packets for pre-Week-6 closure."""

from __future__ import annotations

import json
from pathlib import Path

from vietnamese_labor_law_assistant.evaluation.review_packets import prepare_human_review_packets

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    print(json.dumps(prepare_human_review_packets(ROOT), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
