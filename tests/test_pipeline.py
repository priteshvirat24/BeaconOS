"""Tests for the multi-agent intelligence pipeline and Mission Timeline.

These prove that the timeline reflects *real* LangGraph execution: the graph
runs for real, state accumulates across stages (synthesizer sees investigator
evidence, planner sees claims, critic sees the plan), and the timeline surface
renders the real merged metrics (claim confidences, DAG edges, risk flags).

Agent bodies are replaced with deterministic stubs so the test is hermetic (no
LLM / Slack / MCP), but the pipeline graph itself is the production graph.
"""

from __future__ import annotations

import uuid

from beacon.agents.base import (
    AgentBase,
    AgentContext,
    AgentResult,
    ClaimProposal,
    ContradictionProposal,
    EvidenceCandidate,
)
from beacon.agents.pipeline import STAGE_ORDER, run_intelligence_pipeline
from beacon.slack.mission_timeline import (
    MissionTimelinePublisher,
    mission_timeline_blocks,
)


class _StubAgent(AgentBase):
    def __init__(self, node_id: str) -> None:
        super().__init__(agent_id=node_id, capabilities=[])
        self.node_id = node_id
        self.seen_context: AgentContext | None = None

    @property
    def system_prompt(self) -> str:
        return "stub"

    async def execute(self, context: AgentContext) -> AgentResult:
        self.seen_context = context
        r = self._empty_result(context)
        if self.node_id == "triage":
            r.metadata = {"should_create_crisis": True, "severity_assessment": "severe"}
            r.mission_proposals = [{"mission_type": "workspace_investigation"}]
        elif self.node_id == "investigate":
            r.evidence_candidates = [
                EvidenceCandidate(
                    source_type="slack_rts",
                    source_provider="slack_search",
                    normalized_content="Clinic on 3rd Ave is operational.",
                    raw_content_hash="h1",
                )
            ]
        elif self.node_id == "external_intel":
            r.evidence_candidates = [
                EvidenceCandidate(
                    source_type="hazard_api",
                    source_provider="usgs",
                    normalized_content="M6.1 aftershock 20km NE.",
                    raw_content_hash="h2",
                )
            ]
        elif self.node_id == "synthesize":
            r.claim_proposals = [
                ClaimProposal(
                    statement="Clinic is operational.",
                    epistemic_status="verified_fact",
                    confidence=0.9,
                ),
                ClaimProposal(
                    statement="Aftershocks likely to continue.",
                    epistemic_status="supported_inference",
                    confidence=0.6,
                ),
            ]
            r.contradiction_proposals = [
                ContradictionProposal(description="road status conflict", severity=0.4)
            ]
        elif self.node_id == "plan":
            r.plan_proposals = [
                {
                    "objective": "Stabilize clinic supply",
                    "tasks": [
                        {"objective": "Assess road access", "dependencies": []},
                        {"objective": "Dispatch supplies", "dependencies": [0]},
                        {"objective": "Confirm delivery", "dependencies": [1]},
                    ],
                }
            ]
        elif self.node_id == "critique":
            r.metadata = {
                "single_points_of_failure": ["only one route to clinic"],
                "unsupported_assumptions": ["assumes bridge intact"],
                "severity_score": 0.55,
            }
        return r


def _stub_agents() -> dict[str, _StubAgent]:
    return {node_id: _StubAgent(node_id) for node_id in STAGE_ORDER}


class _FakeSlackClient:
    def __init__(self) -> None:
        self.posts: list[dict] = []
        self.updates: list[dict] = []

    async def chat_postMessage(self, **kwargs):  # noqa: N802 - Slack SDK API name
        self.posts.append(kwargs)
        return {"ts": "1700000000.000001"}

    async def chat_update(self, **kwargs):  # noqa: N802 - Slack SDK API name
        self.updates.append(kwargs)
        return {"ts": kwargs.get("ts")}


# --- Pipeline behaviour ----------------------------------------------------


