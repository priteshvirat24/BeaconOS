"""Beacon Command — Evidence Synthesizer Agent.

Synthesizes evidence into structured claims with epistemic status assessment.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from beacon.agents.base import (
    AgentBase,
    AgentContext,
    AgentResult,
    ClaimProposal,
    ContradictionProposal,
    GapProposal,
)
from beacon.logging import get_logger

logger = get_logger(__name__)


class SynthesisOutput(BaseModel):
    """Structured output from evidence synthesis."""

    claims: list[dict[str, Any]] = Field(default_factory=list)
    contradictions: list[dict[str, Any]] = Field(default_factory=list)
    gaps: list[dict[str, Any]] = Field(default_factory=list)
    summary: str = ""
    confidence_assessment: str = ""


class EvidenceSynthesizer(AgentBase):
    """Synthesizes evidence items into structured claims.

    Does NOT generate claims from thin air — every claim must cite specific evidence.
    Identifies contradictions and information gaps across the evidence set.
    """

    def __init__(self) -> None:
        super().__init__(
            agent_id="evidence_synthesizer",
            capabilities=["evidence_synthesis", "claim_creation", "contradiction_detection"],
        )

    @property
    def system_prompt(self) -> str:
        return """You are the Beacon Evidence Synthesizer. Your role is to analyze evidence items
and produce structured claims with proper epistemic status.

CRITICAL RULES:
1. Every claim MUST cite specific evidence. No claim may exist without supporting evidence.
2. Assign epistemic status honestly: verified_fact, supported_inference, weak_inference, unknown.
3. Confidence scores must reflect actual evidence strength, not desired certainty.
4. Flag ANY contradictions between evidence items.
5. Identify information gaps — what is NOT known that would change decisions.
6. Do not hallucinate claims. If evidence is ambiguous, say so.
7. Track source diversity — claims supported by multiple independent sources are stronger.

For each claim, provide:
- A clear, specific statement
- Subject-predicate-object structure where possible
- Confidence score (0.0-1.0)
- Epistemic status
- IDs of supporting evidence

Respond in the required JSON schema."""

    async def execute(self, context: AgentContext) -> AgentResult:
        """Execute evidence synthesis."""
        result = self._empty_result(context)

        evidence_items = context.world_model.evidence_items
        if not evidence_items:
            result.status = "completed"
            result.summary = "No evidence to synthesize"
            return result

        try:
            from beacon.llm import create_llm_provider, StructuredLLMClient
            from beacon.config import get_settings

            settings = get_settings()
            if not settings.is_llm_configured:
                result.summary = "LLM not configured, cannot synthesize"
                return result

            provider = create_llm_provider(settings)
            client = StructuredLLMClient(provider)

            # Prepare evidence summaries
            evidence_text = "\n\n".join([
                f"Evidence [{e.get('id', 'unknown')}]:\n"
                f"  Source: {e.get('source_type', 'unknown')} / {e.get('source_provider', 'unknown')}\n"
                f"  Content: {e.get('normalized_content', '')[:500]}\n"
                f"  Reliability: {e.get('reliability_score', 0.5)}\n"
                f"  Observed: {e.get('observed_at', 'unknown')}"
                for e in evidence_items[:20]  # Limit to avoid context overflow
            ])

            messages = [
                {"role": "system", "content": self.system_prompt},
                {
                    "role": "user",
                    "content": (
                        f"Crisis: {context.world_model.crisis_title or 'Unknown'}\n"
                        f"Objective: {context.objective}\n\n"
                        f"Evidence items to synthesize:\n{evidence_text}\n\n"
                        f"Existing claims: {[c.get('statement', '')[:100] for c in context.world_model.claims[:10]]}\n\n"
                        f"Synthesize these into structured claims. Identify contradictions and gaps."
                    ),
                },
            ]

            synthesis, record = await client.generate_structured(
                messages, SynthesisOutput, agent_id=self.agent_id
            )

            # Convert to typed proposals
            for claim_data in synthesis.claims:
                result.claim_proposals.append(ClaimProposal(
                    statement=claim_data.get("statement", ""),
                    normalized_subject=claim_data.get("subject"),
                    predicate=claim_data.get("predicate"),
                    object_=claim_data.get("object"),
                    epistemic_status=claim_data.get("epistemic_status", "unknown"),
                    confidence=claim_data.get("confidence", 0.0),
                    supporting_evidence_ids=claim_data.get("evidence_ids", []),
                ))

            for contra in synthesis.contradictions:
                result.contradiction_proposals.append(ContradictionProposal(
                    description=contra.get("description", ""),
                    claim_a_id=contra.get("claim_a_id"),
                    claim_b_id=contra.get("claim_b_id"),
                    severity=contra.get("severity", 0.5),
                ))

            for gap in synthesis.gaps:
                result.gap_proposals.append(GapProposal(
                    question=gap.get("question", ""),
                    uncertainty_score=gap.get("uncertainty_score", 0.5),
                    decision_impact=gap.get("decision_impact", 0.5),
                    urgency=gap.get("urgency", 0.5),
                ))

            result.summary = synthesis.summary
            result.status = "completed"

        except Exception as e:
            logger.error("synthesis_error", error=str(e))
            result.status = "failed"
            result.termination_reason = str(e)

        return result


# Register with supervisor
from beacon.agents.supervisor import register_agent
register_agent("evidence_synthesis", EvidenceSynthesizer)
