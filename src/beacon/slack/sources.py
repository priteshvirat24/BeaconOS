"""Beacon Command — Sources & Visibility computation.

Turns the real evidence/claim state of a mission into an honest, always-visible
provenance footer for Situation Briefs. Most Slack bots hide their sourcing;
Beacon makes evidence provenance and its *consent posture* a first-class UI
element.

The "0 private conversations" figure is not a hardcoded reassurance — it is
computed from real state. Slack direct-message and group-DM channel IDs begin
with ``D``; because the RTS layer (:mod:`beacon.slack.search`) excludes
``im``/``mpim`` by construction, this count is mechanically 0, and it would
surface a non-zero number immediately if a DM ever leaked into the evidence set.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from beacon.slack.block_kit import BlockBuilder


@dataclass
class SourceVisibility:
    """Provenance + consent summary derived from real mission state."""

    public_channels: int
    private_conversations: int
    evidence_count: int
    verified: int
    supported_inference: int
    weak_inference: int
    contested: int


def compute_source_visibility(state: dict[str, Any]) -> SourceVisibility:
    """Compute the Sources & Visibility summary from live pipeline state."""
    evidence = state.get("evidence_items", [])

    workspace_channels: set[str] = set()
    dm_conversations: set[str] = set()
    for ev in evidence:
        if ev.get("source_type") != "slack_rts":
            continue
        meta = ev.get("metadata", {}) or {}
        channel_id = str(meta.get("channel_id", "") or "")
        channel_name = meta.get("channel_name") or channel_id
        # Slack DM / group-DM channel ids start with 'D'; these must never appear.
        if channel_id.startswith("D"):
            dm_conversations.add(channel_id)
        elif channel_name:
            workspace_channels.add(channel_name)

    claims = state.get("claims", [])

    def _count(status: str) -> int:
        return sum(1 for c in claims if c.get("epistemic_status") == status)

    return SourceVisibility(
        public_channels=len(workspace_channels),
        private_conversations=len(dm_conversations),
        evidence_count=len(evidence),
        verified=_count("verified_fact"),
        supported_inference=_count("supported_inference"),
        weak_inference=_count("weak_inference"),
        contested=_count("contested"),
    )


def sources_visibility_footer_blocks(sv: SourceVisibility) -> list[dict[str, Any]]:
    """Build the always-on Sources & Visibility footer Block Kit blocks."""
    b = BlockBuilder()
    b.divider()
    b.context(
        f"🔎 *Sources & Visibility* — Grounded in *{sv.public_channels}* "
        f"coordinator-visible channel(s), *{sv.private_conversations}* private "
        f"conversation(s), *{sv.evidence_count}* evidence item(s). "
        f"Claims: {sv.verified} verified · {sv.supported_inference} supported "
        f"inference · {sv.weak_inference} weak · {sv.contested} contested."
    )
    b.context(
        "🔒 Beacon searches only channels the coordinator can already see — "
        "never direct messages, and never its own bot posts."
    )
    return b.build()


def footer_for_state(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Convenience: compute and render the footer directly from state."""
    return sources_visibility_footer_blocks(compute_source_visibility(state))
