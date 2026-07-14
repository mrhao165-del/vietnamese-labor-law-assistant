"""Render Week 4 CSV and Markdown reports from an already completed JSON benchmark."""

from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "evaluation/results"


def main() -> int:
    report = json.loads((RESULTS / "week4_retrieval_comparison.json").read_text(encoding="utf-8"))
    rows = report["results"]
    fields = [
        "configuration",
        "hit_rate_at_1",
        "hit_rate_at_5",
        "recall_at_5",
        "mrr",
        "mean_latency_ms",
        "p95_latency_ms",
        "error_rate",
    ]
    with (RESULTS / "week4_retrieval_comparison.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "configuration": row["configuration"],
                    **{key: row["metrics"].get(key) for key in fields[1:]},
                }
            )
    lines = [
        "# Week 4 official retrieval comparison",
        "",
        "| Pipeline | Hit@1 | Recall@5 | MRR | Mean ms | P95 ms |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        metric = row["metrics"]
        lines.append(
            f"| {row['configuration']} | {metric['hit_rate_at_1']:.4f} | "
            f"{metric['recall_at_5']:.4f} | {metric['mrr']:.4f} | "
            f"{metric['mean_latency_ms']:.2f} | {metric['p95_latency_ms']:.2f} |"
        )
    lines.extend(["", f"Best dev configuration: `{report['best_dev_configuration']}`."])
    (RESULTS / "week4_retrieval_comparison.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
