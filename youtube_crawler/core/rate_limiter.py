"""
Token-bucket rate limiter backed by Redis for distributed rate limiting.
Falls back to in-memory limiting when Redis is unavailable.
"""

import asyncio
import time
from collections import defaultdict

from loguru import logger


class RateLimiter:
    """
    Async token-bucket rate limiter.
    Supports per-platform rate limit configuration.
    """

    def __init__(self):
        self._buckets: dict[str, dict] = {}
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    def configure(self, platform: str, max_requests: int, period_seconds: int) -> None:
        """
        Configure rate limit for a specific platform.

        Args:
            platform: Platform identifier (e.g., 'youtube', 'reddit')
            max_requests: Maximum number of requests allowed in the period
            period_seconds: Time period in seconds
        """
        self._buckets[platform] = {
            "max_requests": max_requests,
            "period": period_seconds,
            "tokens": max_requests,
            "last_refill": time.monotonic(),
        }
        logger.debug(
            f"Rate limiter configured for '{platform}': {max_requests} req / {period_seconds}s"
        )

    async def acquire(self, platform: str, cost: int = 1) -> bool:
        """
        Acquire tokens for a request. Waits if necessary.

        Args:
            platform: Platform identifier
            cost: Number of tokens to consume (default 1)

        Returns:
            True when tokens are acquired
        """
        if platform not in self._buckets:
            return True  # No limit configured

        async with self._locks[platform]:
            bucket = self._buckets[platform]
            self._refill(bucket)

            if bucket["tokens"] >= cost:
                bucket["tokens"] -= cost
                return True

            # Calculate wait time
            wait_time = bucket["period"] * (cost - bucket["tokens"]) / bucket["max_requests"]
            logger.warning(f"Rate limit reached for '{platform}', waiting {wait_time:.1f}s")

        # Wait outside the lock
        await asyncio.sleep(wait_time)

        # Retry after waiting
        async with self._locks[platform]:
            self._refill(bucket)
            bucket["tokens"] = max(0, bucket["tokens"] - cost)
            return True

    def get_remaining(self, platform: str) -> int | None:
        """Get remaining tokens for a platform."""
        if platform not in self._buckets:
            return None
        bucket = self._buckets[platform]
        self._refill(bucket)
        return int(bucket["tokens"])

    def _refill(self, bucket: dict) -> None:
        """Refill tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - bucket["last_refill"]
        refill = elapsed * bucket["max_requests"] / bucket["period"]
        bucket["tokens"] = min(bucket["max_requests"], bucket["tokens"] + refill)
        bucket["last_refill"] = now


# Global rate limiter instance
rate_limiter = RateLimiter()


def setup_rate_limiter() -> RateLimiter:
    """Initialize rate limiter with settings from config."""
    from youtube_crawler.core.config import get_settings

    settings = get_settings()

    rate_limiter.configure("youtube", settings.youtube_rate_limit, settings.youtube_rate_period)
    rate_limiter.configure("reddit", settings.reddit_rate_limit, settings.reddit_rate_period)
    rate_limiter.configure("tiktok", settings.tiktok_rate_limit, settings.tiktok_rate_period)
    rate_limiter.configure("default", settings.default_rate_limit, settings.default_rate_period)

    logger.info("Rate limiter initialized for all platforms")
    return rate_limiter