async def test_pipeline_runs_all_stages_in_order():
    seen: list[str] = []

    async def on_stage(node_id, state):
        if node_id is not None:
            seen.append(node_id)

    await run_intelligence_pipeline(
        objective="test", agents=_stub_agents(), on_stage=on_stage
    )
    assert seen == list(STAGE_ORDER)


async def test_state_accumulates_across_stages():
    """The core 'real pipeline' claim: later agents see earlier outputs."""
    agents = _stub_agents()
    final = await run_intelligence_pipeline(objective="test", agents=agents)

    # Synthesizer must have seen both evidence items produced upstream.
    synth_ctx = agents["synthesize"].seen_context
    assert synth_ctx is not None
    assert len(synth_ctx.world_model.evidence_items) == 2

    # Planner must have seen the synthesizer's claims.
    plan_ctx = agents["plan"].seen_context
    assert len(plan_ctx.world_model.claims) == 2

    # Critic must have seen the planner's plan.
    crit_ctx = agents["critique"].seen_context
    assert len(crit_ctx.world_model.active_plans) == 1

    assert len(final["evidence_items"]) == 2
    assert len(final["claims"]) == 2
    assert len(final["plans"]) == 1


async def test_pipeline_survives_a_failing_stage():
    class _Boom(_StubAgent):
        async def execute(self, context):
            raise RuntimeError("kaboom")

    agents = _stub_agents()
    agents["external_intel"] = _Boom("external_intel")

    final = await run_intelligence_pipeline(objective="test", agents=agents)
    # Downstream stages still ran despite the failure.
    assert "synthesize" in final["stage_results"]
    assert "critique" in final["stage_results"]
    assert any("external_intel" in e for e in final["errors"])


# --- Timeline rendering (real metrics) -------------------------------------


async def test_timeline_publisher_posts_once_then_updates():
    client = _FakeSlackClient()
    publisher = MissionTimelinePublisher(client, channel="C1")
    await run_intelligence_pipeline(
        objective="test", agents=_stub_agents(), on_stage=publisher
    )
    # One initial post, then one update per stage (6).
    assert len(client.posts) == 1
    assert len(client.updates) == len(STAGE_ORDER)
    # Every update targets the same message ts.
    assert {u["ts"] for u in client.updates} == {"1700000000.000001"}


async def test_timeline_shows_real_claim_confidence_breakdown():
    final = await run_intelligence_pipeline(objective="test", agents=_stub_agents())
    blocks = mission_timeline_blocks(final)
    text = " ".join(
        b.get("text", {}).get("text", "")
        for b in blocks
        if isinstance(b.get("text"), dict)
    )
    # 2 claims: 1 verified_fact, 1 supported_inference — surfaced literally.
    assert "2 claims" in text
    assert "✅1" in text and "🟢1" in text


async def test_timeline_shows_real_dag_edge_count():
    final = await run_intelligence_pipeline(objective="test", agents=_stub_agents())
    blocks = mission_timeline_blocks(final)
    text = " ".join(
        b.get("text", {}).get("text", "")
        for b in blocks
        if isinstance(b.get("text"), dict)
    )
    # 3 tasks with 2 dependency edges (task1->0, task2->1).
    assert "3 tasks" in text
    assert "2 dependency edges" in text


async def test_timeline_flags_critique_risks():
    final = await run_intelligence_pipeline(objective="test", agents=_stub_agents())
    blocks = mission_timeline_blocks(final)
    text = " ".join(
        b.get("text", {}).get("text", "")
        for b in blocks
        if isinstance(b.get("text"), dict)
    )
    # 2 risk flags (1 SPOF + 1 unsupported assumption).
    assert "2 risk flags" in text


async def test_initial_timeline_all_pending():
    from beacon.agents.pipeline import _new_state

    state = _new_state(str(uuid.uuid4()), "obj", "", "", None)
    blocks = mission_timeline_blocks(state)
    text = " ".join(
        b.get("text", {}).get("text", "")
        for b in blocks
        if isinstance(b.get("text"), dict)
    )
    assert "queued" in text or "reasoning" in text  # nothing completed yet
