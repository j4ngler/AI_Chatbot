"""Giới hạn tần suất in-memory (theo khóa, ví dụ IP) — phù hợp demo/single instance."""
from __future__ import annotations

import threading
import time


class MemoryRateLimiter:
    def __init__(self) -> None:
        self._buckets: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, max_requests: int, window_sec: float) -> bool:
        if max_requests <= 0:
            return True
        now = time.time()
        with self._lock:
            arr = [t for t in self._buckets.get(key, []) if now - t < window_sec]
            if len(arr) >= max_requests:
                self._buckets[key] = arr
                return False
            arr.append(now)
            self._buckets[key] = arr
            return True
