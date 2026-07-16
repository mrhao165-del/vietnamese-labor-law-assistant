"""Thin MCP adapter over the deterministic calculator service."""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from typing import Any, Protocol, TypeVar

import structlog
from pydantic import BaseModel, ValidationError

from vietnamese_labor_law_assistant.calculator.errors import (
    EndDateBeforeStartDateError,
    InvalidDateRangeError,
    InvalidInputCombinationError,
    RuleNotFoundError,
)
from vietnamese_labor_law_assistant.calculator.models import (
    ContractDurationInput,
    ContractDurationResult,
    NoticePeriodInput,
    NoticePeriodResult,
)
from vietnamese_labor_law_assistant.calculator.service import CalculatorService

from .schemas import ToolError, ToolMeta, ToolResponse

DataT = TypeVar("DataT", bound=BaseModel)


class CalculatorServicePort(Protocol):
    def calculate_notice_period(self, payload: NoticePeriodInput) -> NoticePeriodResult: ...

    def calculate_contract_duration(
        self, payload: ContractDurationInput
    ) -> ContractDurationResult: ...


class LegalCalculatorToolAdapter:
    """Validates bounded MCP inputs and maps calculator outcomes to public envelopes."""

    def __init__(
        self, service_provider: Callable[[], CalculatorServicePort] = CalculatorService
    ) -> None:
        self._service_provider = service_provider
        self._logger = structlog.get_logger(__name__)

    def calculate_notice_period(
        self,
        contract_type: object,
        special_case: object = "NONE",
        employee_role: object = "STANDARD",
    ) -> ToolResponse[NoticePeriodResult]:
        tool_name = "calculate_notice_period"
        request_id = self._request_id()
        try:
            payload = NoticePeriodInput.model_validate(
                {
                    "contract_type": contract_type,
                    "special_case": special_case,
                    "employee_role": employee_role,
                }
            )
        except ValidationError as error:
            return self._validation_error(tool_name, request_id, error)
        return self._execute(
            tool_name,
            request_id,
            {
                "contract_type": payload.contract_type.value,
                "special_case": payload.special_case.value,
                "employee_role": payload.employee_role.value,
            },
            lambda: self._service_provider().calculate_notice_period(payload),
        )

    def calculate_contract_duration(
        self, contract_type: object, start_date: object, end_date: object = None
    ) -> ToolResponse[ContractDurationResult]:
        tool_name = "calculate_contract_duration"
        request_id = self._request_id()
        try:
            payload = ContractDurationInput.model_validate(
                {"contract_type": contract_type, "start_date": start_date, "end_date": end_date}
            )
        except ValidationError as error:
            return self._validation_error(tool_name, request_id, error)
        return self._execute(
            tool_name,
            request_id,
            {
                "contract_type": payload.contract_type.value,
                "start_date": payload.start_date.isoformat(),
                "end_date": payload.end_date.isoformat() if payload.end_date else None,
            },
            lambda: self._service_provider().calculate_contract_duration(payload),
        )

    def _execute(
        self,
        tool_name: str,
        request_id: str,
        arguments: dict[str, Any],
        operation: Callable[[], DataT],
    ) -> ToolResponse[DataT]:
        started = time.perf_counter()
        try:
            data = operation()
            self._log(tool_name, request_id, arguments, "ok", data, started)
            return ToolResponse(
                ok=True, data=data, meta=ToolMeta(tool=tool_name, request_id=request_id)
            )
        except EndDateBeforeStartDateError:
            return self._expected_error(
                tool_name,
                request_id,
                arguments,
                started,
                "END_DATE_BEFORE_START_DATE",
                "Ngày kết thúc không được trước ngày bắt đầu.",
            )
        except InvalidDateRangeError:
            return self._expected_error(
                tool_name,
                request_id,
                arguments,
                started,
                "INVALID_DATE_RANGE",
                "Cần cung cấp ngày kết thúc để tính thời hạn hợp đồng.",
            )
        except InvalidInputCombinationError:
            return self._expected_error(
                tool_name,
                request_id,
                arguments,
                started,
                "INVALID_INPUT_COMBINATION",
                "Tổ hợp loại hợp đồng, trường hợp và vai trò không nằm trong phạm vi hỗ trợ.",
            )
        except RuleNotFoundError:
            return self._expected_error(
                tool_name,
                request_id,
                arguments,
                started,
                "RULE_NOT_FOUND",
                "Không tìm thấy quy tắc xác định phù hợp với dữ liệu đã xác thực.",
            )
        except Exception:
            self._logger.error(
                "mcp_legal_calculator_unexpected_error",
                tool_name=tool_name,
                request_id=request_id,
                exc_info=True,
            )
            return self._expected_error(
                tool_name,
                request_id,
                arguments,
                started,
                "INTERNAL_TOOL_ERROR",
                "Đã xảy ra lỗi nội bộ khi xử lý yêu cầu tính toán.",
            )

    def _validation_error(
        self, tool_name: str, request_id: str, error: ValidationError
    ) -> ToolResponse[Any]:
        fields = {str(item["loc"][0]) for item in error.errors() if item.get("loc")}
        if "contract_type" in fields:
            code, message = "INVALID_CONTRACT_TYPE", "Loại hợp đồng không hợp lệ."
        elif "special_case" in fields:
            code, message = "INVALID_SPECIAL_CASE", "Trường hợp đặc biệt không hợp lệ."
        elif "employee_role" in fields:
            code, message = "INVALID_EMPLOYEE_ROLE", "Vai trò người lao động không hợp lệ."
        elif fields.intersection({"start_date", "end_date"}):
            code, message = (
                "INVALID_DATE_FORMAT",
                "Ngày phải là ISO calendar date hợp lệ YYYY-MM-DD.",
            )
        else:
            code, message = "INVALID_INPUT_COMBINATION", "Dữ liệu đầu vào không hợp lệ."
        self._log(tool_name, request_id, {}, "error", None, None, code)
        return self._error(tool_name, request_id, code, message)

    def _expected_error(
        self,
        tool_name: str,
        request_id: str,
        arguments: dict[str, Any],
        started: float,
        code: str,
        message: str,
    ) -> ToolResponse[Any]:
        self._log(tool_name, request_id, arguments, "error", None, started, code)
        return self._error(tool_name, request_id, code, message)

    def _error(self, tool_name: str, request_id: str, code: str, message: str) -> ToolResponse[Any]:
        return ToolResponse(
            ok=False,
            error=ToolError(code=code, message=message, retryable=False),
            meta=ToolMeta(tool=tool_name, request_id=request_id),
        )

    def _log(
        self,
        tool_name: str,
        request_id: str,
        arguments: dict[str, Any],
        status: str,
        data: BaseModel | None,
        started: float | None,
        error_code: str | None = None,
    ) -> None:
        self._logger.info(
            "mcp_legal_calculator_tool_completed",
            tool_name=tool_name,
            request_id=request_id,
            arguments=arguments,
            status=status,
            rule_id=data.rule_id
            if isinstance(data, (NoticePeriodResult, ContractDurationResult))
            else None,
            support_status=data.support_status.value
            if isinstance(data, NoticePeriodResult)
            else None,
            latency_ms=round((time.perf_counter() - started) * 1000, 3) if started else None,
            error_code=error_code,
        )

    @staticmethod
    def _request_id() -> str:
        return str(uuid.uuid4())
