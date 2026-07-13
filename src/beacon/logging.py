"""Beacon Command — Structured Logging.

Uses structlog with JSON output in production and console output in development.
Secrets are automatically redacted from log output.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

_SECRET_KEYS = frozenset({
    "slack_bot_token",
    "slack_coordinator_user_token",
    "slack_signing_secret",
    "slack_app_token",
    "gemini_api_key",
    "openai_api_key",
    "langsmith_api_key",
    "weather_api_key",
    "geocoding_api_key",
    "routing_api_key",
    "resource_api_key",
    "authorization",
    "token",
    "password",
    "secret",
    "api_key",
})


def _redact_secrets(
    _logger: Any, _method: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Redact known secret keys from structured log events."""
    for key in list(event_dict.keys()):
        if any(s in key.lower() for s in _SECRET_KEYS):
            val = event_dict[key]
            if isinstance(val, str) and len(val) > 8:
                event_dict[key] = val[:4] + "****" + val[-4:]
            elif isinstance(val, str):
                event_dict[key] = "****"
    return event_dict


def configure_logging(log_level: str = "INFO", json_output: bool = False) -> None:
    """Configure structlog and stdlib logging for the application.

    Args:
        log_level: Logging level string.
        json_output: If True, output JSON lines. If False, use colored console output.
    """
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.ExtraAdder(),
        _redact_secrets,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if json_output:
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Quiet noisy libraries
    for name in ("uvicorn.access", "httpx", "httpcore", "asyncio"):
        logging.getLogger(name).setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Get a structured logger instance."""
    return structlog.get_logger(name)
