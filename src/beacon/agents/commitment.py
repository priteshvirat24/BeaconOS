"""Beacon Command — Commitment Agent & Reconciliation Agent."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from beacon.agents.base import AgentBase, AgentContext, AgentResult
from beacon.logging import get_logger

logger = get_logger(__name__)


class CommitmentOutput(BaseModel):
    commitments: list[dict[str, Any]] = Field(default_factory=list)
    summary: str = ""


class CommitmentAgent(AgentBase):
    """Detects operational commitments from Slack message content."""

    def __init__(self) -> None:
        super().__init__(
            agent_id="commitment_agent",
            capabilities=["commitment_detection", "deadline_extraction"],
        )

    @property
    def system_prompt(self) -> str:
        return """You are the Beacon Commitment Agent. Analyze Slack messages for operational 
commitments — statements where someone promises to do something.

For each commitment, extract:
1. The commitment statement
2. Who made it (name/user reference)
3. The type (delivery, action, information, decision)
4. Any deadline mentioned
5. Confidence that this is a genuine commitment (not hypothetical)

Examples of commitments:
- "I'll have the water truck there by 3pm" → delivery commitment
- "Let me check on the road conditions" → information commitment  
- "We'll approve the convoy route tomorrow" → decision commitment

NOT commitments:
- "Someone should check the roads" → vague suggestion
- "It would be good if..." → hypothetical"""

    async def execute(self, context: AgentContext) -> AgentResult:
        result = self._empty_result(context)

        evidence_items = context.world_model.evidence_items
        slack_messages = [
            e for e in evidence_items
            if e.get("source_type") in ("slack_rts", "slack_message")
        ]

        if not slack_messages:
            result.summary = "No Slack messages to analyze for commitments"
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

            messages_text = "\n\n".join([
                f"[{m.get('metadata', {}).get('username', '?')} in #{m.get('metadata', {}).get('channel_name', '?')}]: "
                f"{m.get('normalized_content', '')[:500]}"
                for m in slack_messages[:15]
            ])

            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": (
                    f"Crisis: {context.world_model.crisis_title}\n\n"
                    f"Messages to analyze:\n{messages_text}\n\n"
                    f"Extract any operational commitments."
                )},
            ]

            output, _ = await client.generate_structured(
                messages, CommitmentOutput, agent_id=self.agent_id
            )

            result.metadata = {"commitments": output.commitments}
            result.summary = output.summary
            result.observations = [
                f"Detected {len(output.commitments)} commitments"
            ]
            result.status = "completed"

        except Exception as e:
            logger.error("commitment_error", error=str(e))
            result.status = "failed"
            result.termination_reason = str(e)

        return result


class ReconciliationOutput(BaseModel):
    conflicts: list[dict[str, Any]] = Field(default_factory=list)
    resolutions: list[dict[str, Any]] = Field(default_factory=list)
    summary: str = ""


class ReconciliationAgent(AgentBase):
    """Resolves conflicts between concurrent state patches."""

    def __init__(self) -> None:
        super().__init__(
            agent_id="reconciliation_agent",
            capabilities=["conflict_resolution", "state_reconciliation"],
        )

    @property
    def system_prompt(self) -> str:
        return """You are the Beacon Reconciliation Agent. When multiple agents produce 
conflicting state patches, you resolve them by:
1. Identifying the conflict (what entities are affected?)
2. Comparing the evidence basis for each patch
3. Applying a resolution strategy:
   - Latest-wins (for temporal data)
   - Evidence-quality-wins (for claims)
   - Merge (for non-overlapping changes)
   - Escalate (for genuinely ambiguous conflicts)"""

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
                    f"Objective: {context.objective}\n"
                    f"Claims: {len(context.world_model.claims)}\n"
                    f"Contradictions: {len(context.world_model.contradictions)}\n\n"
                    f"Analyze and resolve any state conflicts."
                )},
            ]

            output, _ = await client.generate_structured(
                messages, ReconciliationOutput, agent_id=self.agent_id
            )

            result.metadata = {
                "conflicts": output.conflicts,
                "resolutions": output.resolutions,
            }
            result.summary = output.summary
            result.status = "completed"

        except Exception as e:
            result.status = "failed"
            result.termination_reason = str(e)

        return result


from beacon.agents.supervisor import register_agent
register_agent("commitment_processing", CommitmentAgent)
register_agent("reconciliation", ReconciliationAgent)
