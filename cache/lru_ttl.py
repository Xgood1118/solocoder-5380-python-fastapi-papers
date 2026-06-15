import hashlib
import json
import time
from collections import OrderedDict
from typing import Any, Optional, Tuple, Dict, List

from config import settings
from logging_config import get_logger

logger = get_logger(__name__)


class LRUCache:
    def __init__(self, capacity: Optional[int] = None, ttl_seconds: Optional[int] = None):
        self.capacity = capacity or settings.cache_max_entries
        self.ttl_seconds = ttl_seconds or settings.cache_ttl_seconds
        self._cache: "OrderedDict[str, Tuple[float, Any]]" = OrderedDict()
        self._hits = 0
        self._misses = 0

    def _make_key(self, key_tuple: Tuple) -> str:
        raw = json.dumps(key_tuple, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _is_expired(self, ts: float) -> bool:
        return (time.time() - ts) > self.ttl_seconds

    def _evict_expired(self):
        expired_keys: List[str] = []
        for k, (ts, _) in self._cache.items():
            if self._is_expired(ts):
                expired_keys.append(k)
            else:
                break
        for k in expired_keys:
            del self._cache[k]

    def get(self, key_tuple: Tuple) -> Optional[Any]:
        key = self._make_key(key_tuple)
        self._evict_expired()
        if key in self._cache:
            ts, value = self._cache[key]
            if self._is_expired(ts):
                del self._cache[key]
                self._misses += 1
                logger.debug("cache_miss_expired", key=key[:16])
                return None
            self._cache.move_to_end(key)
            self._hits += 1
            logger.debug("cache_hit", key=key[:16])
            return value
        self._misses += 1
        logger.debug("cache_miss", key=key[:16])
        return None

    def set(self, key_tuple: Tuple, value: Any) -> None:
        key = self._make_key(key_tuple)
        self._cache[key] = (time.time(), value)
        self._cache.move_to_end(key)
        while len(self._cache) > self.capacity:
            self._cache.popitem(last=False)
        logger.debug("cache_set", key=key[:16], size=len(self._cache))

    def clear(self) -> None:
        self._cache.clear()
        self._hits = 0
        self._misses = 0

    @property
    def stats(self) -> Dict[str, int]:
        return {
            "size": len(self._cache),
            "capacity": self.capacity,
            "hits": self._hits,
            "misses": self._misses,
        }


_search_cache: Optional[LRUCache] = None
_citation_cache: Optional[LRUCache] = None


def get_search_cache() -> LRUCache:
    global _search_cache
    if _search_cache is None:
        _search_cache = LRUCache()
    return _search_cache


def get_citation_cache() -> LRUCache:
    global _citation_cache
    if _citation_cache is None:
        _citation_cache = LRUCache()
    return _citation_cache
