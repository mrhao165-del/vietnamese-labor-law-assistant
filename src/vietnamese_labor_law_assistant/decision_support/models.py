"""Typed, source-grounded contracts for Week-2 case intake."""

from __future__ import annotations

import re
from typing import TypeAlias

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .enums import AssertionMode, SourceType, VerificationStatus
from .issues import IssueCode

NormalizedValue: TypeAlias = str | int | float | bool
_EXACT_ISO_DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")


class CaseIntakeInput(BaseModel):
    """One raw user-message source supplied to a future case-intake extractor."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_text: str = Field(min_length=1, max_length=16000)
    source_ref: str = Field(pattern=r"^user_message:[A-Za-z0-9_-]{1,80}$")
    source_type: SourceType = SourceType.USER_MESSAGE

    @field_validator("source_text")
    @classmethod
    def source_text_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("source_text must not be blank")
        return value


class SourceSpan(BaseModel):
    """A literal half-open Python code-point span in its referenced source."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    start_offset: int = Field(ge=0)
    end_offset: int = Field(gt=0)
    text: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def validate_offsets_match_text(self) -> SourceSpan:
        if self.end_offset - self.start_offset != len(self.text):
            raise ValueError("source span offsets must exactly bound its literal text")
        return self


class CaseFact(BaseModel):
    """A source-grounded assertion whose verification remains independent from extraction."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    fact_id: str = Field(pattern=r"^CF-[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")
    fact_key: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,79}$")
    fact_type: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,79}$")
    raw_value: str = Field(min_length=1, max_length=2000)
    normalized_value: NormalizedValue
    assertion_mode: AssertionMode
    verification_status: VerificationStatus
    source_type: SourceType
    source_ref: str = Field(pattern=r"^user_message:[A-Za-z0-9_-]{1,80}$")
    source_span: SourceSpan

    @field_validator("raw_value")
    @classmethod
    def raw_value_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("raw_value must not be blank")
        return value

    @model_validator(mode="after")
    def validate_source_grounding(self) -> CaseFact:
        if self.raw_value not in self.source_span.text:
            raise ValueError("raw_value must occur in the cited source span")
        if self.fact_type == "TEMPORAL_EXPRESSION" and self.normalized_value != self.raw_value:
            raise ValueError("temporal expressions must preserve their non-exact raw value")
        if (
            isinstance(self.normalized_value, str)
            and _EXACT_ISO_DATE_PATTERN.fullmatch(self.normalized_value)
            and self.normalized_value not in self.raw_value
        ):
            raise ValueError("exact normalized dates must occur literally in the raw value")
        return self


class CandidateIssue(BaseModel):
    """One allowlisted issue that intake may identify as preliminarily relevant."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    issue_code: IssueCode


class CaseIntakeResult(BaseModel):
    """Week-2 extracted facts and preliminary issues, without downstream analysis state."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    facts: list[CaseFact] = Field(default_factory=list, max_length=50)
    candidate_issues: list[CandidateIssue] = Field(default_factory=list, max_length=2)

    @model_validator(mode="after")
    def validate_unique_contract_identifiers(self) -> CaseIntakeResult:
        fact_ids = [fact.fact_id for fact in self.facts]
        if len(fact_ids) != len(set(fact_ids)):
            raise ValueError("fact IDs must be unique")
        issue_codes = [issue.issue_code for issue in self.candidate_issues]
        if len(issue_codes) != len(set(issue_codes)):
            raise ValueError("candidate issue codes must be unique")
        return self
