"""Run operational Week 11 fixtures through the public HTTP API."""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from vietnamese_labor_law_assistant.guardrails.source_registry import CanonicalSourceRegistry

DEFAULT_FIXTURES = Path("tests/end_to_end/fixtures/week11_live_smoke_cases.json")
DEFAULT_SOURCE = Path("data/processed/labor_law_clauses.jsonl")
FORBIDDEN_PUBLIC_MARKERS = (
    "INSUFFICIENT_VERIFIED_EVIDENCE",
    "traceback",
    "authorization:",
    "api_key=",
)


def _post_chat(url: str, question: str, timeout: float) -> tuple[int, dict[str, Any]]:
    payload = json.dumps({"question": question}, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        try:
            body = json.load(exc)
        except (json.JSONDecodeError, UnicodeDecodeError):
            body = {"error": "non_json_http_error"}
        return exc.code, body


def _citations_are_canonical(
    citations: list[dict[str, Any]], registry: CanonicalSourceRegistry
) -> bool:
    for citation in citations:
        chunk_id = citation.get("chunk_id")
        record = registry.get(chunk_id) if isinstance(chunk_id, str) else None
        if record is None:
            return False
        if citation.get("article_number") != record.article_number:
            return False
        if citation.get("clause_number") != record.clause_number:
            return False
    return True


def _evaluate(
    fixture: dict[str, Any], status: int, body: dict[str, Any], registry: CanonicalSourceRegistry
) -> dict[str, Any]:
    tools = [item.get("tool_name") for item in body.get("tool_trace", [])]
    citations = body.get("citations", [])
    verification = body.get("verification") or {}
    public_text = json.dumps(body, ensure_ascii=False).casefold()
    checks = {
        "http_200": status == 200,
        "route": body.get("route") == fixture["expected_route"],
        "final_status": body.get("final_status") in fixture["expected_final_statuses"],
        "verification": verification.get("status") in fixture["expected_verification_statuses"],
        "tools": tools == fixture["expected_tools"],
        "minimum_citations": len(citations) >= fixture["minimum_citations"],
        "maximum_citations": len(citations) <= fixture.get("maximum_citations", 1000),
        "canonical_citations": _citations_are_canonical(citations, registry),
        "public_answer": bool(body.get("answer_text")),
        "safe_envelope": not any(
            marker.casefold() in public_text for marker in FORBIDDEN_PUBLIC_MARKERS
        ),
    }
    return {
        "fixture_id": fixture["fixture_id"],
        "source": fixture["source"],
        "http_status": status,
        "workflow_status": body.get("final_status"),
        "route": body.get("route"),
        "tools": tools,
        "trace_count": len(body.get("tool_trace", [])),
        "verification": verification.get("status"),
        "reason_code": body.get("verification_code"),
        "citation_count": len(citations),
        "canonical_citation_validity": checks["canonical_citations"],
        "latency_ms": body.get("latency_ms"),
        "checks": checks,
        "result": "PASS" if all(checks.values()) else "FAIL",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8080")
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--timeout", type=float, default=180.0)
    args = parser.parse_args()

    payload = json.loads(args.fixtures.read_text(encoding="utf-8"))
    registry = CanonicalSourceRegistry(args.source)
    rows: list[dict[str, Any]] = []
    for fixture in payload["cases"]:
        for run_index in range(1, fixture["runs"] + 1):
            started = time.perf_counter()
            status, body = _post_chat(
                f"{args.base_url.rstrip('/')}/api/v1/chat", fixture["question"], args.timeout
            )
            row = _evaluate(fixture, status, body, registry)
            row["run_index"] = run_index
            row["client_elapsed_ms"] = round((time.perf_counter() - started) * 1000, 3)
            rows.append(row)
            print(json.dumps(row, ensure_ascii=False))
    summary = {
        "schema_version": payload["schema_version"],
        "classification": payload["classification"],
        "runs": len(rows),
        "passed": sum(row["result"] == "PASS" for row in rows),
        "failed": sum(row["result"] == "FAIL" for row in rows),
    }
    print(json.dumps({"summary": summary}, ensure_ascii=False))
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
