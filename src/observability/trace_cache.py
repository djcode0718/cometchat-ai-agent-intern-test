"""Thread-safe bounded in-memory cache with Time-To-Live (TTL) and LRU eviction."""

import threading
import time
from collections import OrderedDict
from typing import Any, Dict, Optional


class BoundedTTLCache:
    """Thread-safe bounded in-memory cache with TTL expiration and LRU capacity eviction."""

    def __init__(self, maxsize: int = 1000, ttl_seconds: float = 3600.0) -> None:
        self.maxsize = max(1, maxsize)
        self.ttl_seconds = float(ttl_seconds)
        self._data: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._lock = threading.RLock()

    def set(self, key: str, value: Any) -> None:
        """Insert or update a key with the current timestamp, evicting expired or LRU items."""
        with self._lock:
            now = time.time()
            self._prune_expired_locked(now)

            if key in self._data:
                self._data.move_to_end(key)
            self._data[key] = (now, value)

            # Evict oldest if exceeding capacity
            while len(self._data) > self.maxsize:
                self._data.popitem(last=False)

    def get(self, key: str) -> Optional[Any]:
        """Retrieve value if key exists and has not expired."""
        with self._lock:
            if key not in self._data:
                return None
            ts, val = self._data[key]
            if time.time() - ts > self.ttl_seconds:
                del self._data[key]
                return None
            self._data.move_to_end(key)
            return val

    def delete(self, key: str) -> bool:
        """Remove a key from cache."""
        with self._lock:
            if key in self._data:
                del self._data[key]
                return True
            return False

    def clear(self) -> None:
        """Clear all entries."""
        with self._lock:
            self._data.clear()

    def __len__(self) -> int:
        with self._lock:
            self._prune_expired_locked(time.time())
            return len(self._data)

    def _prune_expired_locked(self, now: float) -> None:
        """Remove entries older than ttl_seconds from the front."""
        expired_keys = [
            k for k, (ts, _) in self._data.items() if now - ts > self.ttl_seconds
        ]
        for k in expired_keys:
            del self._data[k]
