"""Vietnamese-preserving lexical normalisation for BM25."""

from __future__ import annotations

import re
import unicodedata

NORMALIZATION_VERSION = "v1"


def normalize_lexical_text(text: str, lowercase: bool = True) -> str:
    value = unicodedata.normalize("NFC", text).replace("\u00a0", " ")
    value = re.sub(r"[\u200b-\u200d\ufeff]", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value.lower() if lowercase else value
