from __future__ import annotations

from vietnamese_labor_law_assistant.calculator.provenance import validate_rule_provenance
from vietnamese_labor_law_assistant.calculator.rules import DURATION_RULES, NOTICE_RULES


def test_every_rule_legal_basis_exists_in_the_fixed_processed_source() -> None:
    report = validate_rule_provenance()
    assert report.valid
    assert report.checked_rule_count == len(NOTICE_RULES) + len(DURATION_RULES)
    assert report.missing_legal_basis_count == 0
    assert report.issues == ()


def test_external_regulation_rule_retains_article_35_citation() -> None:
    external = next(rule for rule in NOTICE_RULES if "EXTERNAL" in rule.rule_id)
    basis = external.legal_basis[0]
    assert basis.article == 35 and basis.clause == 1 and basis.point == "d"
