"""Capture 24 deterministic live Agent responses for independent manual review."""

from __future__ import annotations

import argparse
import csv
import html
import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from vietnamese_labor_law_assistant.evaluation.week12_portfolio import (
    review_row,
    validate_review_rows,
)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def selected_cases(root: Path) -> list[dict[str, Any]]:
    week11 = read_json(root / "tests/end_to_end/fixtures/week11_live_smoke_cases.json")
    multi = read_json(root / "tests/end_to_end/fixtures/multi_article_live_cases.json")
    categories = {
        "week11-retrieval-positive": "direct_legal_retrieval",
        "week11-calculator-positive": "calculator_only",
        "week11-combined-positive": "retrieval_and_calculator",
        "week11-combined-fail-closed": "citation_guardrail_edge_case",
        "week11-out-of-scope": "out_of_scope",
        "week11-valid-input-insufficient-context": "missing_article",
        "week11-clarification-required": "clarification_required",
        "multi-article-32-54": "multi_article",
        "multi-article-34-43": "multi_article",
        "multi-article-20-35-169": "multi_article",
        "multi-article-duplicate-35": "multi_article_deduplication",
        "multi-article-valid-missing": "mixed_valid_missing_article",
        "multi-article-all-missing": "insufficient_context",
        "multi-article-over-limit": "clarification_required",
    }
    cases: list[dict[str, Any]] = []
    for case in week11["cases"]:
        cases.append({**case, "review_category": categories[case["fixture_id"]]})
    broad_ids = {
        "week11-article-20",
        "week11-article-34",
        "week11-article-43",
        "week11-article-97",
        "week11-article-169",
    }
    for case in week11["broad_article_lookup"]["cases"]:
        if case["fixture_id"] in broad_ids:
            category = (
                "legal_keyword_article_lookup"
                if case["fixture_id"]
                in {"week11-article-20", "week11-article-34", "week11-article-43"}
                else "direct_legal_retrieval"
            )
            cases.append({**case, "review_category": category})
    for case in multi["cases"]:
        cases.append({**case, "review_category": categories[case["fixture_id"]]})

    selected_week9 = {
        "w9-004": "natural_paraphrase",
        "w9-005": "legal_keyword_article_lookup",
        "w9-008": "natural_paraphrase",
        "w9-014": "calculator_only",
        "w9-030": "retrieval_and_calculator",
    }
    for line in (
        (root / "data/evaluation/week9_agent_eval_v1.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ):
        case = json.loads(line)
        if case["case_id"] not in selected_week9:
            continue
        expected_articles = []
        article_number = case["expected_parameters"].get("article_number")
        if article_number is not None:
            expected_articles.append(article_number)
        cases.append(
            {
                "fixture_id": case["case_id"],
                "source": "data/evaluation/week9_agent_eval_v1.jsonl",
                "question": case["question"],
                "expected_route": case["expected_intent"],
                "expected_tools": case["expected_tools"],
                "expected_article_arguments": expected_articles,
                "review_category": selected_week9[case["case_id"]],
            }
        )
    return sorted(cases, key=lambda item: item["fixture_id"])


def request_json(url: str, method: str = "GET", body: dict[str, Any] | None = None) -> Any:
    encoded = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        url,
        data=encoded,
        method=method,
        headers={"Content-Type": "application/json"} if body is not None else {},
    )
    try:
        with urllib.request.urlopen(request, timeout=360) as response:
            raw = response.read()
            return json.loads(raw.decode("utf-8")) if raw else None
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"{method} {url} returned HTTP {exc.code}") from exc


def write_packet(rows: list[dict[str, Any]], csv_path: Path, html_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0])
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    header = "".join(f"<th>{html.escape(field)}</th>" for field in fields)
    body = "\n".join(
        "<tr>"
        + "".join(f"<td><div>{html.escape(str(row.get(field, '')))}</div></td>" for field in fields)
        + "</tr>"
        for row in rows
    )
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Week 12 manual review packet</title>
<style>
body{{font:14px system-ui;margin:24px;color:#172033}} h1{{margin-bottom:4px}}
.notice{{background:#fff7d6;border:1px solid #d9b44a;padding:12px;max-width:1100px}}
table{{border-collapse:collapse;margin-top:18px}}
th,td{{border:1px solid #ccd3df;padding:8px;vertical-align:top}}
th{{position:sticky;top:0;background:#172033;color:white}}
td div{{max-width:440px;max-height:220px;overflow:auto;white-space:pre-wrap}}
tr:nth-child(even){{background:#f5f7fa}}
</style></head><body><h1>Week 12 manual review packet</h1>
<p class="notice"><strong>Independent human review required.</strong>
All reviewer fields are intentionally blank. The rows are live HTTP Agent outputs captured from
official operational/evaluation fixtures; they are not self-approved.</p>
<p>Rows: {len(rows)}. Review instructions:
<code>docs/releases/manual_review_instructions.md</code>.</p>
<table><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table></body></html>
"""
    html_path.write_text(document, encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8080")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    cases = selected_cases(root)
    if len(cases) != 24:
        raise SystemExit(f"selection invariant failed: expected 24 cases, got {len(cases)}")
    rows: list[dict[str, Any]] = []
    for index, case in enumerate(cases, start=1):
        response = request_json(
            f"{args.base_url.rstrip('/')}/api/v1/chat",
            method="POST",
            body={"question": case["question"]},
        )
        rows.append(review_row(case, response, f"W12-{index:03d}"))
        conversation_id = response.get("conversation_id")
        if conversation_id:
            request_json(
                f"{args.base_url.rstrip('/')}/api/v1/conversations/{conversation_id}",
                method="DELETE",
            )
        print(f"{index:02d}/24 {case['fixture_id']} captured")
    validate_review_rows(rows)
    write_packet(
        rows,
        root / "evaluation/review/week12_manual_review_packet.csv",
        root / "evaluation/review/week12_manual_review_packet.html",
    )
    print("PASS: wrote 24-row live manual-review packet with blank reviewer fields")


if __name__ == "__main__":
    main()
