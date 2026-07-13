"""Beacon Command — Intelligence Pipeline (multi-agent LangGraph chain).

This module wires Beacon's six agents into a *single, real* LangGraph pipeline
in which each stage's output feeds the next:

    triage -> investigate (Slack RTS) -> external_intel (hazard APIs)
           -> synthesize (claims) -> plan (task DAG) -> critique (risk flags)

Unlike the per-mission supervisor (which routes one agent per mission), this
graph threads an *accumulating world model* through all stages: the synthesizer
sees the investigator's evidence, the planner sees the synthesizer's claims, and
the critic sees the planner's plan. That accumulation is what makes the
multi-agent reasoning genuine rather than six disconnected LLM calls.

The Mission Timeline surface is driven directly off ``graph.astream(...,
stream_mode="updates")`` — i.e. off real node completions and real merged
state — so the on-screen trace reflects actual graph execution, never a scripted
sequence. See :mod:`beacon.slack.mission_timeline`.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from beacon.agents.base import (
    AgentBase,
    AgentBudget,
    AgentContext,
    AgentResult,
    PolicyContext,
    WorldModelSlice,
)
from beacon.logging import get_logger

logger = get_logger(__name__)


# --- Stage definitions -----------------------------------------------------

# Ordered pipeline. Each stage: (node_id, human label, emoji, agent factory).
# Factories are lazy so importing this module doesn't pull every agent eagerly.
def _stage_agents() -> dict[str, AgentBase]:
    from beacon.agents.critique import RedTeamCritic
    from beacon.agents.evidence_synthesizer import EvidenceSynthesizer
    from beacon.agents.external_intelligence import ExternalIntelligenceAgent
    from beacon.agents.planner import PlannerAgent
    from beacon.agents.triage import TriageAgent
    from beacon.agents.workspace_investigator import WorkspaceInvestigator

    return {
        "triage": TriageAgent(),
        "investigate": WorkspaceInvestigator(),
        "external_intel": ExternalIntelligenceAgent(),
        "synthesize": EvidenceSynthesizer(),
        "plan": PlannerAgent(),
        "critique": RedTeamCritic(),
    }


# (node_id, label, emoji) in execution order. The single source of truth for
# both the graph topology and the timeline rendering.
PIPELINE_STAGES: tuple[tuple[str, str, str], ...] = (
    ("triage", "Triage", "🧭"),
    ("investigate", "Workspace Investigator", "🔎"),
    ("external_intel", "External Intel", "🌐"),
    ("synthesize", "Evidence Synthesizer", "🧪"),
    ("plan", "Response Planner", "🗺️"),
    ("critique", "Red-Team Critic", "🛡️"),
)
STAGE_ORDER: tuple[str, ...] = tuple(s[0] for s in PIPELINE_STAGES)
STAGE_LABELS: dict[str, str] = {s[0]: s[1] for s in PIPELINE_STAGES}
STAGE_EMOJI: dict[str, str] = {s[0]: s[2] for s in PIPELINE_STAGES}


# --- State helpers ---------------------------------------------------------

def _new_state(
    mission_id: str,
    objective: str,
    crisis_id: str,
    crisis_title: str,
    seed_evidence: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    seed = seed_evidence or []
    severity_score = seed[0].get("severity_score") if seed else None
    return {
        "mission_id": mission_id,
        "crisis_id": crisis_id,
        "crisis_title": crisis_title,
        "objective": objective,
        "severity_score": severity_score,
        "evidence_items": list(seed),
        "claims": [],
        "contradictions": [],
        "gaps": [],
        "plans": [],
        # per-stage rollup used by the timeline; keyed by node_id
        "stage_results": {},
        "errors": [],
    }


def _context_from_state(state: dict[str, Any], mission_type: str) -> AgentContext:
    """Build an AgentContext reflecting everything accumulated so far."""
    crisis_id = state.get("crisis_id") or ""
    return AgentContext(
        mission_id=uuid.UUID(state["mission_id"]),
        mission_type=mission_type,
        objective=state.get("objective", ""),
        world_model=WorldModelSlice(
            crisis_id=uuid.UUID(crisis_id) if crisis_id else None,
            crisis_title=state.get("crisis_title") or None,
            evidence_items=state.get("evidence_items", []),
            claims=state.get("claims", []),
            contradictions=state.get("contradictions", []),
            intelligence_gaps=state.get("gaps", []),
            active_plans=state.get("plans", []),
        ),
        budget=AgentBudget(tool_budget=12),
        policy=PolicyContext(),
    )


def _merge_result(node_id: str, state: dict[str, Any], result: AgentResult) -> None:
    """Fold an agent's typed result into the accumulating pipeline state."""
    # Evidence — assign stable ids so downstream stages can cite them.
    for ev in result.evidence_candidates:
        idx = len(state["evidence_items"]) + 1
        item = ev.model_dump()
        item["id"] = item.get("raw_content_hash") or f"ev-{idx}"
        state["evidence_items"].append(item)

    for claim in result.claim_proposals:
        state["claims"].append(claim.model_dump())
    for contra in result.contradiction_proposals:
        state["contradictions"].append(contra.model_dump())
    for gap in result.gap_proposals:
        state["gaps"].append(gap if isinstance(gap, dict) else gap.model_dump())
    for plan in result.plan_proposals:
        state["plans"].append(plan)

    state["stage_results"][node_id] = {
        "status": result.status,
        "summary": result.summary,
        "observations": result.observations[-5:],
        "metadata": result.metadata,
        "metrics": _stage_metrics(node_id, state, result),
    }
    if result.status == "failed" and result.termination_reason:
        state["errors"].append(f"{node_id}: {result.termination_reason}")


