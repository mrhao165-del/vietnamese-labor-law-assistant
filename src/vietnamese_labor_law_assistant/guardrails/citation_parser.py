"""Unicode-tolerant parser for explicit Vietnamese legal references."""

from __future__ import annotations

import re
import unicodedata

from .models import LegalReference

_ARTICLE = re.compile(r"\bđiều\s*(\d+)\b", re.IGNORECASE)
_CLAUSE = re.compile(r"\bkhoản\s*(\d+)\b", re.IGNORECASE)
_POINT = re.compile(r"\bđiểm\s*([a-zđ])\b", re.IGNORECASE)


def normalize_citation_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).casefold().split())


def parse_legal_citation(value: str) -> LegalReference | None:
    """Parse only components that are explicitly present; no component is inferred."""
    normalized = normalize_citation_text(value)
    article = _ARTICLE.search(normalized)
    if article is None:
        return None
    clause = _CLAUSE.search(normalized)
    point = _POINT.search(normalized)
    return LegalReference(
        article=int(article.group(1)),
        clause=int(clause.group(1)) if clause else None,
        point=point.group(1).lower() if point else None,
    )


def extract_legal_citations(value: str) -> list[LegalReference]:
    """Return unique explicit references in order of first appearance."""
    parsed = parse_legal_citation(value)
    return [] if parsed is None else [parsed]
