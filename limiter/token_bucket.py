import asyncio
import time
from typing import Dict, Optional

from config import settings
from logging_config import get_logger

logger = get_logger(__name__)


class TokenBucketLimiter:
    def __init__(self, rate: float, capacity: Optional[float] = None):
        self._rate = rate
        self._capacity = capacity if capacity is not None else rate
        self._tokens = self._capacity
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    def _refill(self):
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
        self._last_refill = now

    async def acquire(self, tokens: float = 1.0) -> None:
        async with self._lock:
            self._refill()
            if self._tokens >= tokens:
                self._tokens -= tokens
                return
            deficit = tokens - self._tokens
            wait_time = deficit / self._rate
            self._tokens = 0.0
            self._last_refill = time.monotonic()
        await asyncio.sleep(wait_time)
        async with self._lock:
            self._refill()
            self._tokens = max(0.0, self._tokens - tokens)

    async def try_acquire(self, tokens: float = 1.0) -> bool:
        async with self._lock:
            self._refill()
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            return False


_limiters: Dict[str, TokenBucketLimiter] = {}


def get_limiter(source: str) -> TokenBucketLimiter:
    if source not in _limiters:
        if source == "arxiv":
            _limiters[source] = TokenBucketLimiter(
                rate=settings.arxiv_rate_per_sec,
                capacity=settings.arxiv_rate_per_sec,
            )
        elif source == "crossref":
            _limiters[source] = TokenBucketLimiter(
                rate=settings.crossref_rate_per_sec,
                capacity=settings.crossref_rate_per_sec * 2,
            )
        elif source == "semantic_scholar":
            _limiters[source] = TokenBucketLimiter(
                rate=settings.semantic_rate_per_min / 60.0,
                capacity=settings.semantic_rate_per_min,
            )
        else:
            _limiters[source] = TokenBucketLimiter(rate=10.0, capacity=20.0)
    return _limiters[source]
