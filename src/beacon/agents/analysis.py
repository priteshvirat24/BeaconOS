"""Beacon Command — Contradiction Hunter & Gap Hunter Agents."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from beacon.agents.base import AgentBase, AgentContext, AgentResult, ContradictionProposal, GapProposal
from beacon.logging import get_logger

logger = get_logger(__name__)


class ContradictionAnalysis(BaseModel):
    contradictions: list[dict[str, Any]] = Field(default_factory=list)
    consistency_score: float = 1.0
    summary: str = ""


class ContradictionHunter(AgentBase):
    """Actively searches for contradictions across claims and evidence."""

    def __init__(self) -> None:
        super().__init__(
            agent_id="contradiction_hunter",
            capabilities=["contradiction_detection", "consistency_analysis"],
        )

    @property
    def system_prompt(self) -> str:
        return """You are the Beacon Contradiction Hunter. Systematically compare claims and 
evidence to identify logical contradictions, temporal inconsistencies, and source conflicts.

For each contradiction found:
1. Identify the two conflicting statements
2. Explain the nature of the contradiction
3. Assess severity (how much does this affect decisions?)
4. Suggest which claim is more likely correct based on evidence quality"""

    async def execute(self, context: AgentContext) -> AgentResult:
        result = self._empty_result(context)

        claims = context.world_model.claims
        if len(claims) < 2:
            result.summary = "Insufficient claims for contradiction analysis"
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

            claims_text = "\n".join([
                f"Claim [{c.get('id', i)}] ({c.get('epistemic_status', 'unknown')}, "
                f"confidence={c.get('confidence', 0)}): {c.get('statement', '')}"
                for i, c in enumerate(claims[:20])
            ])

            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": (
                    f"Analyze these claims for contradictions:\n\n{claims_text}\n\n"
                    f"Evidence count: {len(context.world_model.evidence_items)}\n"
                    f"Known contradictions: {len(context.world_model.contradictions)}\n\n"
                    f"Find NEW contradictions not already identified."
                )},
            ]

            analysis, _ = await client.generate_structured(
                messages, ContradictionAnalysis, agent_id=self.agent_id
            )

            for contra in analysis.contradictions:
                result.contradiction_proposals.append(ContradictionProposal(
                    description=contra.get("description", ""),
                    claim_a_id=contra.get("claim_a_id"),
                    claim_b_id=contra.get("claim_b_id"),
                    severity=contra.get("severity", 0.5),
                ))

            result.summary = analysis.summary
            result.metadata = {"consistency_score": analysis.consistency_score}
            result.status = "completed"

        except Exception as e:
            logger.error("contradiction_hunter_error", error=str(e))
            result.status = "failed"
            result.termination_reason = str(e)

        return result


class GapAnalysis(BaseModel):
    gaps: list[dict[str, Any]] = Field(default_factory=list)
    coverage_assessment: str = ""
    critical_unknowns: list[str] = Field(default_factory=list)


class GapHunter(AgentBase):
    """Identifies critical information gaps that affect decision-making."""

    def __init__(self) -> None:
        super().__init__(
            agent_id="gap_hunter",
            capabilities=["gap_analysis", "information_need_identification"],
        )

    @property
    def system_prompt(self) -> str:
        return """You are the Beacon Gap Hunter. Identify what is NOT known that would change 
operational decisions. Prioritize gaps by:
1. Decision impact — would filling this gap change a plan or recommendation?
2. Urgency — how soon is this information needed?
3. Resolvability — can this gap realistically be filled?
4. Acquisition cost — what effort is required?

For each gap, suggest concrete acquisition strategies: Slack search, external API query,
targeted human request, or scheduled recheck."""

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

            claims_text = "\n".join([
                f"- [{c.get('epistemic_status', '?')}] {c.get('statement', '')[:200]}"
                for c in context.world_model.claims[:15]
            ])
            existing_gaps = "\n".join([
                f"- {g.get('question', '')[:200]}"
                for g in context.world_model.intelligence_gaps[:10]
            ])
            tasks_text = "\n".join([
                f"- {t.get('title', '')[:200]} ({t.get('status', '?')})"
                for t in context.world_model.active_tasks[:10]
            ])

            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": (
                    f"Crisis: {context.world_model.crisis_title}\n"
                    f"Objective: {context.objective}\n\n"
                    f"Known claims:\n{claims_text or 'None'}\n\n"
                    f"Active tasks:\n{tasks_text or 'None'}\n\n"
                    f"Already-identified gaps:\n{existing_gaps or 'None'}\n\n"
                    f"What critical information gaps remain? Focus on gaps NOT already identified."
                )},
            ]

            analysis, _ = await client.generate_structured(
                messages, GapAnalysis, agent_id=self.agent_id
            )

            for gap in analysis.gaps:
                result.gap_proposals.append(GapProposal(
                    question=gap.get("question", ""),
                    uncertainty_score=gap.get("uncertainty_score", 0.5),
                    decision_impact=gap.get("decision_impact", 0.5),
                    urgency=gap.get("urgency", 0.5),
                    candidate_strategies=gap.get("strategies", []),
                ))

            result.summary = analysis.coverage_assessment
            result.observations = analysis.critical_unknowns
            result.status = "completed"

        except Exception as e:
            logger.error("gap_hunter_error", error=str(e))
            result.status = "failed"
            result.termination_reason = str(e)

        return result


from beacon.agents.supervisor import register_agent
register_agent("contradiction_resolution", ContradictionHunter)
register_agent("gap_analysis", GapHunter)
