"""Offline Week 12 release artefact, documentation, and secret-safety verifier."""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
from pathlib import Path

from historical_frontend_lock import read_historical_frontend_lock_source

from vietnamese_labor_law_assistant.evaluation.week12_portfolio import (
    SELECTED_RETRIEVAL_CONFIG,
    select_phase_manifest,
    sha256_file,
    validate_benchmark_summary,
    validate_checksum_contract,
    validate_final_agent_guardrail,
    validate_final_candidate_manifest,
    validate_review_rows,
)
from vietnamese_labor_law_assistant.evaluation.week12_round3_review import (
    validate_completed_review,
)

LINK_PATTERN = re.compile(r"\[[^\]]+\]\((?!https?://|mailto:)([^)#]+)(?:#[^)]+)?\)")
SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bAIza[A-Za-z0-9_-]{20,}\b"),
)
FORBIDDEN_TRACKED_PARTS = (
    "data/runtime/",
    "frontend/node_modules/",
    "frontend/dist/",
    ".cache/",
)


def tracked_files(root: Path) -> list[Path]:
    output = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    ).stdout
    return [root / item.decode("utf-8") for item in output.split(b"\0") if item]


def validate_local_links(root: Path) -> None:
    missing: list[str] = []
    for document in (root / "README.md", *sorted((root / "docs").rglob("*.md"))):
        text = document.read_text(encoding="utf-8")
        for raw_target in LINK_PATTERN.findall(text):
            target = raw_target.strip().strip("<>")
            if not target or target.startswith("/"):
                continue
            resolved = (document.parent / target).resolve()
            if not resolved.exists():
                missing.append(f"{document.relative_to(root)} -> {target}")
    if missing:
        raise ValueError("missing local documentation links:\n" + "\n".join(missing))


def validate_secret_and_runtime_policy(root: Path) -> None:
    findings: list[str] = []
    for path in tracked_files(root):
        relative = path.relative_to(root).as_posix()
        if any(part in relative for part in FORBIDDEN_TRACKED_PARTS):
            findings.append(f"forbidden tracked runtime path: {relative}")
        if path.name == ".env" or (path.name.startswith(".env.") and path.name != ".env.example"):
            findings.append(f"forbidden tracked environment file: {relative}")
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                findings.append(f"possible credential in tracked file: {relative}")
                break
    if findings:
        raise ValueError("\n".join(findings))


def validate_week12_files(root: Path, manifest_phase: str = "auto") -> None:
    result_dir = root / "evaluation/results/week12"
    benchmark = json.loads((result_dir / "benchmark_summary.json").read_text(encoding="utf-8"))
    validate_benchmark_summary(benchmark)
    final_agent_guardrail = json.loads(
        (result_dir / "final_agent_guardrail.json").read_text(encoding="utf-8")
    )
    validate_final_agent_guardrail(final_agent_guardrail)
    manifest = json.loads((result_dir / "release_manifest.json").read_text(encoding="utf-8"))
    if manifest["retrieval"]["selected_config"] != SELECTED_RETRIEVAL_CONFIG:
        raise ValueError("release manifest selected configuration changed")
    versioned_sources = read_historical_frontend_lock_source(root)
    checksum_targets = {
        manifest["corpus"]["path"]: manifest["corpus"]["sha256"],
        manifest["evaluation_dataset"]["path"]: manifest["evaluation_dataset"]["sha256"],
        **{
            name: digest for name, digest in manifest["lockfiles"].items() if name != "compose.yaml"
        },
        manifest["evaluation_dataset"]["manifest_path"]: manifest["evaluation_dataset"][
            "manifest_sha256"
        ],
    }
    validate_checksum_contract(
        root,
        checksum_targets,
        versioned_sources=versioned_sources,
        context="release manifest",
    )
    selected_manifest = select_phase_manifest(result_dir, manifest_phase)
    selected_name = selected_manifest.name
    if selected_name == "final_release_manifest.json":
        validate_final_candidate_manifest(
            root,
            json.loads(selected_manifest.read_text(encoding="utf-8")),
            versioned_sources=versioned_sources,
        )
    elif selected_name == "remediation_manifest.json":
        remediation_manifest_path = selected_manifest
        remediation = json.loads(remediation_manifest_path.read_text(encoding="utf-8"))
        if remediation.get("status") != "REMEDIATION_COMPLETE_PENDING_HUMAN_REREVIEW":
            raise ValueError("invalid remediation status")
        if sha256_file(root / "compose.yaml") != remediation.get("compose_sha256"):
            raise ValueError("remediation manifest checksum mismatch: compose.yaml")
    elif sha256_file(root / "compose.yaml") != manifest["lockfiles"]["compose.yaml"]:
        raise ValueError("release manifest checksum mismatch: compose.yaml")
    preflight = json.loads((result_dir / "preflight.json").read_text(encoding="utf-8"))
    if preflight["status"] not in {"PASS", "FAIL", "PARTIAL"} or not isinstance(
        preflight["checks"], list
    ):
        raise ValueError("invalid preflight schema")
    with (root / "evaluation/review/week12_manual_review_packet.csv").open(
        encoding="utf-8-sig", newline=""
    ) as stream:
        review_rows = list(csv.DictReader(stream))
    validate_review_rows(review_rows, reviewer_fields_must_be_blank=False)
    _validate_review_rounds(root)
    for name in ("architecture.png", "rag-pipeline.png", "agent-graph.png", "evaluation-chart.png"):
        path = root / "docs/images" / name
        if not path.exists() or path.stat().st_size < 10_000:
            raise ValueError(f"missing or implausibly small asset: {path}")


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def _validate_review_rounds(root: Path) -> None:
    """Verify archived review evidence and the completed round-3 contract."""

    result_dir = root / "evaluation/results/week12"
    for round_number in (1, 2, 3):
        evidence = json.loads(
            (result_dir / f"review_round{round_number}_validation.json").read_text(encoding="utf-8")
        )
        source = evidence.get("reviewed_packet", evidence.get("source"))
        archive = evidence["archive"]
        source_path = root / source["path"]
        archive_path = root / archive["path"]
        if sha256_file(source_path) != source["sha256"]:
            raise ValueError(f"round-{round_number} reviewed source checksum mismatch")
        if sha256_file(archive_path) != archive["sha256"]:
            raise ValueError(f"round-{round_number} review archive checksum mismatch")
        if sha256_file(source_path) != sha256_file(archive_path):
            raise ValueError(f"round-{round_number} source/archive mismatch")

    blank_path = root / "evaluation/review/week12_manual_review_round3.csv"
    reviewed_path = root / "evaluation/review/week12_manual_review_round3_reviewed.csv"
    ai_path = root / "evaluation/review/week12_manual_review_round3_ai_pre_review.csv"
    validate_completed_review(
        _read_csv(blank_path),
        _read_csv(reviewed_path),
        {"W12-R3-006", "W12-R3-008", "W12-R3-019"},
        _read_csv(ai_path) if ai_path.exists() else None,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest-phase",
        choices=("auto", "historical", "remediation", "final"),
        default="auto",
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    validate_week12_files(root, args.manifest_phase)
    validate_local_links(root)
    validate_secret_and_runtime_policy(root)
    selected = select_phase_manifest(root / "evaluation/results/week12", args.manifest_phase)
    print(f"PASS: Week 12 artefacts, documentation paths, tracked-file safety, and {selected.name}")


if __name__ == "__main__":
    main()
