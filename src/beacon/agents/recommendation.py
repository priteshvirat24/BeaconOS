"""Beacon Command — Recommendation & Change Analysis Agents."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from beacon.agents.base import AgentBase, AgentContext, AgentResult
from beacon.logging import get_logger

logger = get_logger(__name__)


class RecommendationOutput(BaseModel):
    recommended_action: str = ""
    rationale: str = ""
    alternatives: list[dict[str, Any]] = Field(default_factory=list)
    evidence_citations: list[str] = Field(default_factory=list)
    unresolved_uncertainties: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    required_approvals: list[str] = Field(default_factory=list)
    expected_outcome: str = ""


class RecommendationAgent(AgentBase):
    """Produces evidence-grounded recommendations with citations."""

    def __init__(self) -> None:
        super().__init__(
            agent_id="recommendation_agent",
            capabilities=["recommendation", "evidence_citation"],
        )

    @property
    def system_prompt(self) -> str:
        return """You are the Beacon Recommendation Agent. Produce actionable recommendations 
backed by specific evidence citations. Every recommendation MUST:
1. Cite the specific claims/evidence that support it
2. Acknowledge what is uncertain
3. List alternatives considered
4. Specify what approvals are needed
5. State expected outcomes and how to verify them"""

    async def execute(self, context: AgentContext) -> AgentResult:
        result = self._empty_result(context)

        try:
            from beacon.llm import create_llm_provider, StructuredLLMClient
            from beacon.config import get_settings

            settings = get_settings()
            if not settings.is_llm_configured:
                result.summary = "LLM not configured"
                return result

            provider = create_llm_provider(settings)
            client = StructuredLLMClient(provider)

            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": (
                    f"Crisis: {context.world_model.crisis_title}\n"
                    f"Objective: {context.objective}\n\n"
                    f"Claims:\n" + "\n".join([
                        f"- [{c.get('id', '?')}] ({c.get('epistemic_status', '?')}, "
                        f"conf={c.get('confidence', 0):.1f}): {c.get('statement', '')[:200]}"
                        for c in context.world_model.claims[:15]
                    ]) + "\n\n"
                    f"Gaps: {[g.get('question', '')[:100] for g in context.world_model.intelligence_gaps[:5]]}\n"
                    f"Contradictions: {len(context.world_model.contradictions)}\n\n"
                    f"Generate an evidence-grounded recommendation."
                )},
            ]

            rec, _ = await client.generate_structured(
                messages, RecommendationOutput, agent_id=self.agent_id
            )

            result.decision_support = [rec.model_dump()]
            result.summary = rec.rationale[:500]
            result.status = "completed"

        except Exception as e:
            logger.error("recommendation_error", error=str(e))
            result.status = "failed"
            result.termination_reason = str(e)

        return result


class MaterialChangeOutput(BaseModel):
    is_material: bool = False
    materiality_score: float = 0.0
    affected_plans: list[str] = Field(default_factory=list)
    affected_tasks: list[str] = Field(default_factory=list)
    affected_decisions: list[str] = Field(default_factory=list)
    requires_replanning: bool = False
    summary: str = ""


class ChangeAnalyst(AgentBase):
    """Detects material changes and propagates their impact."""

    def __init__(self) -> None:
        super().__init__(
            agent_id="change_analyst",
            capabilities=["change_detection", "impact_propagation"],
        )

    @property
    def system_prompt(self) -> str:
        return """You are the Beacon Change Analyst. When new evidence or claim changes occur,
determine:
1. Is this a MATERIAL change? (Would it change any plan, task, or decision?)
2. What specific plans/tasks/decisions are affected?
3. Does this require replanning?
4. What is the urgency of addressing this change?

A change is material if ignoring it could lead to incorrect operational decisions."""

    async def execute(self, context: AgentContext) -> AgentResult:
        result = self._empty_result(context)

        try:
            from beacon.llm import create_llm_provider, StructuredLLMClient
            from beacon.config import get_settings

            settings = get_settings()
            if not settings.is_llm_configured:
                result.summary = "LLM not configured"
                return result

            provider = create_llm_provider(settings)
            client = StructuredLLMClient(provider)

            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": (
                    f"Crisis: {context.world_model.crisis_title}\n"
                    f"Change context: {context.objective}\n\n"
                    f"Current claims: {[c.get('statement', '')[:100] for c in context.world_model.claims[:10]]}\n"
                    f"Active plans: {len(context.world_model.active_plans)}\n"
                    f"Active tasks: {len(context.world_model.active_tasks)}\n\n"
                    f"Assess materiality of this change."
                )},
            ]

            change, _ = await client.generate_structured(
                messages, MaterialChangeOutput, agent_id=self.agent_id
            )

            result.metadata = change.model_dump()
            result.summary = change.summary

            if change.requires_replanning:
                result.mission_proposals.append({
                    "mission_type": "replanning",
                    "objective": f"Replan due to material change: {change.summary}",
                    "priority": change.materiality_score,
                })

            result.status = "completed"

        except Exception as e:
            logger.error("change_analyst_error", error=str(e))
            result.status = "failed"
            result.termination_reason = str(e)

        return result


from beacon.agents.supervisor import register_agent
register_agent("recommendation", RecommendationAgent)
register_agent("change_analysis", ChangeAnalyst)
