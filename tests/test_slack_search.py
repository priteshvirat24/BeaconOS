"""Tests for Beacon Command — Slack Real-Time Search provider.

These tests exercise the ``assistant.search.context`` (RTS) migration and,
most importantly, prove the *coordinator-visibility guarantee* in code:

    Beacon only ever surfaces what the authenticating coordinator's token is
    allowed to see. A token with no access to a private channel returns zero
    results from that channel, and direct messages are never returned at all.

We can't call the live Slack API in a unit test, so we inject an
``httpx.MockTransport`` that *simulates Slack's own access boundary*: it reads
the presented bearer token and the requested ``channel_types`` and returns only
the messages that token is authorized to see. The assertions then verify that
our provider (a) authenticates with the coordinator user token, (b) requests a
DM-excluding channel set, and (c) faithfully surfaces only what the boundary
returns — never fabricating or broadening access.
"""

from __future__ import annotations

import json

import httpx
import pytest

from beacon.slack import TokenProvider
from beacon.slack.search import (
    DEFAULT_CHANNEL_TYPES,
    RTS_MAX_LIMIT,
    SlackSearchProvider,
)

# --- Simulated Slack workspace --------------------------------------------

PUBLIC_CHANNEL = {"id": "C_PUBLIC", "name": "ph-operations", "type": "public_channel"}
PRIVATE_CHANNEL = {"id": "C_PRIVATE", "name": "exec-private", "type": "private_channel"}
DM_CHANNEL = {"id": "D_DM", "name": "mpdm-coord", "type": "im"}

# A message lives in exactly one channel.
WORLD = {
    "C_PUBLIC": [
        {
            "author_name": "Priya Coordinator",
            "author_user_id": "U_PRIYA",
            "team_id": "T1",
            "channel_id": "C_PUBLIC",
            "channel_name": "ph-operations",
            "message_ts": "1700000000.000100",
            "content": "Field team reports the clinic on 3rd Ave is still standing.",
            "is_author_bot": False,
            "permalink": "https://x.slack.com/archives/C_PUBLIC/p1700000000000100",
        },
        {
            "author_name": "Beacon",
            "author_user_id": "U_BOT",
            "team_id": "T1",
            "channel_id": "C_PUBLIC",
            "channel_name": "ph-operations",
            "message_ts": "1700000000.000200",
            "content": "[Beacon] Automated situation brief posted.",
            "is_author_bot": True,
            "permalink": "https://x.slack.com/archives/C_PUBLIC/p1700000000000200",
        },
    ],
    "C_PRIVATE": [
        {
            "author_name": "Exec Lead",
            "author_user_id": "U_EXEC",
            "team_id": "T1",
            "channel_id": "C_PRIVATE",
            "channel_name": "exec-private",
            "message_ts": "1700000000.000300",
            "content": "Board approved emergency budget of $500k.",
            "is_author_bot": False,
            "permalink": "https://x.slack.com/archives/C_PRIVATE/p1700000000000300",
        }
    ],
    "D_DM": [
        {
            "author_name": "Priya Coordinator",
            "author_user_id": "U_PRIYA",
            "team_id": "T1",
            "channel_id": "D_DM",
            "channel_name": "mpdm-coord",
            "message_ts": "1700000000.000400",
            "content": "private DM: my personal phone is 555-0100",
            "is_author_bot": False,
            "permalink": "https://x.slack.com/archives/D_DM/p1700000000000400",
        }
    ],
}

CHANNEL_TYPE = {
    "C_PUBLIC": "public_channel",
    "C_PRIVATE": "private_channel",
    "D_DM": "im",
}

# Which channels each token is allowed to see (Slack's real boundary).
TOKEN_VISIBILITY = {
    # The default coordinator: member of the public channel and their own DM,
    # but NOT the exec private channel.
    "xoxp-coordinator": {"C_PUBLIC", "D_DM"},
    # An exec whose token additionally sees the private channel.
    "xoxp-exec": {"C_PUBLIC", "C_PRIVATE", "D_DM"},
    # A bot token — should never be used by the search provider.
    "xoxb-bot": {"C_PUBLIC"},
}


def make_transport(seen_requests: list[dict] | None = None) -> httpx.MockTransport:
    """Build a MockTransport that enforces Slack's access boundary."""

    def handler(request: httpx.Request) -> httpx.Response:
        auth = request.headers.get("Authorization", "")
        token = auth.removeprefix("Bearer ").strip()
        body = json.loads(request.content.decode() or "{}")
        if seen_requests is not None:
            seen_requests.append({"token": token, "body": body})

        requested_types = set(body.get("channel_types", []))
        include_bots = bool(body.get("include_bots", False))
        visible = TOKEN_VISIBILITY.get(token, set())

        messages: list[dict] = []
        for channel_id, msgs in WORLD.items():
            if channel_id not in visible:
                continue  # token cannot see this channel — Slack omits it
            if CHANNEL_TYPE[channel_id] not in requested_types:
                continue  # caller did not ask for this channel class
            for m in msgs:
                if m["is_author_bot"] and not include_bots:
                    continue
                messages.append(m)

        return httpx.Response(
            200,
            json={
                "ok": True,
                "results": {"messages": messages, "files": [], "channels": []},
                "response_metadata": {"next_cursor": ""},
            },
        )

    return httpx.MockTransport(handler)


