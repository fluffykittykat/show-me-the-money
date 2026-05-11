"""Token bucket rate limiter for API calls."""

import asyncio
import time
from contextlib import asynccontextmanager


class SmartRateLimiter:
    """Token bucket rate limiter for API calls.

    Each API has its own bucket with configurable calls-per-hour and burst limits.
    Usage::

        limiter = SmartRateLimiter()
        async with limiter.acquire("congress_gov"):
            response = await client.get(url)
    """

    # FEC: documented limit is 1000/hour with API key. Leave headroom for ad-hoc
    # /refresh/{slug} calls that fire alongside the scheduler.
    # senate_efd: site has no published limit but is fragile — keep low + small burst.
    LIMITS = {
        "congress_gov": {"calls_per_hour": 5000, "burst": 10},
        "fec": {"calls_per_hour": 900, "burst": 5},
        "senate_efd": {"calls_per_hour": 300, "burst": 2},
        "lda": {"calls_per_hour": 500, "burst": 3},
    }

    def __init__(self):
        self._semaphores: dict[str, asyncio.Semaphore] = {}
        self._tokens: dict[str, float] = {}
        self._last_refill: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._call_counts: dict[str, int] = {}
        self._total_wait_time: dict[str, float] = {}

        for api_name, limits in self.LIMITS.items():
            burst = limits["burst"]
            self._semaphores[api_name] = asyncio.Semaphore(burst)
            self._tokens[api_name] = float(burst)
            self._last_refill[api_name] = time.monotonic()
            self._locks[api_name] = asyncio.Lock()
            self._call_counts[api_name] = 0
            self._total_wait_time[api_name] = 0.0

    def _refill(self, api_name: str) -> None:
        """Refill tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self._last_refill[api_name]
        limits = self.LIMITS[api_name]
        rate_per_second = limits["calls_per_hour"] / 3600.0
        new_tokens = elapsed * rate_per_second
        if new_tokens > 0:
            self._tokens[api_name] = min(
                self._tokens[api_name] + new_tokens,
                float(limits["burst"]),
            )
            self._last_refill[api_name] = now

    @asynccontextmanager
    async def acquire(self, api_name: str):
        """Acquire a rate-limit token for the given API.

        Blocks until a token is available, then yields control.
        """
        if api_name not in self.LIMITS:
            raise ValueError(
                f"Unknown API: {api_name}. Known APIs: {list(self.LIMITS.keys())}"
            )

        wait_start = time.monotonic()

        async with self._locks[api_name]:
            self._refill(api_name)

            while self._tokens[api_name] < 1.0:
                # Calculate how long to wait for one token
                limits = self.LIMITS[api_name]
                rate_per_second = limits["calls_per_hour"] / 3600.0
                wait_time = (1.0 - self._tokens[api_name]) / rate_per_second
                await asyncio.sleep(wait_time)
                self._refill(api_name)

            self._tokens[api_name] -= 1.0
            self._call_counts[api_name] += 1

        wait_elapsed = time.monotonic() - wait_start
        self._total_wait_time[api_name] += wait_elapsed

        try:
            yield
        finally:
            pass

    def stats(self) -> dict:
        """Return call counts and wait times for all APIs."""
        result = {}
        for api_name in self.LIMITS:
            result[api_name] = {
                "calls_made": self._call_counts[api_name],
                "total_wait_seconds": round(self._total_wait_time[api_name], 2),
                "tokens_remaining": round(self._tokens[api_name], 2),
            }
        return result

    def reset(self) -> None:
        """Reset all counters and refill tokens."""
        for api_name, limits in self.LIMITS.items():
            burst = limits["burst"]
            self._tokens[api_name] = float(burst)
            self._last_refill[api_name] = time.monotonic()
            self._call_counts[api_name] = 0
            self._total_wait_time[api_name] = 0.0


_shared: SmartRateLimiter | None = None


def get_rate_limiter() -> SmartRateLimiter:
    """Process-wide shared rate limiter. All ingestion clients should use this."""
    global _shared
    if _shared is None:
        _shared = SmartRateLimiter()
    return _shared
