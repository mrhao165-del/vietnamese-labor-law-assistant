"""Coverage tests for the deterministic fact-policy registry."""

from __future__ import annotations


def test_policy_registry_covers_the_canonical_17_keys_without_redefining_contracts() -> None:
    from vietnamese_labor_law_assistant.decision_support.fact_contract import (
        CANONICAL_FACT_CONTRACT,
    )
    from vietnamese_labor_law_assistant.decision_support.fact_policies import (
        FACT_POLICY_REGISTRY,
        FactNormalizationKind,
    )
    from vietnamese_labor_law_assistant.decision_support.issue_registry import FactKey

    assert tuple(FACT_POLICY_REGISTRY) == tuple(FactKey)
    assert len(FACT_POLICY_REGISTRY) == 17
    assert all(
        policy.definition is CANONICAL_FACT_CONTRACT[fact_key]
        for fact_key, policy in FACT_POLICY_REGISTRY.items()
    )
    assert set(FactNormalizationKind) == {
        FactNormalizationKind.MONTH_DURATION,
        FactNormalizationKind.MONEY_VND,
        FactNormalizationKind.EXACT_ISO_DATE,
        FactNormalizationKind.TEMPORAL_EXPRESSION,
        FactNormalizationKind.CONTRACT_TYPE,
        FactNormalizationKind.CONTRACT_EXPIRY_STATEMENT,
        FactNormalizationKind.NOTICE_SPECIAL_CASE,
        FactNormalizationKind.EMPLOYEE_ROLE,
        FactNormalizationKind.WAGE_PAYMENT_PROBLEM,
        FactNormalizationKind.WAGE_PAYMENT_STATUS,
        FactNormalizationKind.WAGE_DELAY_FORCE_MAJEURE,
    }


def test_every_policy_has_positive_semantic_anchors_and_an_explicit_normalizer() -> None:
    from vietnamese_labor_law_assistant.decision_support.fact_policies import (
        FACT_POLICY_REGISTRY,
    )

    assert all(policy.semantic_anchors for policy in FACT_POLICY_REGISTRY.values())
    assert all(policy.normalization_kind is not None for policy in FACT_POLICY_REGISTRY.values())


def test_every_non_role_policy_declares_neighbor_property_starts() -> None:
    from vietnamese_labor_law_assistant.decision_support.fact_policies import (
        FACT_POLICY_REGISTRY,
    )
    from vietnamese_labor_law_assistant.decision_support.issue_registry import FactKey

    for fact_key, policy in FACT_POLICY_REGISTRY.items():
        if fact_key is FactKey.EMPLOYEE_ROLE:
            assert policy.property_start_patterns == ()
        else:
            assert policy.property_start_patterns