def _dag_edge_count(plans: list[dict[str, Any]]) -> int:
    edges = 0
    for plan in plans:
        for task in plan.get("tasks", []):
            edges += len(task.get("dependencies", []) or [])
    return edges


def _claims_by_status(claims: list[dict[str, Any]]) -> dict[str, int]:
    counts = {
        "verified_fact": 0,
        "supported_inference": 0,
        "weak_inference": 0,
        "contested": 0,
    }
    for c in claims:
        status = c.get("epistemic_status", "unknown")
        if status in counts:
            counts[status] += 1
    return counts


def _stage_metrics(
    node_id: str, state: dict[str, Any], result: AgentResult
) -> dict[str, Any]:
    """Compute the real headline metrics for a stage from merged state."""
    if node_id == "triage":
        md = result.metadata or {}
        return {
            "severity": md.get("severity_assessment", "n/a"),
            "should_create_crisis": bool(md.get("should_create_crisis")),
            "recommended_missions": len(result.mission_proposals),
            "initial_questions": len(result.gap_proposals),
        }
    if node_id in ("investigate", "external_intel"):
        return {
            "evidence_added": len(result.evidence_candidates),
            "evidence_total": len(state["evidence_items"]),
            "searches": sum(
                1 for t in result.tool_traces if t.status == "success"
            ),
        }
    if node_id == "synthesize":
        counts = _claims_by_status(state["claims"])
        return {
            "claims_total": len(state["claims"]),
            **counts,
            "contradictions": len(state["contradictions"]),
        }
    if node_id == "plan":
        tasks = sum(len(p.get("tasks", [])) for p in state["plans"])
        return {
            "tasks": tasks,
            "dag_edges": _dag_edge_count(state["plans"]),
        }
    if node_id == "critique":
        md = result.metadata or {}
        risk_flags = (
            len(md.get("single_points_of_failure", []) or [])
            + len(md.get("unsupported_assumptions", []) or [])
            + len(md.get("irreversible_actions", []) or [])
            + len(md.get("unresolved_contradictions", []) or [])
        )
        return {
            "risk_flags": risk_flags,
            "severity_score": md.get("severity_score", 0.0),
            "spofs": len(md.get("single_points_of_failure", []) or []),
        }
    return {}


