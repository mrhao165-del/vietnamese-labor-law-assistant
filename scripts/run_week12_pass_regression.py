"""Re-run every round-1 PASS row once through the remediated public API."""

from __future__ import annotations

import argparse
import csv
import json
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from vietnamese_labor_law_assistant.guardrails.source_registry import CanonicalSourceRegistry


def _post(url: str, question: str, timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps({"question": question}, ensure_ascii=False).encode(),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def _run_case(
    case: dict[str, str],
    args: argparse.Namespace,
    registry: CanonicalSourceRegistry,
    run_index: int,
) -> dict[str, Any]:
    started = time.perf_counter()
    body = _post(f"{args.base_url.rstrip('/')}/api/v1/chat", case["question"], args.timeout)
    traces = body.get("tool_trace") or []
    citations = body.get("citations") or []
    expected_tools = json.loads(case["expected_tool_calls"])
    expected_articles = set(json.loads(case["expected_article_clause_point"]))
    actual_articles: set[int] = set()
    canonical = True
    for citation in citations:
        chunk_id = citation.get("chunk_id")
        record = registry.get(chunk_id) if isinstance(chunk_id, str) else None
        canonical = canonical and record is not None
        if record is not None:
            actual_articles.add(record.article_number)
    checks = {
        "route": body.get("route") == case["expected_route"],
        "tools": [item.get("tool_name") for item in traces] == expected_tools,
        "canonical_citations": canonical,
        "article_coverage": bool(
            not expected_articles
            or expected_articles.intersection({998, 999})
            or expected_articles.issubset(actual_articles)
        ),
        "safe_answer": bool(body.get("answer_text"))
        and "INSUFFICIENT_VERIFIED_EVIDENCE" not in str(body.get("answer_text")),
    }
    return {
        "review_id": case["review_id"],
        "question_id": case["question_id"],
        "run_index": run_index,
        "request_id": body.get("request_id"),
        "route": body.get("route"),
        "observed_tools": [item.get("tool_name") for item in traces],
        "final_status": body.get("final_status"),
        "verification_code": body.get("verification_code"),
        "citation_count": len(citations),
        "latency_ms": body.get("latency_ms"),
        "client_elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "checks": checks,
        "result": "PASS" if all(checks.values()) else "FAIL",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8080")
    parser.add_argument("--timeout", type=float, default=360)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evaluation/results/week12/review_remediation_pass_regression.json"),
    )
    parser.add_argument("--review-id", action="append", default=[])
    parser.add_argument("--runs", type=int, default=1)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    with (root / "evaluation/review/week12_manual_review_packet.csv").open(
        encoding="utf-8-sig", newline=""
    ) as stream:
        cases = [row for row in csv.DictReader(stream) if row["reviewer_decision"] == "PASS"]
    if args.review_id:
        selected = set(args.review_id)
        cases = [case for case in cases if case["review_id"] in selected]
    elif len(cases) != 15:
        raise SystemExit(f"expected 15 round-1 PASS rows, got {len(cases)}")
    registry = CanonicalSourceRegistry(root / "data/processed/labor_law_clauses.jsonl")
    attempts = []
    for case in cases:
        for run_index in range(1, args.runs + 1):
            row = _run_case(case, args, registry, run_index)
            attempts.append(row)
            print(json.dumps(row, ensure_ascii=False))
    report = {
        "schema_version": "1.0",
        "status": "PASS" if all(row["result"] == "PASS" for row in attempts) else "FAIL",
        "provenance": "LIVE_DOCKER_COMPOSE_CPU_PUBLIC_HTTP",
        "generated_at": datetime.now(UTC).isoformat(),
        "case_count": len(attempts),
        "passed": sum(row["result"] == "PASS" for row in attempts),
        "failed": sum(row["result"] == "FAIL" for row in attempts),
        "attempts": attempts,
    }
    output = args.output if args.output.is_absolute() else root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
