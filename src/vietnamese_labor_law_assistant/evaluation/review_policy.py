"""Policy for distinguishing independent human review from AI-assisted evidence."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

HUMAN_DECISIONS = frozenset({"PASS", "CORRECTED", "REJECTED", "NEEDS_DISCUSSION"})
AI_REVIEWER_MARKERS = (
    "ai",
    "assistant",
    "automated",
    "bot",
    "chatgpt",
    "codex",
    "gpt",
    "machine",
    "trí tuệ nhân tạo",
)
NON_INDEPENDENT_ROLE_MARKERS = ("project author",)


def reviewer_is_independent_human(reviewer_name: str | None) -> bool:
    """Return whether a supplied reviewer identity is not an AI/machine identity.

    This is a conservative metadata check, not proof of a person's legal credentials.
    A non-empty name, role, timestamp, and evidence note remain required before a
    review row can be counted as independent human evidence.
    """
    normalized = (reviewer_name or "").strip().casefold()
    return bool(normalized) and not any(marker in normalized for marker in AI_REVIEWER_MARKERS)


def reviewer_role_is_independent(reviewer_role: str | None) -> bool:
    """Return false for explicitly self-reviewing roles such as project author."""
    normalized = (reviewer_role or "").strip().casefold()
    return bool(normalized) and not any(
        marker in normalized for marker in NON_INDEPENDENT_ROLE_MARKERS
    )


def independent_human_review_errors(row: Mapping[str, str]) -> list[str]:
    """List missing or invalid evidence fields for a human-review packet row."""
    decision = row.get("human_decision", "").strip().upper()
    errors: list[str] = []
    if decision not in HUMAN_DECISIONS:
        errors.append("human_decision must be PASS, CORRECTED, REJECTED, or NEEDS_DISCUSSION")
    if not reviewer_is_independent_human(row.get("reviewer_name")):
        errors.append("reviewer_name is missing or identifies AI/machine review")
    if not reviewer_role_is_independent(row.get("reviewer_role")):
        errors.append(
            "reviewer_role is missing or identifies non-independent project-author review"
        )
    for field in ("reviewer_role", "reviewed_at", "evidence_note"):
        if not row.get(field, "").strip():
            errors.append(f"{field} is required")
    reviewed_at = row.get("reviewed_at", "").strip()
    if reviewed_at:
        try:
            datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
        except ValueError:
            errors.append("reviewed_at must use ISO-8601 format")
    return errors


def is_independent_human_review(row: Mapping[str, str]) -> bool:
    """Return true only for a complete, non-AI human-review decision."""
    return not independent_human_review_errors(row)


def is_project_author_source_verification(row: Mapping[str, str]) -> bool:
    """Accept completed source verification by a named human project author only.

    This narrower evidence class is valid for source-transcription confirmation;
    it deliberately does not make an evaluation label independently reviewed.
    """
    if not reviewer_is_independent_human(row.get("reviewer_name")):
        return False
    role = row.get("reviewer_role", "").strip().casefold()
    if "project author" not in role or "source verifier" not in role:
        return False
    return not any(not row.get(field, "").strip() for field in ("reviewed_at", "evidence_note"))