# --- Graph construction ----------------------------------------------------

def build_pipeline_graph(agents: dict[str, AgentBase]) -> Any:
    """Build the linear multi-agent LangGraph pipeline.

    Each node runs one agent against the *current* accumulated state and folds
    its result back in. A node that raises is recorded and the pipeline
    proceeds (partial intelligence beats a dead pipeline in a crisis).
    """
    from langgraph.graph import END, StateGraph

    def make_node(node_id: str) -> Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]:
        agent = agents[node_id]

        async def node(state: dict[str, Any]) -> dict[str, Any]:
            try:
                ctx = _context_from_state(state, mission_type=node_id)
                result = await agent.execute(ctx)
            except Exception as e:  # noqa: BLE001 - resilience by design
                logger.error("pipeline_stage_error", stage=node_id, error=str(e))
                state["errors"].append(f"{node_id}: {e}")
                state["stage_results"][node_id] = {
                    "status": "failed",
                    "summary": str(e),
                    "observations": [],
                    "metadata": {},
                    "metrics": {},
                }
                return state
            _merge_result(node_id, state, result)
            return state

        return node

    # LangGraph's StateGraph generics don't accept a plain ``dict`` state type;
    # the runtime handles it fine (as the existing supervisor graph also does).
    builder = StateGraph(dict)  # type: ignore[type-var]
    for node_id in STAGE_ORDER:
        builder.add_node(node_id, make_node(node_id))  # type: ignore[call-overload]
    builder.set_entry_point(STAGE_ORDER[0])
    for a, b in zip(STAGE_ORDER, STAGE_ORDER[1:], strict=False):
        builder.add_edge(a, b)
    builder.add_edge(STAGE_ORDER[-1], END)
    return builder.compile()


# Callback signature: (completed_node_id | None, state) -> awaitable.
# Called once with ``None`` before execution (all-pending), then after each
# real graph node completes.
StageCallback = Callable[[str | None, dict[str, Any]], Awaitable[None]]


async def run_intelligence_pipeline(
    *,
    objective: str,
    mission_id: uuid.UUID | None = None,
    crisis_id: uuid.UUID | None = None,
    crisis_title: str = "",
    seed_evidence: list[dict[str, Any]] | None = None,
    agents: dict[str, AgentBase] | None = None,
    on_stage: StageCallback | None = None,
) -> dict[str, Any]:
    """Run the full multi-agent pipeline, invoking ``on_stage`` per real node.

    Args:
        objective: Mission objective threaded to every agent.
        mission_id: Optional pre-allocated mission id.
        crisis_id / crisis_title: Optional crisis association.
        seed_evidence: Optional pre-seeded evidence (used by scenario replays).
        agents: Optional agent override (tests inject deterministic stubs).
            The graph itself still executes for real.
        on_stage: Async callback fired before execution (node=None) and after
            each node completes, receiving the live merged state.

    Returns:
        The final accumulated pipeline state.
    """
    mission_id = mission_id or uuid.uuid4()
    agents = agents or _stage_agents()
    graph = build_pipeline_graph(agents)

    state = _new_state(
        mission_id=str(mission_id),
        objective=objective,
        crisis_id=str(crisis_id) if crisis_id else "",
        crisis_title=crisis_title,
        seed_evidence=seed_evidence,
    )

    if on_stage is not None:
        await on_stage(None, state)

    async for chunk in graph.astream(state, stream_mode="updates"):
        # ``updates`` yields {node_id: full_returned_state} per completed node.
        for node_id, node_state in chunk.items():
            state = node_state
            if on_stage is not None:
                await on_stage(node_id, state)
            # Pace requests for Gemini Free Tier rate limit (15 requests per minute)
            import asyncio
            await asyncio.sleep(6)

    logger.info(
        "pipeline_completed",
        mission_id=str(mission_id),
        evidence=len(state["evidence_items"]),
        claims=len(state["claims"]),
        errors=len(state["errors"]),
    )
    return state
