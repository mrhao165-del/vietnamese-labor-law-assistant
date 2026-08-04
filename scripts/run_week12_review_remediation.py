"""Run the bounded Week 12 remediation matrix through the public HTTP API."""

from __future__ import annotations

import argparse
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


def _evaluate(
    case: dict[str, Any],
    body: dict[str, Any],
    registry: CanonicalSourceRegistry,
) -> tuple[dict[str, bool], str]:
    traces = body.get("tool_trace") or []
    tools = [item.get("tool_name") for item in traces]
    citations = body.get("citations") or []
    citation_records = [
        registry.get(chunk_id)
        for item in citations
        if isinstance(item, dict) and isinstance((chunk_id := item.get("chunk_id")), str)
    ]
    answer = str(body.get("answer_text") or "")
    expected_routes = case.get("expected_routes", [case["expected_route"]])
    checks = {
        "route": body.get("route") in expected_routes,
        "status": body.get("final_status") == case["expected_status"],
        "canonical_citations": all(record is not None for record in citation_records),
        "safe_answer": bool(answer) and "INSUFFICIENT_VERIFIED_EVIDENCE" not in answer,
    }
    expected_router_decision = case.get("expected_router_decision")
    if expected_router_decision is not None:
        checks["router_decision"] = body.get("router_decision") == expected_router_decision
    expected_planned_tools = case.get("expected_planned_tools")
    if expected_planned_tools is not None:
        checks["planned_tools"] = body.get("planned_tools") == expected_planned_tools
    expected_verification_status = case.get("expected_verification_status")
    if expected_verification_status is not None:
        checks["verification_status"] = (body.get("verification") or {}).get(
            "status"
        ) == expected_verification_status
    expected_tools = case.get("expected_tools")
    if expected_tools is not None:
        checks["tools"] = tools == expected_tools
    unordered_tools = case.get("expected_tools_unordered")
    if unordered_tools is not None:
        checks["tools"] = sorted(tools) == sorted(unordered_tools)
    tools_one_of = case.get("expected_tools_one_of")
    if tools_one_of is not None:
        checks["tools"] = tools in tools_one_of
    unordered_tools_one_of = case.get("expected_tools_unordered_one_of")
    if unordered_tools_one_of is not None:
        checks["tools"] = sorted(tools) in [sorted(option) for option in unordered_tools_one_of]
    expected_articles = case.get("expected_articles")
    if expected_articles is not None:
        actual_articles = {
            record.article_number for record in citation_records if record is not None
        }
        checks["citation_article_coverage"] = set(expected_articles).issubset(actual_articles)
    expected_reason = case.get("expected_reason")
    if expected_reason is not None:
        checks["reason"] = body.get("verification_code") == expected_reason
    for tool_name, expected in case.get("expected_parameters", {}).items():
        actual = next(
            (item.get("parameters") or {} for item in traces if item.get("tool_name") == tool_name),
            {},
        )
        checks[f"parameters:{tool_name}"] = all(
            actual.get(key) == value for key, value in expected.items()
        )
    required_clauses = case.get("required_clauses")
    if required_clauses is not None:
        actual_clauses = {record.clause_number for record in citation_records if record is not None}
        checks["clause_coverage"] = set(required_clauses).issubset(actual_clauses)
    folded = answer.casefold()
    for required in case.get("required_text", []):
        checks[f"contains:{required}"] = required.casefold() in folded
    for forbidden in case.get("forbidden_text", []):
        checks[f"excludes:{forbidden}"] = forbidden.casefold() not in folded
    failed = [name for name, passed in checks.items() if not passed]
    return checks, "all checks passed" if not failed else "failed checks: " + ", ".join(failed)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8080")
    parser.add_argument(
        "--fixtures",
        type=Path,
        default=Path("tests/end_to_end/fixtures/week12_review_remediation_cases.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evaluation/results/week12/review_remediation_live.json"),
    )
    parser.add_argument("--timeout", type=float, default=360)
    parser.add_argument("--original-review-id", action="append", default=[])
    args = parser.parse_args()
    fixtures = json.loads(args.fixtures.read_text(encoding="utf-8"))
    registry = CanonicalSourceRegistry(Path("data/processed/labor_law_clauses.jsonl"))
    attempts: list[dict[str, Any]] = []
    cases = fixtures["cases"]
    if args.original_review_id:
        selected = set(args.original_review_id)
        cases = [case for case in cases if case.get("original_review_id") in selected]
    for case in cases:
        for run_index in range(1, int(case["runs"]) + 1):
            started = time.perf_counter()
            body = _post(
                f"{args.base_url.rstrip('/')}/api/v1/chat",
                case["question"],
                args.timeout,
            )
            elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
            checks, reason = _evaluate(case, body, registry)
            row = {
                "case_id": case.get("case_id"),
                "parent_round2_review_id": case.get("parent_round2_review_id"),
                "original_review_id": case.get("original_review_id"),
                "run_index": run_index,
                "request_id": body.get("request_id"),
                "question": case["question"],
                "router_decision": body.get("router_decision"),
                "route": body.get("route"),
                "outcome_status": body.get("final_status"),
                "planned_tools": body.get("planned_tools") or [],
                "observed_tools": [item.get("tool_name") for item in body.get("tool_trace") or []],
                "sanitized_parameters": [
                    item.get("parameters") for item in body.get("tool_trace") or []
                ],
                "final_status": body.get("final_status"),
                "answer": body.get("answer_text"),
                "citations": body.get("citations") or [],
                "verification": body.get("verification"),
                "verification_code": body.get("verification_code"),
                "warnings": body.get("warnings") or [],
                "latency_ms": body.get("latency_ms"),
                "client_elapsed_ms": elapsed_ms,
                "checks": checks,
                "result": "PASS" if all(checks.values()) else "FAIL",
                "pass_fail_reason": reason,
                "source_commit": "3f659b6ad12235f8c804d14856c85cc4645cba34",
                "runtime_configuration": {
                    "deployment": "DOCKER_COMPOSE_CPU",
                    "selected_retrieval_config": "R2_H2_C10_O5_L512_B1",
                    "guardrail_context_limit": 20,
                },
            }
            attempts.append(row)
            print(json.dumps(row, ensure_ascii=False))
    report = {
        "schema_version": "1.0",
        "status": "PASS" if all(row["result"] == "PASS" for row in attempts) else "FAIL",
        "provenance": "LIVE_DOCKER_COMPOSE_CPU_PUBLIC_HTTP",
        "generated_at": datetime.now(UTC).isoformat(),
        "attempt_count": len(attempts),
        "passed": sum(row["result"] == "PASS" for row in attempts),
        "failed": sum(row["result"] == "FAIL" for row in attempts),
        "attempts": attempts,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
