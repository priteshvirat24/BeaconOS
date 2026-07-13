"""Beacon Command — FastAPI Application Entrypoint.

Initializes all subsystems: database, logging, tracing, Slack, ingestion, MCP, agents.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from beacon.config import BeaconSettings, get_settings
from beacon.db import init_engine, close_engine
from beacon.logging import configure_logging, get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager — startup and shutdown."""
    settings = get_settings()

    # Configure logging
    configure_logging(
        log_level=settings.log_level,
        json_output=settings.app_env.value != "development",
    )
    logger.info(
        "beacon_starting",
        env=settings.app_env.value,
        host=settings.app_host,
        port=settings.app_port,
    )

    # Configure tracing
    from beacon.tracing import configure_tracing

    configure_tracing(
        service_name=settings.otel_service_name,
        otlp_endpoint=settings.otel_exporter_otlp_endpoint,
    )

    # Initialize database
    init_engine(settings.database_url)
    logger.info("database_initialized")

    # Initialize Redis
    try:
        from beacon.services.redis import init_redis

        await init_redis(settings.redis_url)
        logger.info("redis_initialized")
    except Exception as e:
        logger.warning("redis_init_failed", error=str(e))

    # Start hazard ingestion if configured
    ingestion_task = None
    try:
        from beacon.ingestion.scheduler import start_ingestion_scheduler

        ingestion_task = asyncio.create_task(start_ingestion_scheduler(settings))
        logger.info("ingestion_scheduler_started")
    except Exception as e:
        logger.warning("ingestion_scheduler_failed", error=str(e))

    # Initialize Slack Bolt app
    socket_task = None
    try:
        from beacon.slack.app import create_slack_app

        bolt_app = create_slack_app()
        if bolt_app:
            app.state.slack_bolt = bolt_app
            logger.info("slack_bolt_initialized")
            
            if settings.slack_app_token:
                from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
                socket_mode_handler = AsyncSocketModeHandler(bolt_app, settings.slack_app_token)
                socket_task = asyncio.create_task(socket_mode_handler.connect_async())
                logger.info("slack_socket_mode_started")
        else:
            logger.info("slack_bolt_skipped", reason="not configured")
    except Exception as e:
        logger.warning("slack_bolt_init_failed", error=str(e))

    # Start deadline monitor
    deadline_task = None
    try:
        from beacon.services.task_manager import deadline_monitor

        async def _deadline_loop() -> None:
            while True:
                try:
                    await deadline_monitor.check_deadlines()
                except Exception as e:
                    logger.error("deadline_monitor_error", error=str(e))
                await asyncio.sleep(60)

        deadline_task = asyncio.create_task(_deadline_loop())
        logger.info("deadline_monitor_started")
    except Exception as e:
        logger.warning("deadline_monitor_failed", error=str(e))

    logger.info("beacon_ready")
    yield

    # Shutdown
    logger.info("beacon_shutting_down")
    for task in [ingestion_task, deadline_task, socket_task]:
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    try:
        from beacon.services.redis import close_redis

        await close_redis()
    except Exception:
        pass

    await close_engine()
    logger.info("beacon_stopped")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="Beacon Command",
        description="Evidence-grounded crisis intelligence and coordination system",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.app_env.value == "development" else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register API routes
    from beacon.api.router import api_router

    app.include_router(api_router)

    # Mount Slack Bolt events endpoint
    @app.post("/slack/events")
    async def slack_events(request: Request) -> JSONResponse:
        """Slack events endpoint — proxies to Bolt app."""
        bolt = getattr(app.state, "slack_bolt", None)
        if not bolt:
            return JSONResponse({"error": "Slack not configured"}, status_code=503)
        from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler
        handler = AsyncSlackRequestHandler(bolt)
        return await handler.handle(request)

    @app.post("/slack/interactions")
    async def slack_interactions(request: Request) -> JSONResponse:
        """Slack interactive components endpoint."""
        bolt = getattr(app.state, "slack_bolt", None)
        if not bolt:
            return JSONResponse({"error": "Slack not configured"}, status_code=503)
        from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler
        handler = AsyncSlackRequestHandler(bolt)
        return await handler.handle(request)

    # Global exception handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "unhandled_exception",
            path=request.url.path,
            method=request.method,
            error=str(exc),
            exc_info=True,
        )
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error", "detail": "An unexpected error occurred"},
        )

    return app


app = create_app()


if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "beacon.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_env.value == "development",
        log_level=settings.log_level.lower(),
    )
