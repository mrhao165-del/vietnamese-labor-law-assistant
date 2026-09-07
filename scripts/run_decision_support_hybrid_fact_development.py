"""Run one write-once Hybrid Fact V2 synthetic development evaluation."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from vietnamese_labor_law_assistant.common.settings import Settings, get_settings
from vietnamese_labor_law_assistant.decision_support.intake import (
    OpenAIStructuredCaseIntakeExtractor,
)
from vietnamese_labor_law_assistant.evaluation import (
    decision_support_hybrid_fact_development as hybrid_development,
)
from vietnamese_labor_law_assistant.evaluation import (
    decision_support_split_inference_development as split_development,
)
from vietnamese_labor_law_assistant.evaluation.decision_support_provider_pacing import (
    DevelopmentRequestPacer,
)

ACKNOWLEDGEMENT = "HYBRID_FACT_V2_SYNTHETIC_NOT_RELEASE"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--live-development", action="store_true")
    parser.add_argument("--acknowledge-not-release")
    parser.add_argument("--request-pacing-seconds", type=float, default=10)
    parser.add_argument("--inter-case-pacing-seconds", type=float, default=1)
    parser.add_argument("--rate-limit-max-retries", type=int)
    parser.add_argument("--rate-limit-max-wait-seconds", type=float)
    args = parser.parse_args(argv)
    if not args.live_development:
        parser.error("--live-development is required for provider calls")
    if args.acknowledge_not_release != ACKNOWLEDGEMENT:
        parser.error(f"--acknowledge-not-release must equal {ACKNOWLEDGEMENT}")
    if re.fullmatch(r"hybrid-fact-v2-[A-Za-z0-9][A-Za-z0-9._-]{0,104}", args.run_id) is None:
        parser.error("--run-id must be one safe Hybrid Fact V2 development path segment")

    repo_root = args.repo_root.resolve()
    matrix_path = (
        repo_root / "evaluation/development/decision_support/v1_1/post_rc2/"
        "split_inference_synthetic_v1.jsonl"
    )
    output_dir = (
        repo_root / "evaluation/development/decision_support/v1_1/post_rc2/runs" / args.run_id
    )
    try:
        settings = get_settings()
        overrides = {}
        if args.rate_limit_max_retries is not None:
            overrides["case_intake_transport_max_retries"] = args.rate_limit_max_retries
        if args.rate_limit_max_wait_seconds is not None:
            overrides["case_intake_transport_max_wait_seconds"] = args.rate_limit_max_wait_seconds
        if overrides:
            settings = Settings.model_validate({**settings.model_dump(), **overrides})
        pacer = DevelopmentRequestPacer(args.request_pacing_seconds)
        hybrid_development.validate_hybrid_provider_settings(settings)
    except ValueError:
        parser.error("Hybrid Fact development provider configuration is invalid")
    cases = split_development.load_split_inference_synthetic_cases(matrix_path)
    extractor = OpenAIStructuredCaseIntakeExtractor(settings, before_request=pacer.before_request)
    report = asyncio.run(
        hybrid_development.run_hybrid_fact_development(
            cases,
            settings,
            hybrid_development.HybridFactArtifactPaths.from_output_dir(output_dir),
            extractor=extractor,
            run_id=args.run_id,
            started_at=datetime.now(UTC),
            completed_at=None,
            matrix_path=matrix_path,
            request_pacing_seconds=args.request_pacing_seconds,
            inter_case_pacing_seconds=args.inter_case_pacing_seconds,
        )
    )
    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0 if report.gates.overall_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
