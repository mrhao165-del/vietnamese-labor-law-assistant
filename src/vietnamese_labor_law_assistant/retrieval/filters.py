"""One metadata-filter predicate shared by dense, sparse, and hybrid retrieval."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .models import LegalSearchFilters


def matches_filters(value: Mapping[str, Any] | Any, filters: LegalSearchFilters | None) -> bool:
    """Return true only when every supplied filter matches a real chunk field."""
    if filters is None:
        return True
    data = value if isinstance(value, Mapping) else value.model_dump(mode="json")
    for field, expected in filters.as_dict().items():
        actual = data.get(field)
        if field == "point_label":
            points = {str(item).lower() for item in data.get("point_labels", [])}
            if actual is not None:
                points.add(str(actual).lower())
            if str(expected).lower() not in points:
                return False
        elif str(actual) != str(expected):
            return False
    return True
