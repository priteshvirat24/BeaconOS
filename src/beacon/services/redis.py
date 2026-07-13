"""Beacon Command — Redis Client."""

from __future__ import annotations

import redis.asyncio as aioredis
from typing import Optional

from beacon.logging import get_logger

logger = get_logger(__name__)

_redis: Optional[aioredis.Redis] = None


async def init_redis(url: str) -> aioredis.Redis:
    """Initialize the Redis connection pool."""
    global _redis
    _redis = aioredis.from_url(url, decode_responses=True)
    logger.info("redis_connected", url=url[:30] + "...")
    return _redis


def get_redis() -> aioredis.Redis:
    """Get the Redis client. Raises if not initialized."""
    if _redis is None:
        raise RuntimeError("Redis not initialized. Call init_redis() first.")
    return _redis


async def close_redis() -> None:
    """Close the Redis connection pool."""
    global _redis
    if _redis:
        await _redis.close()
        _redis = None
        logger.info("redis_disconnected")
