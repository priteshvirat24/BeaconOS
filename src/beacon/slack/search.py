"""Beacon Command — Slack Search Provider (Real-Time Search API).

Implements workspace search using Slack's Real-Time Search API
(``assistant.search.context``) with the coordinator's user token.

Why this method (and not the legacy ``search.messages``):
    ``assistant.search.context`` is Slack's purpose-built Real-Time Search (RTS)
    endpoint for AI agents. It returns LLM-ready message *content* plus optional
    surrounding context, is governed by the granular ``search:read.*`` scopes,
    and — crucially for Beacon's consent model — returns results strictly within
    the authenticating principal's own visibility.

Consent / data-minimization posture (see README §Responsible Deployment):
    * We authenticate with the *coordinator's user token*, so Beacon can only
      ever see what that human coordinator can already see.
    * We default ``channel_types`` to public + private *channels only* and
      deliberately exclude ``im`` / ``mpim`` (direct messages). Beacon does not
      read DMs even when the coordinator's token technically could.
    * We default ``include_bots`` to ``False`` so Beacon does not ingest its own
      alert posts as independent evidence (avoids self-referential feedback).

The ``SlackSearchResult`` shape and the retry/backoff + structured-logging
contract are preserved from the previous implementation; only the transport and
response parsing changed. Because RTS is cursor-paginated and reports no grand
total, ``search()`` returns ``(results, next_cursor)`` rather than
``(results, total)`` — ``next_cursor`` is ``None`` when there are no more pages.
"""

from __future__ import annotations

import hashlib
import time
from typing import TYPE_CHECKING, Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from beacon.logging import get_logger

if TYPE_CHECKING:
    from beacon.slack import TokenProvider

logger = get_logger(__name__)

# Granular OAuth scopes required on the coordinator *user* token for
# assistant.search.context to return channel messages. Kept here as the single
# source of truth referenced by .env.example and the OAuth install docs.
RTS_USER_TOKEN_SCOPES: tuple[str, ...] = (
    "search:read.public",   # public channels the coordinator belongs to
    "search:read.private",  # private channels the coordinator belongs to
    "search:read.users",    # resolve author identities
)

# Channel classes Beacon will search by default. Public + private *channels*
# only — DMs (im) and group DMs (mpim) are intentionally excluded so Beacon
# never reads private conversations even when the token could.
DEFAULT_CHANNEL_TYPES: tuple[str, ...] = ("public_channel", "private_channel")

# RTS caps a single page at 20 results.
RTS_MAX_LIMIT = 20


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
        thread_ts: str | None = None,
        is_author_bot: bool = False,
    ):
        self.text = text
        self.channel_id = channel_id
        self.channel_name = channel_name
        self.user_id = user_id
        self.username = username
        self.timestamp = timestamp
        self.permalink = permalink
        self.thread_ts = thread_ts
        self.is_author_bot = is_author_bot

    @property
    def content_hash(self) -> str:
        """SHA-256 hash of the message content for deduplication."""
        return hashlib.sha256(self.text.encode()).hexdigest()

    @property
    def source_id(self) -> str:
        """Stable source identifier for this message."""
        return f"slack:{self.channel_id}:{self.timestamp}"


class SlackSearchProvider:
    """Workspace search via Slack RTS (``assistant.search.context``).

    Authenticates with the coordinator's *user* token so results are scoped to
    the coordinator's own Slack visibility — Beacon only sees what the
    coordinator can see.
    """

    def __init__(
        self,
        token_provider: TokenProvider,
        base_url: str = "https://slack.com/api",
        timeout_seconds: int = 20,
        channel_types: tuple[str, ...] = DEFAULT_CHANNEL_TYPES,
        include_bots: bool = False,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self._token_provider = token_provider
        self._base_url = base_url
        self._timeout = timeout_seconds
        self._channel_types = list(channel_types)
        self._include_bots = include_bots
        # Injectable transport enables the coordinator-visibility test to
        # exercise real parsing against a simulated Slack access boundary.
        self._transport = transport

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
        cursor: str | None = None,
    ) -> tuple[list[SlackSearchResult], str | None]:
        """Execute a Real-Time Search over the coordinator-visible workspace.

        Args:
            query: Natural-language / keyword search query.
            count: Results per page (clamped to RTS max of 20).
            sort: Sort field (``timestamp`` or ``score``).
            sort_dir: Sort direction (``asc`` or ``desc``).
            cursor: Opaque pagination cursor from a previous response.

        Returns:
            Tuple of (results list, next_cursor). ``next_cursor`` is ``None``
            when there are no further pages.
        """
        user_token = self._token_provider.get_user_token()
        if not user_token:
            # No coordinator token → no visibility → no results. Never falls
            # back to a bot token, which would change the access boundary.
            logger.warning("slack_search_no_user_token")
            return [], None

        limit = max(1, min(count, RTS_MAX_LIMIT))
        payload: dict[str, Any] = {
            "query": query,
            "limit": limit,
            "sort": sort,
            "sort_dir": sort_dir,
            "content_types": ["messages"],
            "channel_types": self._channel_types,
            "include_bots": self._include_bots,
        }
        if cursor:
            payload["cursor"] = cursor

        start_time = time.monotonic()

        async with httpx.AsyncClient(
            timeout=self._timeout, transport=self._transport
        ) as client:
            response = await client.post(
                f"{self._base_url}/assistant.search.context",
                headers={
                    "Authorization": f"Bearer {user_token}",
                    "Content-Type": "application/json; charset=utf-8",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        latency_ms = int((time.monotonic() - start_time) * 1000)

        if not data.get("ok"):
            error = data.get("error", "unknown")
            logger.error(
                "slack_search_failed", error=error, query=query, latency_ms=latency_ms
            )
            raise RuntimeError(f"Slack RTS search failed: {error}")

        messages = data.get("results", {}).get("messages", []) or []
        next_cursor = (data.get("response_metadata") or {}).get("next_cursor") or None

        results: list[SlackSearchResult] = []
        for msg in messages:
            results.append(
                SlackSearchResult(
                    text=msg.get("content", "") or "",
                    channel_id=msg.get("channel_id", "") or "",
                    channel_name=msg.get("channel_name", "") or "",
                    user_id=msg.get("author_user_id", "") or "",
                    username=msg.get("author_name", "") or "",
                    timestamp=msg.get("message_ts", "") or "",
                    permalink=msg.get("permalink", "") or "",
                    is_author_bot=bool(msg.get("is_author_bot", False)),
                )
            )

        logger.info(
            "slack_search_completed",
            query=query,
            result_count=len(results),
            has_more=bool(next_cursor),
            channel_types=self._channel_types,
            latency_ms=latency_ms,
        )

        return results, next_cursor
