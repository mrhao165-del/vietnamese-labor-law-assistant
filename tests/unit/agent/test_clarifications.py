from vietnamese_labor_law_assistant.agent.clarifications import (
    AMBIGUOUS_CONTRACT_DURATION_OPERATION,
    NOTICE_PARAMETERS_OPERATION,
    clarification_for,
    referenced_article_numbers,
)
from vietnamese_labor_law_assistant.agent.enums import AgentIntent
from vietnamese_labor_law_assistant.agent.models import RouterOutput


def _clarification(operation: str, provider_question: str = "Câu hỏi chưa đạt.") -> RouterOutput:
    return RouterOutput(
        intent=AgentIntent.CALCULATOR_ONLY,
        confidence=1,
        rationale_code="MISSING_PARAMETERS",
        requested_operation=operation,
        requires_clarification=True,
        clarification_question=provider_question,
    )


def test_ambiguous_contract_duration_clarification_separates_three_goals() -> None:
    text = clarification_for(_clarification(AMBIGUOUS_CONTRACT_DURATION_OPERATION))
    assert "ngày bắt đầu" in text and "ngày kết thúc" in text
    assert "thời gian báo trước" in text
    assert "phân loại hợp đồng" in text
    assert "dưới 12 tháng" in text
    assert "12 đến 36 tháng" in text
    assert "không xác định thời hạn" in text
    assert "khoản 2 Điều 35" in text
    assert "xác định thời hạn (từ 12 đến 36 tháng)" not in text


def test_personalized_notice_clarification_requests_required_facts() -> None:
    text = clarification_for(_clarification(NOTICE_PARAMETERS_OPERATION))
    assert "dưới 12 tháng" in text
    assert "12 đến 36 tháng" in text
    assert "không xác định thời hạn" in text
    assert "khoản 2 Điều 35" in text


def test_unrecognized_clarification_preserves_bounded_provider_question() -> None:
    output = _clarification("OTHER_CLARIFICATION", "Vui lòng cho biết thông tin còn thiếu.")
    assert clarification_for(output) == "Vui lòng cho biết thông tin còn thiếu."


def test_article_references_support_repeated_and_compact_lists() -> None:
    assert referenced_article_numbers("Điều 20, Điều 32, Điều 35 và Điều 54") == [20, 32, 35, 54]
    assert referenced_article_numbers("Tóm tắt các Điều 20, 32, 35, 54") == [20, 32, 35, 54]
