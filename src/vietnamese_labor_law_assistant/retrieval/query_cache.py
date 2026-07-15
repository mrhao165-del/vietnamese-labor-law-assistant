"""Thread-safe bounded LRU cache for query embeddings only."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Sequence
from threading import RLock


class QueryEmbeddingCache:
    """Small process-local LRU cache; it never persists query text or vectors."""

    def __init__(self, enabled: bool, max_size: int) -> None:
        self.enabled = enabled
        self.max_size = max_size
        self._values: OrderedDict[str, tuple[float, ...]] = OrderedDict()
        self._lock = RLock()
        self.eviction_count = 0

    def get(self, key: str) -> list[float] | None:
        if not self.enabled or self.max_size == 0:
            return None
        with self._lock:
            value = self._values.get(key)
            if value is None:
                return None
            self._values.move_to_end(key)
            return list(value)

    def put(self, key: str, vector: Sequence[float]) -> None:
        if not self.enabled or self.max_size == 0:
            return
        with self._lock:
            self._values[key] = tuple(float(item) for item in vector)
            self._values.move_to_end(key)
            while len(self._values) > self.max_size:
                self._values.popitem(last=False)
                self.eviction_count += 1

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._values)

    def clear(self) -> None:
        with self._lock:
            self._values.clear()
            self.eviction_count = 0
