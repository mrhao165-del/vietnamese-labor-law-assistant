"""Pydantic domain contracts for deterministic legal calculations."""

from __future__ import annotations

import re
from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .enums import (
    ContractDurationType,
    ContractLimitStatus,
    ContractType,
    DurationUnit,
    EmployeeRole,
    NoticeSpecialCase,
    RuleSupportStatus,
)

ISO_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DISCLAIMER = (
    "Kết quả chỉ có tính chất hỗ trợ tra cứu và không thay thế tư vấn pháp lý chuyên nghiệp."
)


class LegalBasis(BaseModel):
    """Allowlisted provenance for a rule selected from the local source snapshot."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    document_id: str
    document_name: str
    article: int = Field(gt=0)
    clause: int = Field(gt=0)
    point: str | None = None
    source_chunk_id: str
    source_label: str
    source_snapshot_date: str


class NoticePeriodInput(BaseModel):
    """Closed inputs for employee unilateral-termination notice calculation."""

    model_config = ConfigDict(extra="forbid")

    contract_type: ContractType
    special_case: NoticeSpecialCase = NoticeSpecialCase.NONE
    employee_role: EmployeeRole = EmployeeRole.STANDARD


class CalendarPeriod(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    years: int = Field(ge=0)
    months: int = Field(ge=0, le=11)
    days: int = Field(ge=0)


class ContractDurationInput(BaseModel):
    """Strict ISO-calendar-date inputs; datetime and locale strings are not accepted."""

    model_config = ConfigDict(extra="forbid")

    contract_type: ContractDurationType
    start_date: date
    end_date: date | None = None

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def require_iso_calendar_date(cls, value: object) -> object:
        if value is None:
            return value
        if not isinstance(value, str) or not ISO_DATE_PATTERN.fullmatch(value):
            raise ValueError("date must use YYYY-MM-DD")
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("date must be a valid ISO calendar date") from exc


class NoticePeriodResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scope: str = "employee_unilateral_termination"
    contract_type: ContractType
    special_case: NoticeSpecialCase
    employee_role: EmployeeRole
    notice_required: bool
    notice_days: int | None = Field(default=None, ge=0)
    unit: DurationUnit
    support_status: RuleSupportStatus
    rule_id: str
    legal_basis: tuple[LegalBasis, ...]
    assumptions: tuple[str, ...] = ()
    warning: str = DISCLAIMER


class ContractDurationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_type: ContractDurationType
    start_date: date
    end_date: date
    elapsed_days: int = Field(ge=0)
    calendar_period: CalendarPeriod
    maximum_allowed_months: int | None = Field(default=None, ge=0)
    maximum_allowed_end_date: date | None = None
    limit_status: ContractLimitStatus
    rule_id: str
    calculation_convention: str
    legal_basis: tuple[LegalBasis, ...]
    assumptions: tuple[str, ...] = ()
    warning: str = DISCLAIMER
