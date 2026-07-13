"""Beacon Command — Scenario replay harness.

Replays a *real, disclosed* historical/current hazard event through Beacon's
**production** code path — the same normalizer, the same severity/threshold
logic, and the same six-agent :mod:`beacon.agents.pipeline` chain that live
polling uses — and drives the live Mission Timeline exactly as a live event
would.

There is deliberately **no "demo mode" branch** anywhere in the ingestion or
agent code. This harness only (a) reads a stored real payload, (b) calls the
poller's real ``normalize_*`` method, and (c) seeds the normalized hazard into
the real pipeline. If the replay path and the live path ever diverged, that
would be a bug to fix here, not a shortcut.

Every run prints an explicit disclosure of which real event it is replaying
(source, date, location, magnitude/severity) so honest narration is automatic.

Usage:
    python -m scratch.replay_event                     # list scenarios
    python -m scratch.replay_event ridgecrest          # console timeline
    python -m scratch.replay_event ridgecrest --org local
    python -m scratch.replay_event midland_flood --channel C0123456789  # post to Slack
"""

from __future__ import annotations

import argparse
import asyncio
import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from beacon.agents.pipeline import run_intelligence_pipeline
from beacon.ingestion.nws import NWSPoller
from beacon.ingestion.usgs import USGSPoller
from beacon.slack.block_kit import situation_brief_blocks
from beacon.slack.mission_timeline import mission_timeline_blocks
from beacon.slack.sources import footer_for_state

if TYPE_CHECKING:
    from collections.abc import Callable

    from beacon.agents.base import AgentBase

FIXTURES = Path(__file__).parent / "fixtures"


# --- Organization profiles (breadth: large INGO vs small local nonprofit) ---

ORG_PROFILES: dict[str, str] = {
    "ingo": (
        "a large multi-country international NGO with regional logistics hubs, "
        "standing medical teams, and multiple field offices"
    ),
    "local": (
        "a small local relief nonprofit with a handful of volunteers, one "
        "warehouse, and limited surge capacity"
    ),
}


@dataclass
class Scenario:
    key: str
    source: str          # usgs | nws | gdacs
    fixture: str         # filename under scratch/fixtures/
    disclosure: str      # human, real-event disclosure line for narration


# Each scenario points at a REAL payload fetched from the live provider and
# stored verbatim (real GeoJSON shape, not hand-simplified).
SCENARIOS: dict[str, Scenario] = {
    "ridgecrest": Scenario(
        key="ridgecrest",
        source="usgs",
        fixture="usgs_ridgecrest_2019_m71.json",
        disclosure=(
            "REAL EVENT — USGS: 2019 Ridgecrest earthquake sequence, "
            "M7.1, near Ridgecrest, California, 2019-07-06 (event ci38457511)."
        ),
    ),
    "midland_flood": Scenario(
        key="midland_flood",
        source="nws",
        fixture="nws_severe_weather_alert.json",
        disclosure=(
            "REAL EVENT — US National Weather Service: active Flash Flood "
            "Warning (Severe), Midland, TX (fetched live from api.weather.gov)."
        ),
    ),
}


def _normalize(scenario: Scenario) -> dict[str, Any] | None:
    """Run the stored real payload through the poller's REAL normalizer."""
    payload = json.loads((FIXTURES / scenario.fixture).read_text())
    if scenario.source == "usgs":
        poller = USGSPoller(feed_url="unused", min_magnitude=4.0)
        return poller.normalize_feature(payload)
    if scenario.source == "nws":
        return NWSPoller().normalize_alert(payload)
    raise ValueError(f"Unsupported source: {scenario.source}")


def _seed_evidence(normalized: dict[str, Any]) -> list[dict[str, Any]]:
    """Present the normalized hazard to the pipeline as triage input evidence."""
    return [
        {
            "id": f"hazard:{normalized['source_type']}:{normalized['source_event_id']}",
            "source_type": normalized["source_type"],
            "source_provider": normalized["source_type"],
            "hazard_type": normalized["hazard_type"],
            "magnitude": normalized.get("magnitude"),
            "severity_score": normalized["severity_score"],
            "location": normalized.get("location", ""),
            "latitude": normalized.get("latitude"),
            "longitude": normalized.get("longitude"),
            "normalized_content": (
                f"{normalized['title']} — severity {normalized['severity']} "
                f"({normalized['severity_score']}/10) at {normalized.get('location', 'unknown')}"
            ),
        }
    ]


class ConsolePublisher:
    """Pipeline ``on_stage`` callback that prints the timeline progressively.

    Used when no Slack channel is provided, so the harness is fully runnable
    (and its progressive behaviour visible) without Slack credentials.
    """

    def __init__(self) -> None:
        self.frames = 0

    async def __call__(self, node_id: str | None, state: dict[str, Any]) -> None:
        self.frames += 1
        stage = "START" if node_id is None else f"completed: {node_id}"
        print(f"\n─── Mission Timeline update #{self.frames} ({stage}) " + "─" * 20)
        for block in mission_timeline_blocks(state):
            if block["type"] == "section":
                print("  " + block["text"]["text"].replace("\n", "  "))
            elif block["type"] == "context":
                print("  · " + block["elements"][0]["text"])
            elif block["type"] == "header":
                print(block["text"]["text"])


