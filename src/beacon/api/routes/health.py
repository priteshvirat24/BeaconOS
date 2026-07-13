"""Health and readiness endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from beacon.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.get("/health")
async def health_check() -> dict:
    """Application health check."""
    return {"status": "healthy", "service": "beacon-command"}


@router.get("/ready")
async def readiness_check() -> dict:
    """Readiness check — verifies database and Redis connectivity."""
    checks: dict = {"service": "beacon-command"}

    # Check database
    try:
        from beacon.db import get_engine

        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        checks["database"] = "connected"
    except Exception as e:
        checks["database"] = f"error: {e}"

    # Check Redis
    try:
        from beacon.services.redis import get_redis

        redis = get_redis()
        await redis.ping()
        checks["redis"] = "connected"
    except Exception as e:
        checks["redis"] = f"error: {e}"

    all_ok = all(v in ("connected",) for k, v in checks.items() if k != "service")
    checks["status"] = "ready" if all_ok else "degraded"

    return checks
