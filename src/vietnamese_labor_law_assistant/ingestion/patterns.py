"""Anchored parsing helpers for Vietnamese legal-document headings."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .normalize import normalize_legal_text


@dataclass(frozen=True)
class HeadingMatch:
    """A parsed structural heading and its optional trailing title."""

    number: str
    title: str | None


@dataclass(frozen=True)
class PointMatch:
    """A parsed point label and the text beginning at that point."""

    label: str
    text: str


CHAPTER_RE = re.compile(
    r"^chương\s+(?P<number>[ivxlcdm]+|\d+)(?:\s*[.:\-]\s*|\s+)?(?P<title>.*)$",
    re.IGNORECASE,
)
SECTION_RE = re.compile(
    r"^mục\s+(?P<number>[ivxlcdm]+|\d+)(?:\s*[.:\-]\s*|\s+)?(?P<title>.*)$",
    re.IGNORECASE,
)
ARTICLE_RE = re.compile(r"^điều\s+(?P<number>[1-9]\d*)(?P<suffix>.*)$", re.IGNORECASE)
CLAUSE_RE = re.compile(r"^(?P<number>[1-9]\d{0,1})\s*[.:]\s+(?P<text>\S.*)$")
POINT_RE = re.compile(r"^(?P<label>[a-zđ])\s*[).]\s+(?P<text>\S.*)$", re.IGNORECASE)


def _heading(match: re.Match[str] | None) -> HeadingMatch | None:
    if match is None:
        return None
    title = match.group("title").strip() or None
    return HeadingMatch(number=match.group("number").upper(), title=title)


def parse_chapter_heading(text: str) -> HeadingMatch | None:
    """Parse an anchored ``Chương`` heading."""
    return _heading(CHAPTER_RE.fullmatch(normalize_legal_text(text)))


def parse_section_heading(text: str) -> HeadingMatch | None:
    """Parse an anchored ``Mục`` heading."""
    return _heading(SECTION_RE.fullmatch(normalize_legal_text(text)))


def parse_article_heading(text: str) -> HeadingMatch | None:
    """Parse a direct article title, excluding quoted or embedded citations."""
    match = ARTICLE_RE.fullmatch(normalize_legal_text(text))
    if match is None:
        return None
    suffix = match.group("suffix").strip()
    if not suffix:
        return HeadingMatch(number=match.group("number"), title=None)
    if suffix[0] in ".:-":
        title = suffix[1:].strip() or None
        return HeadingMatch(number=match.group("number"), title=title)
    # Direct headings without punctuation normally begin their title with an uppercase letter.
    # This rejects citations such as "Điều 35 của Bộ luật".
    if suffix[0].isupper():
        return HeadingMatch(number=match.group("number"), title=suffix)
    return None


def parse_clause_heading(text: str) -> HeadingMatch | None:
    """Parse an integer clause label; values with three digits avoid matching years."""
    match = CLAUSE_RE.fullmatch(normalize_legal_text(text))
    if match is None:
        return None
    return HeadingMatch(number=match.group("number"), title=match.group("text"))


def parse_point_heading(text: str) -> PointMatch | None:
    """Parse an anchored Vietnamese point label, including ``đ``."""
    match = POINT_RE.fullmatch(normalize_legal_text(text))
    if match is None:
        return None
    return PointMatch(label=match.group("label").lower(), text=match.group("text"))
