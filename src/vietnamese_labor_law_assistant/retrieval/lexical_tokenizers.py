"""Corpus/query-identical Vietnamese lexical tokenizers."""

from __future__ import annotations

from typing import Protocol, cast

from underthesea import word_tokenize

from .lexical_normalization import normalize_lexical_text


class LexicalTokenizer(Protocol):
    name: str
    version: str

    def tokenize(self, text: str) -> list[str]: ...


class WhitespaceTokenizer:
    name = "whitespace"
    version = "v1"

    def tokenize(self, text: str) -> list[str]:
        return normalize_lexical_text(text).split()


class UndertheseaTokenizer:
    name = "underthesea"
    version = "9.5.0"

    def tokenize(self, text: str) -> list[str]:
        value = word_tokenize(normalize_lexical_text(text), format="text")
        return cast(list[str], value.split() if isinstance(value, str) else list(value))


def get_lexical_tokenizer(name: str) -> LexicalTokenizer:
    if name == "whitespace":
        return WhitespaceTokenizer()
    if name == "underthesea":
        return UndertheseaTokenizer()
    raise ValueError(f"Unknown lexical tokenizer: {name}")
