"""Provider-neutral port for extracting a typed case-intake result."""

from __future__ import annotations

from typing import Protocol

from .models import CaseIntakeInput, CaseIntakeResult


class CaseIntakeExtractor(Protocol):
    """Extract facts and preliminary issues from one typed raw case input."""

    async def extract(self, case_input: CaseIntakeInput) -> CaseIntakeResult: ...
