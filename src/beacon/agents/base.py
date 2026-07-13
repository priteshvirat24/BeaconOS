"""Beacon Command — Agent Base & Runtime Contract.

Every agent follows the same runtime contract defined here.
Agents receive typed context and produce typed results.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field

from beacon.logging import get_logger

logger = get_logger(__name__)


# --- Agent Input Contracts ---

class AgentBudget(BaseModel):
    """Budget constraints for an agent execution."""

    tool_budget: int = 12
    token_budget: Optional[int] = None
    timeout_seconds: int = 120
    tools_used: int = 0
    tokens_used: int = 0

    @property
    def tool_budget_remaining(self) -> int:
        return max(0, self.tool_budget - self.tools_used)

    @property
    def is_budget_exhausted(self) -> bool:
        return self.tools_used >= self.tool_budget


class PolicyContext(BaseModel):
    """Policy constraints for agent behavior."""

    human_approval_required: bool = True
    auto_create_crisis_channel: bool = False
    auto_create_draft_tasks: bool = False
    max_authority_level: str = "L1_RECOMMEND"
    prompt_version: int = 1


class MemoryContext(BaseModel):
    """Memory context from episodic and semantic memory."""

    similar_episodes: list[dict[str, Any]] = Field(default_factory=list)
    relevant_procedures: list[dict[str, Any]] = Field(default_factory=list)
    organizational_knowledge: list[dict[str, Any]] = Field(default_factory=list)


class WorldModelSlice(BaseModel):
    """Relevant slice of the world model for an agent's mission."""

    crisis_id: Optional[uuid.UUID] = None
    crisis_title: Optional[str] = None
    crisis_status: Optional[str] = None
    evidence_items: list[dict[str, Any]] = Field(default_factory=list)
    claims: list[dict[str, Any]] = Field(default_factory=list)
    contradictions: list[dict[str, Any]] = Field(default_factory=list)
    intelligence_gaps: list[dict[str, Any]] = Field(default_factory=list)
    hypotheses: list[dict[str, Any]] = Field(default_factory=list)
    active_tasks: list[dict[str, Any]] = Field(default_factory=list)
    active_plans: list[dict[str, Any]] = Field(default_factory=list)
    resources: list[dict[str, Any]] = Field(default_factory=list)
    constraints: list[dict[str, Any]] = Field(default_factory=list)


class AgentContext(BaseModel):
    """Full context provided to an agent for execution."""

    mission_id: uuid.UUID
    mission_type: str
    objective: str
    world_model: WorldModelSlice
    allowed_tools: list[str] = Field(default_factory=list)
    budget: AgentBudget
    policy: PolicyContext
    memory: MemoryContext = Field(default_factory=MemoryContext)
    correlation_id: str = ""
    trace_id: str = ""


# --- Agent Output Contracts ---

class EvidenceCandidate(BaseModel):
    """Proposed evidence item from agent observation."""

    source_type: str
    source_provider: str
    normalized_content: str
    raw_content_hash: str
    source_uri: Optional[str] = None
    slack_permalink: Optional[str] = None
    reliability_score: float = 0.5
    geographic_scope: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ClaimProposal(BaseModel):
    """Proposed claim from evidence synthesis."""

    statement: str
    normalized_subject: Optional[str] = None
    predicate: Optional[str] = None
    object_: Optional[str] = None
    epistemic_status: str = "unknown"
    confidence: float = 0.0
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class GapProposal(BaseModel):
    """Proposed intelligence gap."""

    question: str
    uncertainty_score: float = 0.5
    decision_impact: float = 0.5
    urgency: float = 0.5
    candidate_strategies: list[str] = Field(default_factory=list)


class ContradictionProposal(BaseModel):
    """Proposed contradiction between claims."""

    description: str
    claim_a_id: Optional[str] = None
    claim_b_id: Optional[str] = None
    severity: float = 0.5


class ToolTrace(BaseModel):
    """Record of a tool invocation during agent execution."""

    tool_name: str
    input_params: dict[str, Any] = Field(default_factory=dict)
    output_summary: str = ""
    latency_ms: int = 0
    status: str = "success"
    error: Optional[str] = None


class AgentResult(BaseModel):
    """Typed result from agent execution."""

    mission_id: uuid.UUID
    agent_id: str
    status: str = "completed"  # completed, failed, budget_exhausted, timed_out
    termination_reason: str = ""

    observations: list[str] = Field(default_factory=list)
    evidence_candidates: list[EvidenceCandidate] = Field(default_factory=list)
    claim_proposals: list[ClaimProposal] = Field(default_factory=list)
    gap_proposals: list[GapProposal] = Field(default_factory=list)
    contradiction_proposals: list[ContradictionProposal] = Field(default_factory=list)
    hypothesis_updates: list[dict[str, Any]] = Field(default_factory=list)
    plan_proposals: list[dict[str, Any]] = Field(default_factory=list)
    decision_support: list[dict[str, Any]] = Field(default_factory=list)
    mission_proposals: list[dict[str, Any]] = Field(default_factory=list)
    state_patch: Optional[dict[str, Any]] = None
    tool_traces: list[ToolTrace] = Field(default_factory=list)

    summary: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


# --- Agent Base Class ---

class AgentBase(ABC):
    """Abstract base for all Beacon agents.

    Enforces the runtime contract:
    - Typed input (AgentContext)
    - Typed output (AgentResult)
    - Budget tracking
    - Structured LLM calls
    - Tool tracing
    """

    def __init__(self, agent_id: str, capabilities: list[str]):
        self.agent_id = agent_id
        self.capabilities = capabilities

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """System prompt for this agent type."""
        ...

    @abstractmethod
    async def execute(self, context: AgentContext) -> AgentResult:
        """Execute the agent's mission.

        Args:
            context: Full agent context with mission, world model, budget, and policy.

        Returns:
            Typed AgentResult with observations, proposals, and traces.
        """
        ...

    def _empty_result(self, context: AgentContext, status: str = "completed") -> AgentResult:
        """Create an empty result with basic fields populated."""
        return AgentResult(
            mission_id=context.mission_id,
            agent_id=self.agent_id,
            status=status,
        )
