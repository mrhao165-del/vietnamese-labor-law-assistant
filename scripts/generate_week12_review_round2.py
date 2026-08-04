"""Build the nine-row Week 12 round-2 packet from preserved and live evidence."""

from __future__ import annotations

import csv
import html
import json
from pathlib import Path
from typing import Any

ROUND2_IDS = {
    "W12-001": "W12-R2-001",
    "W12-003": "W12-R2-003",
    "W12-006": "W12-R2-006",
    "W12-008": "W12-R2-008",
    "W12-010": "W12-R2-010",
    "W12-011": "W12-R2-011",
    "W12-012": "W12-R2-012",
    "W12-015": "W12-R2-015",
    "W12-019": "W12-R2-019",
}
REVIEWER_FIELDS = (
    "reviewer_decision",
    "reviewer_name",
    "reviewer_role",
    "reviewed_at",
    "evidence_note",
)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _write_html(rows: list[dict[str, str]], path: Path) -> None:
    fields = list(rows[0])
    header = "".join(f"<th>{html.escape(field)}</th>" for field in fields)
    body = "\n".join(
        "<tr>"
        + "".join(f"<td><div>{html.escape(str(row.get(field, '')))}</div></td>" for field in fields)
        + "</tr>"
        for row in rows
    )
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Week 12 round-2 remediation review</title><style>
body{{font:14px system-ui;margin:24px;color:#172033}} .notice{{max-width:1100px;padding:14px;
background:#fff7d6;border:1px solid #caa53a}} table{{border-collapse:collapse;margin-top:18px}}
th,td{{border:1px solid #ccd3df;padding:8px;vertical-align:top}}
th{{position:sticky;top:0;background:#172033;color:white}}
td div{{max-width:460px;max-height:260px;overflow:auto;white-space:pre-wrap}}
tr:nth-child(even){{background:#f5f7fa}}</style></head><body>
<h1>Week 12 round-2 remediation review</h1>
<p class="notice"><strong>Independent comparison required.</strong> Compare each preserved
round-1 answer and finding with the corrected live behavior. Enter a new decision based only on
the corrected behavior. All round-2 reviewer fields are intentionally blank.</p>
<p>Rows: {len(rows)}. Instructions:
<code>docs/releases/week12_round2_review_instructions.md</code>.</p>
<table><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table></body></html>
"""
    path.write_text(document, encoding="utf-8", newline="\n")


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    original_rows = {
        row["review_id"]: row
        for row in _read_csv(root / "evaluation/review/week12_manual_review_packet.csv")
    }
    analysis = json.loads(
        (root / "evaluation/results/week12/review_remediation_analysis.json").read_text(
            encoding="utf-8"
        )
    )
    analysis_by_id = {row["review_id"]: row for row in analysis["cases"]}
    live = json.loads(
        (root / "evaluation/results/week12/review_remediation_live.json").read_text(
            encoding="utf-8"
        )
    )
    if live.get("status") != "PASS":
        raise SystemExit("live remediation matrix is not PASS")
    live_by_id: dict[str, dict[str, Any]] = {}
    for attempt in live["attempts"]:
        if attempt["result"] == "PASS":
            live_by_id.setdefault(attempt["original_review_id"], attempt)
    rows: list[dict[str, str]] = []
    for original_id, round2_id in ROUND2_IDS.items():
        original = original_rows[original_id]
        finding = analysis_by_id[original_id]
        corrected = live_by_id[original_id]
        row = {
            "round2_review_id": round2_id,
            "original_review_id": original_id,
            "original_human_decision": original["reviewer_decision"],
            "original_human_evidence_note": original["evidence_note"],
            "question": original["question"],
            "original_answer": original["system_answer"],
            "original_route": original["expected_route"],
            "original_tool_calls": original["observed_tool_calls"],
            "root_cause": finding["root_cause"],
            "fix_summary": finding["generic_remediation_strategy"],
            "corrected_answer": str(corrected["answer"]),
            "corrected_route": str(corrected["route"]),
            "corrected_tool_calls": _json(corrected["observed_tools"]),
            "corrected_citations": _json(corrected["citations"]),
            "corrected_verification": _json(corrected["verification"]),
            "corrected_warnings": _json(corrected["warnings"]),
            "corrected_latency": str(corrected["latency_ms"]),
            "live_provenance": (
                "LIVE_DOCKER_COMPOSE_CPU_PUBLIC_HTTP;"
                f"request_id={corrected['request_id']};"
                f"source_commit={corrected['source_commit']}"
            ),
            **{field: "" for field in REVIEWER_FIELDS},
        }
        rows.append(row)
    if len(rows) != 9 or any(row[field] for row in rows for field in REVIEWER_FIELDS):
        raise SystemExit("round-2 packet invariant failed")
    review_dir = root / "evaluation/review"
    csv_path = review_dir / "week12_manual_review_round2.csv"
    html_path = review_dir / "week12_manual_review_round2.html"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    _write_html(rows, html_path)
    print("PASS: wrote 9-row round-2 packet with blank reviewer fields")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