def build_situation_brief(
    scenario: Scenario, normalized: dict[str, Any], state: dict[str, Any]
) -> list[dict[str, Any]]:
    """Build a Situation Brief from the real final pipeline state."""
    claims = state.get("claims", [])
    verified = sum(1 for c in claims if c.get("epistemic_status") == "verified_fact")
    contested = sum(1 for c in claims if c.get("epistemic_status") == "contested")
    tasks = sum(len(p.get("tasks", [])) for p in state.get("plans", []))
    summary = (
        state.get("stage_results", {}).get("triage", {}).get("summary")
        or normalized.get("normalized_content")
        or normalized["title"]
    )
    brief = situation_brief_blocks(
        crisis_title=normalized["title"][:100],
        status="active" if normalized["severity_score"] >= 6 else "monitoring",
        summary=summary,
        evidence_count=len(state.get("evidence_items", [])),
        verified_claims=verified,
        contested_claims=contested,
        critical_gaps=len(state.get("gaps", [])),
        active_tasks=tasks,
        crisis_id=str(state.get("mission_id", "")),
    )
    # Always-on Sources & Visibility footer (provenance + consent posture).
    return brief + footer_for_state(state)


async def replay(
    scenario_key: str,
    *,
    org: str = "ingo",
    channel: str | None = None,
    agents: dict[str, AgentBase] | None = None,
    publisher_factory: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    """Replay one scenario end-to-end through the real pipeline.

    Returns the final pipeline state (plus ``_brief`` blocks) for inspection.
    """
    scenario = SCENARIOS[scenario_key]
    normalized = _normalize(scenario)

    print("=" * 78)
    print(scenario.disclosure)
    print(f"Org profile: {ORG_PROFILES.get(org, org)}")
    if normalized is None:
        print("Event did not clear the ingestion threshold — no crisis triggered.")
        print("=" * 78)
        return {"triggered": False}
    print(
        f"Normalized: type={normalized['hazard_type']} "
        f"severity={normalized['severity']} score={normalized['severity_score']}/10 "
        f"location={normalized.get('location', 'n/a')}"
    )
    print("=" * 78)

    objective = (
        f"Assess and coordinate response to '{normalized['title']}' "
        f"(a {normalized['hazard_type']} event) as {ORG_PROFILES.get(org, org)}."
    )

    # Choose a publisher: real Slack if a channel is given, else console.
    if publisher_factory is not None:
        publisher = publisher_factory()
    elif channel:
        from slack_sdk.web.async_client import AsyncWebClient

        from beacon.config import get_settings
        from beacon.slack.mission_timeline import MissionTimelinePublisher

        client = AsyncWebClient(token=get_settings().slack_bot_token)
        publisher = MissionTimelinePublisher(client, channel)
    else:
        publisher = ConsolePublisher()

    mission_id = uuid.uuid4()
    state = await run_intelligence_pipeline(
        objective=objective,
        mission_id=mission_id,
        crisis_title=normalized["title"][:100],
        seed_evidence=_seed_evidence(normalized),
        agents=agents,
        on_stage=publisher,
    )

    brief = build_situation_brief(scenario, normalized, state)
    state["_brief"] = brief

    # Post or print the resulting Situation Brief.
    if channel and publisher_factory is None:
        from slack_sdk.web.async_client import AsyncWebClient

        from beacon.config import get_settings

        client = AsyncWebClient(token=get_settings().slack_bot_token)
        await client.chat_postMessage(
            channel=channel, text=f"Situation Brief: {normalized['title'][:80]}", blocks=brief
        )
        print("\n[posted Situation Brief to Slack]")
    else:
        print("\n" + "=" * 78 + "\nSITUATION BRIEF\n" + "=" * 78)
        for block in brief:
            if block["type"] == "header":
                print(block["text"]["text"])
            elif block["type"] == "section" and "text" in block:
                print("  " + block["text"]["text"].replace("\n", "  "))
            elif block["type"] == "section" and "fields" in block:
                print("  " + " | ".join(f["text"].replace("\n", ": ") for f in block["fields"]))
            elif block["type"] == "context":
                print("  · " + block["elements"][0]["text"])

    return state


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay a real hazard event through Beacon.")
    parser.add_argument("scenario", nargs="?", help="scenario key")
    parser.add_argument("--org", default="ingo", choices=list(ORG_PROFILES), help="org profile")
    parser.add_argument("--channel", default=None, help="Slack channel id to post to")
    args = parser.parse_args()

    if not args.scenario:
        print("Available scenarios:")
        for s in SCENARIOS.values():
            print(f"  {s.key:16s} [{s.source}]  {s.disclosure}")
        return

    asyncio.run(replay(args.scenario, org=args.org, channel=args.channel))


if __name__ == "__main__":
    main()
