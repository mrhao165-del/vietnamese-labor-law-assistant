"""Validation of calculator legal bases against the fixed processed-source JSONL."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .models import LegalBasis
from .rules import DURATION_RULES, NOTICE_RULES

_CLAUSES_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "processed" / "labor_law_clauses.jsonl"
)


@dataclass(frozen=True)
class ProvenanceValidationReport:
    valid: bool
    checked_rule_count: int
    missing_legal_basis_count: int
    issues: tuple[str, ...]


def validate_rule_provenance() -> ProvenanceValidationReport:
    """Validate all immutable rules; callers cannot supply or scan arbitrary paths."""
    records = [json.loads(line) for line in _CLAUSES_PATH.read_text(encoding="utf-8").splitlines()]
    issues: list[str] = []
    rules = (*NOTICE_RULES, *DURATION_RULES)
    for rule in rules:
        for basis in rule.legal_basis:
            if not _basis_exists(basis, records):
                issues.append(f"{rule.rule_id}:{basis.article}.{basis.clause}.{basis.point}")
    return ProvenanceValidationReport(
        valid=not issues,
        checked_rule_count=len(rules),
        missing_legal_basis_count=len(issues),
        issues=tuple(issues),
    )


def _basis_exists(basis: LegalBasis, records: list[dict[str, object]]) -> bool:
    for record in records:
        if (
            record.get("chunk_id") == basis.source_chunk_id
            and record.get("document_id") == basis.document_id
            and record.get("article_number") == basis.article
            and record.get("clause_number") == basis.clause
        ):
            points = record.get("point_labels", [])
            return basis.point is None or (isinstance(points, list) and basis.point in points)
    return False
