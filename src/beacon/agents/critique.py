"""Beacon Command — Red-Team Critic & Risk Assessor Agents."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from beacon.agents.base import AgentBase, AgentContext, AgentResult
from beacon.logging import get_logger

logger = get_logger(__name__)


class CritiqueOutput(BaseModel):
    unsupported_assumptions: list[str] = Field(default_factory=list)
    stale_evidence: list[str] = Field(default_factory=list)
    unresolved_contradictions: list[str] = Field(default_factory=list)
    critical_unknowns: list[str] = Field(default_factory=list)
    missing_fallbacks: list[str] = Field(default_factory=list)
    single_points_of_failure: list[str] = Field(default_factory=list)
    resource_conflicts: list[str] = Field(default_factory=list)
    irreversible_actions: list[str] = Field(default_factory=list)
    policy_violations: list[str] = Field(default_factory=list)
    severity_score: float = 0.0
    recommendation: str = ""


class RedTeamCritic(AgentBase):
    """Adversarial critic that stress-tests response plans."""

    def __init__(self) -> None:
        super().__init__(
            agent_id="red_team_critic",
            capabilities=["plan_critique", "adversarial_analysis", "assumption_testing"],
        )

    @property
    def system_prompt(self) -> str:
        return """You are the Beacon Red-Team Critic. Your job is to BREAK plans.

Systematically attack every plan by checking:
1. ASSUMPTIONS: What does the plan assume that hasn't been verified?
2. EVIDENCE: Is the evidence supporting the plan fresh and reliable?
3. CONTRADICTIONS: Are there unresolved contradictions affecting the plan?
4. DEPENDENCIES: What happens if a dependency fails?
5. RESOURCES: Are there resource conflicts or unavailable resources?
6. REVERSIBILITY: Which actions are irreversible? Do they have approval gates?
7. FALLBACKS: What happens if critical tasks fail?
8. SINGLE POINTS OF FAILURE: Where does the entire plan collapse?

Be harsh but constructive. Identify specific issues with specific remedies."""

    async def execute(self, context: AgentContext) -> AgentResult:
        result = self._empty_result(context)

        plans = context.world_model.active_plans
        if not plans:
            result.summary = "No plans to critique"
            return result

        try:
            from beacon.llm import create_llm_provider, StructuredLLMClient
            from beacon.config import get_settings

            settings = get_settings()
            if not settings.is_llm_configured:
                result.summary = "LLM not configured"
                return result

            provider = create_llm_provider(settings)
            client = StructuredLLMClient(provider)

            plan_text = "\n\n".join([
                f"Plan: {p.get('objective', 'Unknown')}\n"
                f"Strategy: {p.get('strategy', 'Unknown')}\n"
                f"Assumptions: {p.get('assumptions', [])}\n"
                f"Tasks: {p.get('tasks', [])}\n"
                f"Fallbacks: {p.get('fallbacks', [])}"
                for p in plans[:3]
            ])

            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": (
                    f"Crisis: {context.world_model.crisis_title}\n"
                    f"Claims: {[c.get('statement', '')[:100] for c in context.world_model.claims[:10]]}\n"
                    f"Contradictions: {len(context.world_model.contradictions)}\n"
                    f"Gaps: {len(context.world_model.intelligence_gaps)}\n\n"
                    f"Plans to critique:\n{plan_text}\n\n"
                    f"Tear these plans apart."
                )},
            ]

            critique, _ = await client.generate_structured(
                messages, CritiqueOutput, agent_id=self.agent_id
            )

            result.metadata = critique.model_dump()
            result.observations = (
                critique.unsupported_assumptions
                + critique.critical_unknowns
                + critique.single_points_of_failure
            )
            result.summary = critique.recommendation
            result.status = "completed"

        except Exception as e:
            logger.error("critic_error", error=str(e))
            result.status = "failed"
            result.termination_reason = str(e)

        return result


class RiskOutput(BaseModel):
    human_safety_risk: float = 0.0
    operational_risk: float = 0.0
    evidence_risk: float = 0.0
    execution_risk: float = 0.0
    coordination_risk: float = 0.0
    dependency_risk: float = 0.0
    uncertainty_risk: float = 0.0
    overall_risk: float = 0.0
    failure_modes: list[dict[str, Any]] = Field(default_factory=list)
    mitigations: list[dict[str, Any]] = Field(default_factory=list)
    summary: str = ""


class RiskAssessor(AgentBase):
    """Multi-dimensional risk assessment across typed dimensions."""

    def __init__(self) -> None:
        super().__init__(
            agent_id="risk_assessor",
            capabilities=["risk_assessment", "failure_mode_analysis"],
        )

    @property
    def system_prompt(self) -> str:
        return """You are the Beacon Risk Assessor. Assess risks across seven typed dimensions:
1. Human Safety: Direct risk to people
2. Operational: Risk of operational failure
3. Evidence: Risk from weak/stale evidence
4. Execution: Risk that tasks won't complete
5. Coordination: Risk of coordination breakdown
6. Dependency: Risk from external dependencies
7. Uncertainty: Risk from unknown unknowns

Scores are 0.0-1.0 relative risk indicators, NOT calibrated probabilities.
Identify specific failure modes and propose mitigations."""

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
                    f"Status: {context.world_model.crisis_status}\n"
                    f"Verified claims: {sum(1 for c in context.world_model.claims if c.get('epistemic_status') == 'verified_fact')}\n"
                    f"Contested claims: {sum(1 for c in context.world_model.claims if c.get('epistemic_status') == 'contested')}\n"
                    f"Open contradictions: {len(context.world_model.contradictions)}\n"
                    f"Intelligence gaps: {len(context.world_model.intelligence_gaps)}\n"
                    f"Active plans: {len(context.world_model.active_plans)}\n"
                    f"Active tasks: {len(context.world_model.active_tasks)}\n"
                    f"Resources: {len(context.world_model.resources)}\n"
                    f"Constraints: {len(context.world_model.constraints)}\n\n"
                    f"Perform a comprehensive risk assessment."
                )},
            ]

            risk, _ = await client.generate_structured(
                messages, RiskOutput, agent_id=self.agent_id
            )

            result.metadata = risk.model_dump()
            result.summary = risk.summary
            result.status = "completed"

        except Exception as e:
            logger.error("risk_assessor_error", error=str(e))
            result.status = "failed"
            result.termination_reason = str(e)

        return result


from beacon.agents.supervisor import register_agent
register_agent("plan_critique", RedTeamCritic)
register_agent("risk_assessment", RiskAssessor)