class _StubTokenProvider(TokenProvider):
    def __init__(self, user_token: str, bot_token: str = "xoxb-bot") -> None:
        self._user = user_token
        self._bot = bot_token

    def get_bot_token(self) -> str:
        return self._bot

    def get_user_token(self) -> str:
        return self._user

    def get_signing_secret(self) -> str:
        return "secret"


def make_provider(user_token: str, seen_requests: list | None = None, **kw):
    return SlackSearchProvider(
        _StubTokenProvider(user_token),
        base_url="https://slack.com/api",
        transport=make_transport(seen_requests),
        **kw,
    )


# --- Tests -----------------------------------------------------------------


async def test_returns_public_channel_results_with_correct_field_mapping():
    provider = make_provider("xoxp-coordinator")
    results, cursor = await provider.search("clinic status")

    assert cursor is None
    assert len(results) == 1  # the one human public-channel message
    r = results[0]
    # RTS field mapping: content->text, author_user_id->user_id, etc.
    assert r.text == "Field team reports the clinic on 3rd Ave is still standing."
    assert r.channel_id == "C_PUBLIC"
    assert r.channel_name == "ph-operations"
    assert r.user_id == "U_PRIYA"
    assert r.username == "Priya Coordinator"
    assert r.timestamp == "1700000000.000100"
    assert r.permalink.endswith("p1700000000000100")
    assert r.is_author_bot is False


async def test_coordinator_visibility_private_channel_excluded():
    """THE guarantee: a token without private access sees zero private results."""
    provider = make_provider("xoxp-coordinator")
    results, _ = await provider.search("budget")

    channel_ids = {r.channel_id for r in results}
    assert "C_PRIVATE" not in channel_ids
    assert all("Board approved" not in r.text for r in results)


async def test_authorized_token_does_see_private_channel():
    """The boundary is the token, not a hardcoded filter: an exec token sees it."""
    provider = make_provider("xoxp-exec")
    results, _ = await provider.search("budget")

    private = [r for r in results if r.channel_id == "C_PRIVATE"]
    assert len(private) == 1
    assert "Board approved emergency budget" in private[0].text


async def test_direct_messages_never_returned_even_when_token_can_see_them():
    """DMs are excluded by construction (channel_types), enforcing consent."""
    # xoxp-exec can *see* the DM, but the provider must not request im/mpim.
    provider = make_provider("xoxp-exec")
    results, _ = await provider.search("phone")

    assert all(r.channel_id != "D_DM" for r in results)
    assert all("personal phone" not in r.text for r in results)


async def test_uses_coordinator_user_token_not_bot_token():
    seen: list[dict] = []
    provider = make_provider("xoxp-coordinator", seen_requests=seen)
    await provider.search("anything")

    assert seen, "no request was made"
    assert seen[0]["token"] == "xoxp-coordinator"
    assert seen[0]["token"] != "xoxb-bot"


async def test_default_channel_types_exclude_dms():
    seen: list[dict] = []
    provider = make_provider("xoxp-coordinator", seen_requests=seen)
    await provider.search("anything")

    requested = seen[0]["body"]["channel_types"]
    assert set(requested) == set(DEFAULT_CHANNEL_TYPES)
    assert "im" not in requested and "mpim" not in requested


async def test_bot_messages_excluded_by_default():
    provider = make_provider("xoxp-coordinator")
    results, _ = await provider.search("brief")
    assert all(r.is_author_bot is False for r in results)


async def test_limit_clamped_to_rts_max():
    seen: list[dict] = []
    provider = make_provider("xoxp-coordinator", seen_requests=seen)
    await provider.search("anything", count=1000)
    assert seen[0]["body"]["limit"] == RTS_MAX_LIMIT


async def test_no_user_token_returns_empty_without_calling_api():
    seen: list[dict] = []
    provider = make_provider("", seen_requests=seen)
    results, cursor = await provider.search("anything")
    assert results == [] and cursor is None
    assert seen == []  # never hit the network / never fell back to bot token


async def test_targets_assistant_search_context_endpoint():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(
            200, json={"ok": True, "results": {"messages": []}, "response_metadata": {}}
        )

    provider = SlackSearchProvider(
        _StubTokenProvider("xoxp-coordinator"),
        base_url="https://slack.com/api",
        transport=httpx.MockTransport(handler),
    )
    await provider.search("q")
    assert captured["url"].endswith("/assistant.search.context")


async def test_api_error_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": False, "error": "not_authed"})

    provider = SlackSearchProvider(
        _StubTokenProvider("xoxp-coordinator"),
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(RuntimeError, match="not_authed"):
        await provider.search("q")
