"""Typed, Unicode-tolerant parser for Vietnamese legal references."""

from __future__ import annotations

import re
import unicodedata

from pydantic import BaseModel, ConfigDict, Field

from .models import LegalReference

_REFERENCE = re.compile(
    r"(?:(?:điểm)\s*(?P<point>[a-zđ])\s*)?"
    r"(?:(?:khoản)\s*(?P<clause>\d+)\s*)?"
    r"(?:điều)\s*(?P<article>\d+)",
    re.IGNORECASE,
)
_MALFORMED = re.compile(
    r"\b(?:điều|khoản)\s+(?:một|hai|ba|bốn|năm|sáu|bảy|tám|chín|[?_-])\b"
    r"|\bđiểm\s+(?:\d+|[?_-])\b",
    re.IGNORECASE,
)


class CitationParseResult(BaseModel):
    """Parser diagnostic consumed directly by the verification service."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    references: list[LegalReference] = Field(default_factory=list)
    malformed: bool = False
    duplicate_count: int = Field(default=0, ge=0)


def normalize_citation_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).casefold().split())


def extract_numeric_tokens(value: str) -> set[str]:
    """Return literal numeric tokens used by deterministic grounding checks."""
    return set(re.findall(r"\d+", value))


def parse_citations(value: str) -> CitationParseResult:
    normalized = normalize_citation_text(value)
    references: list[LegalReference] = []
    seen: set[tuple[int, int | None, str | None]] = set()
    duplicates = 0
    spans: list[tuple[int, int]] = []
    for match in _REFERENCE.finditer(normalized):
        spans.append(match.span())
        reference = LegalReference(
            article=int(match.group("article")),
            clause=int(match.group("clause")) if match.group("clause") else None,
            point=match.group("point").lower() if match.group("point") else None,
        )
        key = (reference.article, reference.clause, reference.point)
        if key in seen:
            duplicates += 1
        else:
            seen.add(key)
            references.append(reference)
    remainder = normalized
    for start, end in reversed(spans):
        remainder = remainder[:start] + (" " * (end - start)) + remainder[end:]
    return CitationParseResult(
        references=references,
        malformed=bool(_MALFORMED.search(remainder)),
        duplicate_count=duplicates,
    )


def parse_legal_citation(value: str) -> LegalReference | None:
    parsed = parse_citations(value)
    return parsed.references[0] if parsed.references else None


def extract_legal_citations(value: str) -> list[LegalReference]:
    return parse_citations(value).references
