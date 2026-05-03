"""
Redis caching and queue operations.
Provides caching for API responses, task status, and rate limit state.
"""

from typing import Any, Optional

import redis.asyncio as redis
from loguru import logger

from app.core.config import get_settings


class RedisStorage:
    """Redis cache and queue operations."""

    def __init__(self):
        self._client: Optional[redis.Redis] = None

    async def connect(self) -> None:
        """Initialize Redis connection."""
        settings = get_settings()
        self._client = redis.from_url(
            settings.redis_url,
            decode_responses=True,
            max_connections=20,
        )
        try:
            await self._client.ping()
            logger.info("Redis connected successfully")
        except redis.ConnectionError as e:
            logger.error(f"Redis connection failed: {e}")
            self._client = None

    async def close(self) -> None:
        """Close Redis connection."""
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> Optional[redis.Redis]:
        return self._client

    @property
    def is_connected(self) -> bool:
        return self._client is not None

    # ---- Cache Operations ----

    async def cache_get(self, key: str) -> Optional[str]:
        """Get a cached value."""
        if not self._client:
            return None
        try:
            return await self._client.get(f"cache:{key}")
        except redis.RedisError as e:
            logger.warning(f"Redis cache get error: {e}")
            return None

    async def cache_set(
        self, key: str, value: str, ttl: Optional[int] = None
    ) -> bool:
        """Set a cached value with optional TTL."""
        if not self._client:
            return False

        settings = get_settings()
        ttl = ttl or settings.redis_cache_ttl

        try:
            await self._client.setex(f"cache:{key}", ttl, value)
            return True
        except redis.RedisError as e:
            logger.warning(f"Redis cache set error: {e}")
            return False

    async def cache_delete(self, key: str) -> bool:
        """Delete a cached value."""
        if not self._client:
            return False
        try:
            await self._client.delete(f"cache:{key}")
            return True
        except redis.RedisError:
            return False

    async def cache_json_get(self, key: str) -> Optional[dict]:
        """Get a JSON-cached value."""
        import json
        value = await self.cache_get(key)
        if value:
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                pass
        return None

    async def cache_json_set(
        self, key: str, data: dict, ttl: Optional[int] = None
    ) -> bool:
        """Cache a value as JSON."""
        import json
        return await self.cache_set(key, json.dumps(data, default=str), ttl=ttl)

    # ---- Quota Tracking ----

    async def get_quota_used(self, platform: str, date_key: str) -> int:
        """Get quota used for a platform today."""
        if not self._client:
            return 0
        try:
            val = await self._client.get(f"quota:{platform}:{date_key}")
            return int(val) if val else 0
        except redis.RedisError:
            return 0

    async def increment_quota(
        self, platform: str, date_key: str, amount: int = 1
    ) -> int:
        """Increment quota counter for a platform."""
        if not self._client:
            return 0
        try:
            key = f"quota:{platform}:{date_key}"
            new_val = await self._client.incrby(key, amount)
            # Auto-expire at end of day (25 hours safety margin)
            await self._client.expire(key, 90000)
            return new_val
        except redis.RedisError:
            return 0

    # ---- Task Status ----

    async def set_task_progress(
        self, task_id: int, progress: dict
    ) -> None:
        """Store real-time task progress."""
        if not self._client:
            return
        try:
            import json
            await self._client.setex(
                f"task_progress:{task_id}",
                3600,  # 1 hour TTL
                json.dumps(progress, default=str),
            )
        except redis.RedisError:
            pass

    async def get_task_progress(self, task_id: int) -> Optional[dict]:
        """Get real-time task progress."""
        return await self.cache_json_get(f"task_progress:{task_id}")


# Global Redis storage instance
redis_storage = RedisStorage()
