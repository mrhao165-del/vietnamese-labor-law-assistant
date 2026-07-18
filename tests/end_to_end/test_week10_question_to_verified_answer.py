"""Fixture-level contract that the final agent result exposes verification."""

from vietnamese_labor_law_assistant.agent.models import AgentResult


def test_agent_result_contract_has_verification() -> None:
    assert "verification" in AgentResult.model_fields
