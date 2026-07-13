"""Beacon Command — Supervisor Graph (LangGraph).

Orchestrates agent missions via a LangGraph state machine with PostgreSQL checkpointing.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from beacon.agents.base import AgentBase, AgentContext, AgentResult, AgentBudget, PolicyContext, WorldModelSlice
from beacon.logging import get_logger

logger = get_logger(__name__)


class SupervisorState(BaseModel):
    """LangGraph state for the supervisor graph."""

    mission_id: str = ""
    crisis_id: str = ""
    objective: str = ""
    mission_type: str = ""
    status: str = "created"

    # Agent execution
    assigned_agent: str = ""
    agent_result: Optional[dict[str, Any]] = None
    iteration: int = 0
    max_iterations: int = 12

    # Outputs
    evidence_candidates: list[dict[str, Any]] = Field(default_factory=list)
    claim_proposals: list[dict[str, Any]] = Field(default_factory=list)
    gap_proposals: list[dict[str, Any]] = Field(default_factory=list)
    mission_proposals: list[dict[str, Any]] = Field(default_factory=list)
    observations: list[str] = Field(default_factory=list)

    # Tracking
    tools_used: int = 0
    tool_budget: int = 12
    errors: list[str] = Field(default_factory=list)
    completion_reason: str = ""


# --- Agent Registry ---

_AGENT_REGISTRY: dict[str, type[AgentBase]] = {}


def register_agent(mission_type: str, agent_cls: type[AgentBase]) -> None:
    """Register an agent class for a mission type."""
    _AGENT_REGISTRY[mission_type] = agent_cls


def get_agent_for_mission(mission_type: str) -> Optional[AgentBase]:
    """Get an agent instance for the given mission type."""
    cls = _AGENT_REGISTRY.get(mission_type)
    if cls:
        return cls()
    return None


# --- Register built-in agents ---

def _register_builtin_agents() -> None:
    """Register all built-in agents."""
    from beacon.agents.triage import TriageAgent
    from beacon.agents.workspace_investigator import WorkspaceInvestigator

    register_agent("triage", TriageAgent)
    register_agent("workspace_investigation", WorkspaceInvestigator)


# --- Supervisor Node Functions ---

async def route_mission(state: dict[str, Any]) -> dict[str, Any]:
    """Route a mission to the appropriate agent."""
    _register_builtin_agents()

    mission_type = state.get("mission_type", "")
    agent = get_agent_for_mission(mission_type)

    if not agent:
        return {
            **state,
            "status": "failed",
            "completion_reason": f"No agent registered for mission type: {mission_type}",
        }

    return {**state, "assigned_agent": agent.agent_id, "status": "running"}


async def execute_agent(state: dict[str, Any]) -> dict[str, Any]:
    """Execute the assigned agent."""
    _register_builtin_agents()

    mission_type = state.get("mission_type", "")
    agent = get_agent_for_mission(mission_type)

    if not agent:
        return {**state, "status": "failed", "completion_reason": "Agent not found"}

    # Build context
    context = AgentContext(
        mission_id=uuid.UUID(state["mission_id"]) if state.get("mission_id") else uuid.uuid4(),
        mission_type=mission_type,
        objective=state.get("objective", ""),
        world_model=WorldModelSlice(
            crisis_id=uuid.UUID(state["crisis_id"]) if state.get("crisis_id") else None,
        ),
        budget=AgentBudget(
            tool_budget=state.get("tool_budget", 12),
            tools_used=state.get("tools_used", 0),
        ),
        policy=PolicyContext(),
    )

    try:
        result = await agent.execute(context)

        return {
            **state,
            "agent_result": result.model_dump(),
            "evidence_candidates": [e.model_dump() for e in result.evidence_candidates],
            "claim_proposals": [c.model_dump() for c in result.claim_proposals],
            "gap_proposals": [g.model_dump() for g in result.gap_proposals],
            "mission_proposals": result.mission_proposals,
            "observations": result.observations,
            "tools_used": context.budget.tools_used,
            "status": result.status,
            "completion_reason": result.termination_reason,
            "iteration": state.get("iteration", 0) + 1,
        }
    except Exception as e:
        logger.error("agent_execution_error", agent=agent.agent_id, error=str(e))
        return {
            **state,
            "status": "failed",
            "completion_reason": f"Agent execution error: {e}",
            "errors": state.get("errors", []) + [str(e)],
        }


async def evaluate_termination(state: dict[str, Any]) -> dict[str, Any]:
    """Evaluate whether the mission should continue or terminate."""
    if state.get("status") in ("completed", "failed"):
        return state

    if state.get("iteration", 0) >= state.get("max_iterations", 12):
        return {**state, "status": "completed", "completion_reason": "max_iterations_reached"}

    if state.get("tools_used", 0) >= state.get("tool_budget", 12):
        return {**state, "status": "completed", "completion_reason": "budget_exhausted"}

    return state


def should_continue(state: dict[str, Any]) -> str:
    """Routing function: continue execution or end."""
    if state.get("status") in ("completed", "failed"):
        return "end"
    return "continue"


def build_supervisor_graph() -> Any:
    """Build the LangGraph supervisor state graph."""
    try:
        from langgraph.graph import StateGraph, END

        builder = StateGraph(dict)

        builder.add_node("route", route_mission)
        builder.add_node("execute", execute_agent)
        builder.add_node("evaluate", evaluate_termination)

        builder.set_entry_point("route")
        builder.add_edge("route", "execute")
        builder.add_edge("execute", "evaluate")
        builder.add_conditional_edges(
            "evaluate",
            should_continue,
            {"continue": "execute", "end": END},
        )

        return builder.compile()

    except ImportError:
        logger.warning("langgraph_not_available")
        return None


async def run_mission(
    mission_id: uuid.UUID,
    mission_type: str,
    objective: str,
    *,
    crisis_id: Optional[uuid.UUID] = None,
    tool_budget: int = 12,
) -> dict[str, Any]:
    """Run a mission through the supervisor graph.

    This is the primary entry point for launching agent missions.
    """
    graph = build_supervisor_graph()

    initial_state = {
        "mission_id": str(mission_id),
        "crisis_id": str(crisis_id) if crisis_id else "",
        "objective": objective,
        "mission_type": mission_type,
        "tool_budget": tool_budget,
        "status": "created",
        "iteration": 0,
        "max_iterations": 12,
        "tools_used": 0,
    }

    if graph:
        try:
            final_state = await graph.ainvoke(initial_state)
            return final_state
        except Exception as e:
            logger.error("supervisor_graph_error", error=str(e))
            return {**initial_state, "status": "failed", "completion_reason": str(e)}
    else:
        # Fallback without LangGraph
        _register_builtin_agents()
        agent = get_agent_for_mission(mission_type)
        if not agent:
            return {**initial_state, "status": "failed", "completion_reason": "No agent available"}

        context = AgentContext(
            mission_id=mission_id,
            mission_type=mission_type,
            objective=objective,
            world_model=WorldModelSlice(crisis_id=crisis_id),
            budget=AgentBudget(tool_budget=tool_budget),
            policy=PolicyContext(),
        )

        result = await agent.execute(context)
        return {
            **initial_state,
            "status": result.status,
            "completion_reason": result.termination_reason,
            "agent_result": result.model_dump(),
        }
