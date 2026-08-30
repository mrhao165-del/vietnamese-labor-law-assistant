"""Canonical Prompt-6 prerequisite finalization and approval contracts."""

from __future__ import annotations

import csv
import importlib
import importlib.util
import json
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from vietnamese_labor_law_assistant.evaluation.decision_support_v1_1 import (
    load_v1_1_candidate,
)

CORRECTED_CANDIDATE = Path(
    "data/evaluation/decision_support/v1_1/v1_1_evaluation_candidate_corrected.jsonl"
)
PREFILLED_PACKET = Path(
    "evaluation/review/decision_support/v1_1/"
    "v1_1_human_review_packet_corrected_prefilled_for_human_review.csv"
)
THRESHOLD_SPEC = Path("data/evaluation/decision_support/v1_1/v1_1_proposed_thresholds.json")
MODULE_NAME = "vietnamese_labor_law_assistant.evaluation.decision_support_v1_1_approval"
REVIEWED_AT = datetime(
    2026,
    8,
    30,
    20,
    15,
    30,
    tzinfo=timezone(timedelta(hours=7)),
)


def _approval_module():
    module_spec = importlib.util.find_spec(MODULE_NAME)
    assert module_spec is not None, "the canonical v1.1 approval contract is missing"
    return importlib.import_module(MODULE_NAME)


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _copy_pending_packet(path: Path) -> None:
    rows = _rows(PREFILLED_PACKET)
    fields = list(rows[0])
    for row in rows:
        row["reviewed_at"] = ""
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def test_review_finalizer_changes_only_reviewed_at_and_validates_all_26_rows(
    tmp_path: Path,
) -> None:
    approval = _approval_module()
    packet = tmp_path / "reviewed.csv"
    _copy_pending_packet(packet)
    before = _rows(packet)

    validation = approval.finalize_v1_1_review_packet(
        load_v1_1_candidate(CORRECTED_CANDIDATE),
        packet,
        project_author_name="mrhao165-del",
        reviewed_at=REVIEWED_AT,
    )

    after = _rows(packet)
    assert validation.status == "PASS"
    assert validation.total_rows == 26
    assert validation.pass_count == 26
    assert validation.pending_count == 0
    assert validation.human_validated_true_count == 26
    assert {row["reviewed_at"] for row in after} == {"2026-08-30T20:15:30+07:00"}
    assert all(row["human_validated"] == "false" for row in after)
    assert all(row["review_status"] == "PENDING" for row in after)
    assert all(row["frozen_final"] == "false" for row in after)
    for old_row, new_row in zip(before, after, strict=True):
        assert {key: value for key, value in new_row.items() if key != "reviewed_at"} == {
            key: value for key, value in old_row.items() if key != "reviewed_at"
        }


def test_threshold_approval_is_a_sidecar_and_detects_any_later_threshold_change(
    tmp_path: Path,
) -> None:
    approval = _approval_module()
    threshold_spec = tmp_path / "v1_1_proposed_thresholds.json"
    approval_path = tmp_path / "v1_1_threshold_approval.json"
    shutil.copyfile(THRESHOLD_SPEC, threshold_spec)
    threshold_bytes = threshold_spec.read_bytes()

    evidence = approval.record_v1_1_threshold_approval(
        threshold_spec,
        approval_path,
        reviewer_identifier="tran-phu-hao",
        reviewer_name="Trần Phú Hào",
        reviewer_role="INDEPENDENT_LEGAL_REVIEWER",
        project_author_name="mrhao165-del",
        approved_at=REVIEWED_AT,
    )
    validation = approval.validate_v1_1_threshold_approval(
        threshold_spec,
        approval_path,
        project_author_name="mrhao165-del",
    )

    assert threshold_spec.read_bytes() == threshold_bytes
    assert evidence.approval_decision == "APPROVE_UNCHANGED"
    assert evidence.human_approved is True
    assert evidence.reviewer_identifier == "tran-phu-hao"
    assert evidence.reviewer_name == "Trần Phú Hào"
    assert evidence.reviewer_role == "INDEPENDENT_LEGAL_REVIEWER"
    assert evidence.approved_at.isoformat() == "2026-08-30T20:15:30+07:00"
    assert evidence.changed_after_final_results is False
    assert evidence.frozen_final is False
    assert evidence.threshold_count == 18
    assert validation.status == "PASS"
    assert validation.thresholds_unchanged is True

    changed = json.loads(threshold_spec.read_text(encoding="utf-8"))
    changed["thresholds"]["overall_fact_f1_min"] = 0.89
    threshold_spec.write_text(
        json.dumps(changed, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    invalid = approval.validate_v1_1_threshold_approval(
        threshold_spec,
        approval_path,
        project_author_name="mrhao165-del",
    )
    assert invalid.status == "FAIL"
    assert invalid.thresholds_unchanged is False
    assert "threshold specification checksum differs from the approved proposal" in invalid.errors


def test_threshold_validator_accepts_absolute_bytes_with_registered_identity(
    tmp_path: Path,
) -> None:
    """Copied proposal bytes remain bound to the registered repository identity."""

    approval = _approval_module()
    threshold_spec = tmp_path / "v1_1_proposed_thresholds.json"
    approval_path = tmp_path / "v1_1_threshold_approval.json"
    shutil.copyfile(THRESHOLD_SPEC, threshold_spec)
    shutil.copyfile(
        Path("evaluation/review/decision_support/v1_1/v1_1_threshold_approval.json"),
        approval_path,
    )

    validation = approval.validate_v1_1_threshold_approval(
        threshold_spec,
        approval_path,
        project_author_name="mrhao165-del",
        threshold_spec_identity=(
            "data/evaluation/decision_support/v1_1/v1_1_proposed_thresholds.json"
        ),
    )

    assert validation.status == "PASS"


def test_canonical_cli_finalizes_and_validates_without_running_frozen_evaluation(
    tmp_path: Path,
) -> None:
    packet = tmp_path / "reviewed.csv"
    threshold_spec = tmp_path / "v1_1_proposed_thresholds.json"
    approval_path = tmp_path / "v1_1_threshold_approval.json"
    _copy_pending_packet(packet)
    shutil.copyfile(THRESHOLD_SPEC, threshold_spec)
    threshold_bytes = threshold_spec.read_bytes()

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/finalize_v1_1_prompt6_prerequisites.py",
            "--candidate",
            str(CORRECTED_CANDIDATE),
            "--packet",
            str(packet),
            "--threshold-spec",
            str(threshold_spec),
            "--approval",
            str(approval_path),
            "--project-author-name",
            "mrhao165-del",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert report["human_review"]["status"] == "PASS"
    assert report["human_review"]["pass_count"] == 26
    assert report["threshold_approval"]["status"] == "PASS"
    assert report["threshold_approval"]["thresholds_unchanged"] is True
    assert report["frozen_evaluation_run"] is False
    assert threshold_spec.read_bytes() == threshold_bytes

    validated = subprocess.run(
        [
            sys.executable,
            "scripts/validate_v1_1_threshold_approval.py",
            "--threshold-spec",
            str(threshold_spec),
            "--approval",
            str(approval_path),
            "--project-author-name",
            "mrhao165-del",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert validated.returncode == 0, validated.stderr
    assert json.loads(validated.stdout)["status"] == "PASS"
