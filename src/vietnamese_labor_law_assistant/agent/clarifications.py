"""Canonical no-tool clarification text selected from validated router semantics."""

from __future__ import annotations

import re

from .models import RouterOutput

AMBIGUOUS_CONTRACT_DURATION_OPERATION = "CLARIFY_CONTRACT_DURATION_PURPOSE"
ARTICLE_LIMIT_OPERATION = "CLARIFY_ARTICLE_LIMIT"
NOTICE_PARAMETERS_OPERATION = "CLARIFY_NOTICE_PARAMETERS"
NOTICE_FRAMEWORK_OVERVIEW_OPERATION = "NOTICE_FRAMEWORK_OVERVIEW"

_ARTICLE_REFERENCE = re.compile(
    r"\bĐiều\s+(\d+(?:\s*(?:,|và)\s*\d+)*)",
    re.IGNORECASE,
)
_INTEGER = re.compile(r"\d+")

_AMBIGUOUS_CONTRACT_DURATION_QUESTION = (
    "Bạn muốn (1) tính số ngày/tháng của hợp đồng, (2) xác định thời gian báo trước khi nghỉ "
    "việc, hay (3) phân loại hợp đồng? Nếu chọn (1), vui lòng cung cấp ngày bắt đầu và ngày kết "
    "thúc. Nếu chọn (2), vui lòng cho biết hợp đồng có thời hạn dưới 12 tháng, từ 12 đến 36 "
    "tháng, hay không xác định thời hạn, đồng thời cho biết có hoàn cảnh nào thuộc nhóm không "
    "cần báo trước tại khoản 2 Điều 35 hay không. Nếu chọn (3), vui lòng cung cấp điều khoản về "
    "thời hạn và thời điểm chấm dứt của hợp đồng."
)
_NOTICE_PARAMETERS_QUESTION = (
    "Để xác định thời gian báo trước cho trường hợp cụ thể, vui lòng cho biết hợp đồng có thời "
    "hạn dưới 12 tháng, từ 12 đến 36 tháng, hay không xác định thời hạn; đồng thời cho biết có "
    "hoàn cảnh nào thuộc nhóm không cần báo trước tại khoản 2 Điều 35 hay không."
)


def clarification_for(output: RouterOutput) -> str:
    """Return a stable clarification for known semantic operations."""

    operation = output.requested_operation.upper()
    if operation == AMBIGUOUS_CONTRACT_DURATION_OPERATION:
        return _AMBIGUOUS_CONTRACT_DURATION_QUESTION
    if operation == NOTICE_PARAMETERS_OPERATION:
        return _NOTICE_PARAMETERS_QUESTION
    return output.clarification_question or (
        "Vui lòng cung cấp các tham số còn thiếu: " + ", ".join(output.missing_parameters)
    )


def referenced_article_numbers(question: str) -> list[int]:
    """Extract distinct explicit Điều references in first-seen order."""

    return list(
        dict.fromkeys(
            int(value)
            for article_group in _ARTICLE_REFERENCE.findall(question)
            for value in _INTEGER.findall(article_group)
        )
    )


def article_limit_clarification(article_count: int, maximum: int) -> str:
    """Explain the bounded multi-article contract without invoking a tool."""

    return (
        f"Bạn đã yêu cầu {article_count} điều luật. Hệ thống hỗ trợ tối đa {maximum} "
        "điều luật trong một yêu cầu. Vui lòng chọn hoặc chia danh sách để mỗi yêu cầu "
        f"có tối đa {maximum} điều luật."
    )
