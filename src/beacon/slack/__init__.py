"""Beacon Command — Slack Integration.

TokenProvider abstraction, Slack client wrapper, search, and Block Kit builders.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from beacon.logging import get_logger

logger = get_logger(__name__)


class TokenProvider(ABC):
    """Abstract token provider for Slack API access."""

    @abstractmethod
    def get_bot_token(self) -> str:
        """Get the bot token for posting messages and managing channels."""
        ...

    @abstractmethod
    def get_user_token(self) -> str:
        """Get the coordinator user token for search and user-scoped actions."""
        ...

    @abstractmethod
    def get_signing_secret(self) -> str:
        """Get the signing secret for request verification."""
        ...

    def get_app_token(self) -> Optional[str]:
        """Get the app-level token for Socket Mode (optional)."""
        return None


class EnvCoordinatorTokenProvider(TokenProvider):
    """Token provider reading from environment/settings configuration.

    This is the production provider for single-workspace deployment.
    Future OAuthTokenProvider would replace this for multi-workspace.
    """

    def __init__(
        self,
        bot_token: str,
        user_token: str,
        signing_secret: str,
        app_token: str = "",
    ):
        if not bot_token:
            raise ValueError("SLACK_BOT_TOKEN is required")
        if not signing_secret:
            raise ValueError("SLACK_SIGNING_SECRET is required")
        self._bot_token = bot_token
        self._user_token = user_token
        self._signing_secret = signing_secret
        self._app_token = app_token

    def get_bot_token(self) -> str:
        return self._bot_token

    def get_user_token(self) -> str:
        return self._user_token

    def get_signing_secret(self) -> str:
        return self._signing_secret

    def get_app_token(self) -> Optional[str]:
        return self._app_token or None
