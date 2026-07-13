"""Beacon Command — Sandbox seeding.

Populates a demo Slack workspace with realistic, coherent content so a judge
who explores the sandbox independently sees a populated operation — not an empty
workspace that only makes sense while the video is playing.

The seeded messages align with the `ridgecrest` scenario so the workspace tells
the same story the demo does: a field response to a major earthquake, with
volunteers, logistics, and operational chatter that the Workspace Investigator
would realistically surface.

All content is synthetic (no real people / no real PII).

Usage (bot token needs chat:write and must be invited to the channels):
    export SLACK_BOT_TOKEN=xoxb-...
    python -m scratch.seed_sandbox --ph-ops C012 --volunteers C034 --logistics C056
    python -m scratch.seed_sandbox --dry-run     # print what would be posted
"""

from __future__ import annotations

import argparse
import asyncio
import os

# channel-key -> ordered list of realistic messages
SEED_CONTENT: dict[str, list[str]] = {
    "ph-operations": [
        "Heads up team — USGS just reported a M7.1 near Ridgecrest. Standing up response ops.",
        "Confirmed: our field clinic on 3rd Ave is structurally intact and operational.",
        "Power is out across the east district; the clinic is running on its backup generator.",
        "Road access on Highway 178 is reported blocked by debris — needs verification.",
        "Incident command established. Coordinator on point for the next 12h shift.",
    ],
    "volunteers": [
        "I can drive supplies from the Bakersfield depot tonight — have a 3/4-ton truck.",
        "Two nurses from our roster are available and can reach the 3rd Ave clinic by 8pm.",
        "Shelter at the community center is open; we have room for ~40 people right now.",
        "Need 4 more volunteers for the overnight shift at the shelter — please reply here.",
    ],
    "ph-logistics": [
        "Generator fuel at the clinic is down to ~18 hours. Reordering now.",
        "Medical supply pallet #A17 staged at the depot, ready for dispatch.",
        "Bridge on the north route is weight-restricted post-quake; reroute heavy vehicles.",
        "Water: 600 units on hand at the warehouse, sufficient for 48h at current demand.",
    ],
}


def _post_plan(channels: dict[str, str]) -> list[tuple[str, str, str]]:
    plan: list[tuple[str, str, str]] = []
    for key, messages in SEED_CONTENT.items():
        channel_id = channels.get(key)
        if not channel_id:
            continue
        for msg in messages:
            plan.append((key, channel_id, msg))
    return plan


async def seed(channels: dict[str, str], *, dry_run: bool) -> None:
    plan = _post_plan(channels)
    if not plan:
        print("No channels provided. Pass --ph-ops / --volunteers / --logistics.")
        return

    if dry_run:
        for key, channel_id, msg in plan:
            print(f"[dry-run] #{key} ({channel_id}): {msg}")
        print(f"\n{len(plan)} message(s) would be posted.")
        return

    token = os.environ.get("SLACK_BOT_TOKEN", "")
    if not token:
        print("SLACK_BOT_TOKEN not set. Export it (needs chat:write) and retry.")
        return

    from slack_sdk.web.async_client import AsyncWebClient

    client = AsyncWebClient(token=token)
    posted = 0
    for key, channel_id, msg in plan:
        try:
            await client.chat_postMessage(channel=channel_id, text=msg)
            posted += 1
            await asyncio.sleep(0.4)  # be gentle with rate limits
        except Exception as e:  # noqa: BLE001
            print(f"  failed to post to #{key} ({channel_id}): {e}")
    print(f"Seeded {posted}/{len(plan)} messages across {len(channels)} channel(s).")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed a Beacon demo Slack workspace.")
    parser.add_argument("--ph-ops", dest="ph_operations", help="#ph-operations channel id")
    parser.add_argument("--volunteers", dest="volunteers", help="#volunteers channel id")
    parser.add_argument("--logistics", dest="ph_logistics", help="#ph-logistics channel id")
    parser.add_argument("--dry-run", action="store_true", help="print instead of posting")
    args = parser.parse_args()

    channels = {
        "ph-operations": args.ph_operations,
        "volunteers": args.volunteers,
        "ph-logistics": args.ph_logistics,
    }
    channels = {k: v for k, v in channels.items() if v}
    asyncio.run(seed(channels, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
