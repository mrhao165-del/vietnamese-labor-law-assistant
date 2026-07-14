"""Conservative text normalization that preserves legal source wording."""

from __future__ import annotations

import re
import unicodedata

ZERO_WIDTH_RE = re.compile(r"[\u200b\u200c\u200d\ufeff]")
HORIZONTAL_SPACE_RE = re.compile(r"[^\S\r\n]+")
BLANK_LINES_RE = re.compile(r"\n[ \t]*\n[ \t\n]*")


def normalize_unicode(text: str) -> str:
    """Return NFC text with non-breaking and zero-width characters handled."""
    return ZERO_WIDTH_RE.sub("", unicodedata.normalize("NFC", text).replace("\u00a0", " "))


def normalize_whitespace(text: str) -> str:
    """Normalize line endings and horizontal whitespace without collapsing meaningful lines."""
    value = text.replace("\r\n", "\n").replace("\r", "\n")
    value = "\n".join(HORIZONTAL_SPACE_RE.sub(" ", line).strip() for line in value.split("\n"))
    return BLANK_LINES_RE.sub("\n\n", value).strip()


def normalize_legal_text(text: str) -> str:
    """Normalize source text while retaining Vietnamese diacritics and legal punctuation."""
    return normalize_whitespace(normalize_unicode(text))


def normalize_heading_text(text: str) -> str:
    """Create a comparison-only form for structural heading matching."""
    return normalize_legal_text(text).casefold()


def is_probable_header_or_footer(text: str) -> bool:
    """Recognize only very strong pagination signals; callers must not silently discard text."""
    value = normalize_legal_text(text)
    return bool(re.fullmatch(r"(?:trang\s*)?\d+(?:\s*/\s*\d+)?", value, flags=re.IGNORECASE))
