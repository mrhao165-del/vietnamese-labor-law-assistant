"""Audit every active frozen artifact protected by an exact-byte SHA-256."""

from __future__ import annotations

from pathlib import Path

from vietnamese_labor_law_assistant.evaluation.frozen_evidence import (
    discover_frozen_evidence,
    validate_frozen_evidence,
)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    results = validate_frozen_evidence(root, discover_frozen_evidence(root))
    for result in results:
        status = "PASS" if result.matches else "FAIL"
        print(
            f"{status} {result.evidence.path} "
            f"expected={result.evidence.expected_sha256} actual={result.actual_sha256} "
            f"source={result.evidence.source_field}"
        )
    failures = [result for result in results if not result.matches]
    print(f"checked={len(results)} failed={len(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
