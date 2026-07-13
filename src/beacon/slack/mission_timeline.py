"""Beacon Command — Mission Timeline surface.

A live Block Kit surface that renders the multi-agent intelligence pipeline as
it executes. It is posted once with ``chat.postMessage`` and then advanced with
``chat.update`` on every real graph-node completion, so a viewer watches Triage →
Investigator → Synthesizer → Planner → Critic light up in near-real-time.

Crucially, every number on this surface is read from the *live merged pipeline
state* (see :mod:`beacon.agents.pipeline`) — claim confidence counts, DAG edge
counts, risk-flag counts are all real, not scripted. If the pipeline finds zero
verified claims, the timeline shows zero.
"""

from __future__ import annotations

from typing import Any

from beacon.agents.pipeline import STAGE_EMOJI, STAGE_LABELS, STAGE_ORDER
from beacon.logging import get_logger
from beacon.slack.block_kit import (
    BlockBuilder,
    severity_emoji,
    severity_label_for_score,
)

logger = get_logger(__name__)

ICON_DONE = "✅"
ICON_RUNNING = "🔄"
ICON_PENDING = "⏳"
ICON_FLAGGED = "⚠️"


def _stage_status(node_id: str, state: dict[str, Any]) -> str:
    """Return one of: done, flagged, running, pending — from real state."""
    completed = state.get("stage_results", {})
    if node_id in completed:
        res = completed[node_id]
        if res.get("status") == "failed":
            return "flagged"
        if node_id == "critique" and res.get("metrics", {}).get("risk_flags", 0) > 0:
            return "flagged"
        return "done"

    # First not-yet-completed stage is "running"; the rest are pending.
    for candidate in STAGE_ORDER:
        if candidate not in completed:
            return "running" if candidate == node_id else "pending"
    return "pending"


def _stage_metric_text(node_id: str, state: dict[str, Any]) -> str:
    """Human-readable, real metric summary for a completed stage."""
    res = state.get("stage_results", {}).get(node_id)
    if not res:
        return "_waiting…_"
    if res.get("status") == "failed":
        return f"_stage error — pipeline continued_ (`{res.get('summary', '')[:80]}`)"
    m = res.get("metrics", {})
    if node_id == "triage":
        parts = [f"severity *{m.get('severity', 'n/a')}*"]
        if m.get("should_create_crisis"):
            parts.append("→ create crisis")
        parts.append(f"{m.get('recommended_missions', 0)} missions")
        parts.append(f"{m.get('initial_questions', 0)} questions")
        return " · ".join(parts)
    if node_id in ("investigate", "external_intel"):
        return (
            f"+{m.get('evidence_added', 0)} evidence "
            f"({m.get('evidence_total', 0)} total) · {m.get('searches', 0)} queries"
        )
    if node_id == "synthesize":
        return (
            f"*{m.get('claims_total', 0)} claims* — "
            f"✅{m.get('verified_fact', 0)} "
            f"🟢{m.get('supported_inference', 0)} "
            f"🟡{m.get('weak_inference', 0)} "
            f"🔴{m.get('contested', 0)} · "
            f"{m.get('contradictions', 0)} contradictions"
        )
    if node_id == "plan":
        return f"*{m.get('tasks', 0)} tasks* · {m.get('dag_edges', 0)} dependency edges (DAG)"
    if node_id == "critique":
        return (
            f"*{m.get('risk_flags', 0)} risk flags* · "
            f"{m.get('spofs', 0)} single points of failure · "
            f"severity {float(m.get('severity_score', 0.0)):.2f}"
        )
    return str(res.get("summary", ""))[:120]


def mission_timeline_blocks(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Render the current pipeline state as a Mission Timeline surface."""
    title = state.get("crisis_title") or state.get("objective") or "Mission"
    completed = state.get("stage_results", {})
    done_count = sum(
        1 for n in STAGE_ORDER if n in completed and completed[n].get("status") != "failed"
    )
    total = len(STAGE_ORDER)

    stage_num = min(done_count + (0 if done_count == total else 1), total)
    # Uniform severity chip, shared with hazard alerts / situation briefs.
    label = severity_label_for_score(state.get("severity_score"))
    chip = severity_emoji(label)
    b = BlockBuilder()
    b.header(f"{chip} Mission Timeline: {title[:78]}")
    progress_bar = "▓" * done_count + "░" * (total - done_count)
    b.context(
        f"`{progress_bar}`  Stage {stage_num}/{total}  ·  Live multi-agent reasoning"
    )
    b.divider()

    for node_id in STAGE_ORDER:
        status = _stage_status(node_id, state)
        icon = {
            "done": ICON_DONE,
            "flagged": ICON_FLAGGED,
            "running": ICON_RUNNING,
            "pending": ICON_PENDING,
        }[status]
        label = STAGE_LABELS[node_id]
        emoji = STAGE_EMOJI[node_id]
        if status in ("done", "flagged"):
            detail = _stage_metric_text(node_id, state)
        elif status == "running":
            detail = "_reasoning…_"
        else:
            detail = "_queued_"
        b.section(f"{icon} {emoji} *{label}*\n{detail}")

    b.divider()
    b.context(
        f"Evidence: {len(state.get('evidence_items', []))}  ·  "
        f"Claims: {len(state.get('claims', []))}  ·  "
        f"Contradictions: {len(state.get('contradictions', []))}  ·  "
        f"Errors: {len(state.get('errors', []))}"
    )
    return b.build()


class MissionTimelinePublisher:
    """Posts a Mission Timeline and advances it via ``chat.update``.

    Instances are directly usable as a pipeline ``on_stage`` callback:

        publisher = MissionTimelinePublisher(client, channel="C123")
        await run_intelligence_pipeline(objective=..., on_stage=publisher)

    A Slack failure never aborts the pipeline — the timeline is best-effort.
    """

    def __init__(
        self,
        client: Any,
        channel: str,
        *,
        fallback_text: str = "Beacon mission in progress…",
    ) -> None:
        self._client = client
        self._channel = channel
        self._fallback = fallback_text
        self.ts: str | None = None

    async def __call__(self, node_id: str | None, state: dict[str, Any]) -> None:
        blocks = mission_timeline_blocks(state)
        try:
            if self.ts is None:
                resp = await self._client.chat_postMessage(
                    channel=self._channel, text=self._fallback, blocks=blocks
                )
                self.ts = resp["ts"]
            else:
                await self._client.chat_update(
                    channel=self._channel,
                    ts=self.ts,
                    text=self._fallback,
                    blocks=blocks,
                )
        except Exception as e:  # noqa: BLE001 - timeline is best-effort
            logger.warning(
                "mission_timeline_publish_failed", stage=node_id, error=str(e)
            )
