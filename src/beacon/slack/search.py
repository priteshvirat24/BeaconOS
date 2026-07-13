"""Beacon Command — Slack Search Provider.

Implements workspace search using Slack search.messages API with coordinator user token.
Wrapped behind SlackSearchProvider interface for future RTS migration.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from beacon.logging import get_logger
from beacon.slack import TokenProvider

logger = get_logger(__name__)


class SlackSearchResult:
    """Structured result from a Slack search."""

    def __init__(
        self,
        text: str,
        channel_id: str,
        channel_name: str,
        user_id: str,
        username: str,
        timestamp: str,
        permalink: str,
        thread_ts: Optional[str] = None,
    ):
        self.text = text
        self.channel_id = channel_id
        self.channel_name = channel_name
        self.user_id = user_id
        self.username = username
        self.timestamp = timestamp
        self.permalink = permalink
        self.thread_ts = thread_ts

    @property
    def content_hash(self) -> str:
        """SHA-256 hash of the message content for deduplication."""
        return hashlib.sha256(self.text.encode()).hexdigest()

    @property
    def source_id(self) -> str:
        """Stable source identifier for this message."""
        return f"slack:{self.channel_id}:{self.timestamp}"


class SlackSearchProvider:
    """Slack search using search.messages with coordinator user token.

    Uses the user token because search.messages requires user-level auth.
    This provider respects the coordinator's actual access scope — Beacon
    only sees what the coordinator can see.
    """

    def __init__(
        self,
        token_provider: TokenProvider,
        base_url: str = "https://slack.com/api",
        timeout_seconds: int = 20,
    ):
        self._token_provider = token_provider
        self._base_url = base_url
        self._timeout = timeout_seconds

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def search(
        self,
        query: str,
        *,
        count: int = 20,
        sort: str = "timestamp",
        sort_dir: str = "desc",
        page: int = 1,
    ) -> tuple[list[SlackSearchResult], int]:
        """Execute a workspace search.

        Args:
            query: Search query string.
            count: Number of results per page.
            sort: Sort field (timestamp or score).
            sort_dir: Sort direction (asc or desc).
            page: Page number.

        Returns:
            Tuple of (results list, total matches count).
        """
        user_token = self._token_provider.get_user_token()
        if not user_token:
            logger.warning("slack_search_no_user_token")
            return [], 0

        start_time = time.monotonic()

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base_url}/search.messages",
                headers={"Authorization": f"Bearer {user_token}"},
                data={
                    "query": query,
                    "count": str(count),
                    "sort": sort,
                    "sort_dir": sort_dir,
                    "page": str(page),
                },
            )
            response.raise_for_status()
            data = response.json()

        latency_ms = int((time.monotonic() - start_time) * 1000)

        if not data.get("ok"):
            error = data.get("error", "unknown")
            logger.error("slack_search_failed", error=error, query=query, latency_ms=latency_ms)
            raise RuntimeError(f"Slack search failed: {error}")

        messages = data.get("messages", {})
        total = messages.get("total", 0)
        matches = messages.get("matches", [])

        results = []
        for match in matches:
            results.append(SlackSearchResult(
                text=match.get("text", ""),
                channel_id=match.get("channel", {}).get("id", ""),
                channel_name=match.get("channel", {}).get("name", ""),
                user_id=match.get("user", ""),
                username=match.get("username", ""),
                timestamp=match.get("ts", ""),
                permalink=match.get("permalink", ""),
                thread_ts=match.get("thread_ts"),
            ))

        logger.info(
            "slack_search_completed",
            query=query,
            result_count=len(results),
            total_matches=total,
            latency_ms=latency_ms,
        )

        return results, total
