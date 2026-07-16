from __future__ import annotations

import json
from uuid import UUID

import pytest
from pydantic import ValidationError

from vietnamese_labor_law_assistant.calculator.models import (
    ContractDurationInput,
    NoticePeriodInput,
)
from vietnamese_labor_law_assistant.mcp_servers.legal_calculator.schemas import (
    ToolMeta,
    ToolResponse,
)


def test_closed_notice_enums_reject_unknown_values() -> None:
    with pytest.raises(ValidationError):
        NoticePeriodInput.model_validate({"contract_type": "UNKNOWN"})
    with pytest.raises(ValidationError):
        NoticePeriodInput.model_validate({"contract_type": "INDEFINITE", "special_case": "UNKNOWN"})


@pytest.mark.parametrize("value", ["", "2026/01/01", "2026-01-01T00:00:00"])
def test_duration_input_requires_iso_calendar_date(value: str) -> None:
    with pytest.raises(ValidationError):
        ContractDurationInput.model_validate(
            {"contract_type": "FIXED_TERM", "start_date": value, "end_date": "2026-02-01"}
        )


def test_tool_envelope_json_is_stable_and_serializable() -> None:
    response = ToolResponse[ToolMeta](
        ok=True,
        data=ToolMeta(tool="data", request_id="2c9fccc5-dfb1-4b2d-a8a9-43a8393a8f2b"),
        meta=ToolMeta(
            tool="calculate_notice_period", request_id="3c9fccc5-dfb1-4b2d-a8a9-43a8393a8f2b"
        ),
    )
    body = response.model_dump(mode="json")
    assert json.loads(response.model_dump_json()) == body
    assert UUID(body["meta"]["request_id"])
