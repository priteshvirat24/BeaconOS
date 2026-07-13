"""Tests for the Sources & Visibility footer (provenance + consent posture)."""

from __future__ import annotations

import json

from beacon.slack.sources import (
    compute_source_visibility,
    footer_for_state,
    sources_visibility_footer_blocks,
)


def _state(evidence, claims):
    return {"evidence_items": evidence, "claims": claims}


def _rts(channel_id, channel_name):
    return {
        "source_type": "slack_rts",
        "metadata": {"channel_id": channel_id, "channel_name": channel_name},
    }


def test_counts_public_channels_and_claims():
    state = _state(
        evidence=[
            _rts("C1", "ph-ops"),
            _rts("C1", "ph-ops"),
            _rts("C2", "vols"),
            {"source_type": "hazard_api", "metadata": {}},  # not a Slack source
        ],
        claims=[
            {"epistemic_status": "verified_fact"},
            {"epistemic_status": "verified_fact"},
            {"epistemic_status": "supported_inference"},
            {"epistemic_status": "weak_inference"},
            {"epistemic_status": "contested"},
        ],
    )
    sv = compute_source_visibility(state)
    assert sv.public_channels == 2  # distinct channel names, dedup
    assert sv.evidence_count == 4
    assert sv.verified == 2
    assert sv.supported_inference == 1
    assert sv.weak_inference == 1
    assert sv.contested == 1


def test_private_conversations_is_zero_for_rts_evidence():
    """RTS excludes DMs by construction — the footer must reflect 0."""
    state = _state(
        evidence=[
            {"source_type": "slack_rts", "metadata": {"channel_id": "C9", "channel_name": "ops"}},
        ],
        claims=[],
    )
    assert compute_source_visibility(state).private_conversations == 0


def test_dm_leak_would_be_detected():
    """If a DM (channel id starting with 'D') ever leaked, the count exposes it."""
    state = _state(
        evidence=[
            {"source_type": "slack_rts", "metadata": {"channel_id": "D123", "channel_name": "dm"}},
        ],
        claims=[],
    )
    # This is the guard: the count is computed, not hardcoded to 0.
    assert compute_source_visibility(state).private_conversations == 1


def test_footer_text_contains_real_numbers():
    state = _state(
        evidence=[
            {"source_type": "slack_rts", "metadata": {"channel_id": "C1", "channel_name": "ops"}},
        ],
        claims=[{"epistemic_status": "verified_fact"}],
    )
    blocks = footer_for_state(state)
    text = json.dumps(blocks)
    assert "Sources & Visibility" in text
    assert "1 verified" in text
    assert "private conversation" in text
    assert "*0*" in text  # zero private conversations, mechanically
    assert "never direct messages" in text


def test_footer_blocks_are_valid_block_kit():
    sv = compute_source_visibility(_state([], []))
    blocks = sources_visibility_footer_blocks(sv)
    assert blocks[0]["type"] == "divider"
    assert all(b["type"] in ("divider", "context") for b in blocks)
