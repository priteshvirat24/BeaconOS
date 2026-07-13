"""Beacon Command — Planner Agent.

Generates structured response plans as task DAGs with proper evidence grounding.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from beacon.agents.base import AgentBase, AgentContext, AgentResult
from beacon.logging import get_logger

logger = get_logger(__name__)


class PlanTaskSpec(BaseModel):
    """Specification for a single plan task."""

    objective: str = ""
    assigned_role: str = ""
    estimated_duration_minutes: int = 60
    required_resources: list[str] = Field(default_factory=list)
    required_claims: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    failure_conditions: list[str] = Field(default_factory=list)
    reversibility: str = "reversible"
    dependencies: list[int] = Field(default_factory=list)  # indices of other tasks


class PlanOutput(BaseModel):
    """Structured output for plan generation."""

    objective: str = ""
    strategy: str = ""
    assumptions: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    tasks: list[PlanTaskSpec] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    failure_conditions: list[str] = Field(default_factory=list)
    fallbacks: list[str] = Field(default_factory=list)
    risk_summary: str = ""
    unresolved_questions: list[str] = Field(default_factory=list)


class PlannerAgent(AgentBase):
    """Generates structured response plans."""

    def __init__(self) -> None:
        super().__init__(
            agent_id="planner_agent",
            capabilities=["plan_generation", "task_dag_construction"],
        )

    @property
    def system_prompt(self) -> str:
        return """You are the Beacon Planner Agent. You generate structured crisis response plans.

CRITICAL RULES:
1. Plans must be evidence-grounded. Cite claims that support plan assumptions.
2. Tasks must form a valid DAG (no cycles).
3. Each task must have success criteria and failure conditions.
4. Include fallback plans for each critical path task.
5. Respect identified constraints (resources, access, timing).
6. Flag assumptions that haven't been verified.
7. Be specific about resources needed and roles required.
8. Every irreversible action must have explicit approval requirements.

Output a structured plan with tasks, dependencies, and risk assessment."""

    async def execute(self, context: AgentContext) -> AgentResult:
        """Execute plan generation."""
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

            # Build context prompt
            claims_text = "\n".join([
                f"- [{c.get('epistemic_status', 'unknown')}] {c.get('statement', '')}"
                for c in context.world_model.claims[:15]
            ])
            resources_text = "\n".join([
                f"- {r.get('name', '')} ({r.get('status', 'unknown')})"
                for r in context.world_model.resources[:10]
            ])
            constraints_text = "\n".join([
                f"- {c.get('description', '')}"
                for c in context.world_model.constraints[:10]
            ])

            messages = [
                {"role": "system", "content": self.system_prompt},
                {
                    "role": "user",
                    "content": (
                        f"Crisis: {context.world_model.crisis_title}\n"
                        f"Status: {context.world_model.crisis_status}\n"
                        f"Objective: {context.objective}\n\n"
                        f"Known claims:\n{claims_text or 'None yet'}\n\n"
                        f"Available resources:\n{resources_text or 'None identified'}\n\n"
                        f"Known constraints:\n{constraints_text or 'None identified'}\n\n"
                        f"Active tasks:\n{[t.get('title', '') for t in context.world_model.active_tasks[:10]]}\n\n"
                        f"Generate a structured response plan."
                    ),
                },
            ]

            plan_output, record = await client.generate_structured(
                messages, PlanOutput, agent_id=self.agent_id
            )

            result.plan_proposals = [plan_output.model_dump()]
            result.gap_proposals = [
                {"question": q, "urgency": 0.6, "decision_impact": 0.7}
                for q in plan_output.unresolved_questions
            ]
            result.summary = f"Generated plan: {plan_output.objective} with {len(plan_output.tasks)} tasks"
            result.status = "completed"

        except Exception as e:
            logger.error("planner_error", error=str(e))
            result.status = "failed"
            result.termination_reason = str(e)

        return result


from beacon.agents.supervisor import register_agent
register_agent("plan_generation", PlannerAgent)
