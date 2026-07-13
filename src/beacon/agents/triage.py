"""Beacon Command — Triage Agent.

Hybrid deterministic + semantic triage for incoming hazard events.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from beacon.agents.base import AgentBase, AgentContext, AgentResult, GapProposal
from beacon.logging import get_logger

logger = get_logger(__name__)


class TriageOutput(BaseModel):
    """Structured output from the triage agent."""

    should_create_crisis: bool = False
    crisis_title: str = ""
    severity_assessment: str = "moderate"
    operational_consequences: list[str] = Field(default_factory=list)
    required_intelligence_domains: list[str] = Field(default_factory=list)
    initial_questions: list[str] = Field(default_factory=list)
    recommended_missions: list[str] = Field(default_factory=list)
    rationale: str = ""
    correlation_candidates: list[str] = Field(default_factory=list)


class TriageAgent(AgentBase):
    """Hybrid deterministic + LLM triage agent.

    Deterministic features (severity, magnitude, depth, geography) are computed
    before LLM analysis. The LLM adds operational consequence reasoning.
    Hard safety thresholds cannot be overridden by the LLM.
    """

    def __init__(self) -> None:
        super().__init__(
            agent_id="triage_agent",
            capabilities=["triage", "severity_assessment", "crisis_recommendation"],
        )

    @property
    def system_prompt(self) -> str:
        return """You are the Beacon Triage Agent. Your role is to assess incoming hazard events 
and determine operational response requirements.

Given a hazard event and any existing organizational context, you must:
1. Assess the likely operational consequences for a humanitarian organization
2. Identify what intelligence domains need investigation (logistics, medical, shelter, etc.)
3. Formulate initial questions that need answers
4. Recommend what types of agent missions should be launched
5. Determine if this warrants creating a new crisis or correlating with an existing one

You MUST respect deterministic severity scores. If the system has classified an event as 
high severity, you cannot downgrade it. You may upgrade the assessment if you identify 
additional operational concerns.

Be specific about operational consequences. Not "this is dangerous" but "road access to 
affected communities may be disrupted" or "medical facilities in the area may need 
emergency generator support."

Respond in the required JSON schema."""

    async def execute(self, context: AgentContext) -> AgentResult:
        """Execute triage analysis."""
        result = self._empty_result(context)

        # Extract event data from world model
        events = context.world_model.evidence_items
        if not events:
            result.status = "completed"
            result.termination_reason = "no_events_to_triage"
            result.summary = "No events available for triage"
            return result

        # Deterministic triage features
        event = events[0] if events else {}
        magnitude = event.get("magnitude")
        severity_score = event.get("severity_score", 0)
        hazard_type = event.get("hazard_type", "unknown")
        location = event.get("location", "unknown")

        # Hard safety threshold — cannot be overridden by LLM
        force_crisis = severity_score >= 7.0 or (magnitude and magnitude >= 7.0)

        # Attempt LLM-based triage
        try:
            from beacon.llm import create_llm_provider, StructuredLLMClient
            from beacon.config import get_settings

            settings = get_settings()
            if settings.is_llm_configured:
                provider = create_llm_provider(settings)
                client = StructuredLLMClient(provider)

                messages = [
                    {"role": "system", "content": self.system_prompt},
                    {
                        "role": "user",
                        "content": (
                            f"Triage this hazard event:\n"
                            f"Type: {hazard_type}\n"
                            f"Location: {location}\n"
                            f"Magnitude: {magnitude}\n"
                            f"Severity Score: {severity_score}/10\n"
                            f"Event data: {event}\n\n"
                            f"Existing crises: {[c.get('title', '') for c in context.world_model.claims]}\n"
                            f"Provide your triage assessment."
                        ),
                    },
                ]

                triage_output, record = await client.generate_structured(
                    messages, TriageOutput, agent_id=self.agent_id
                )

                # Enforce hard threshold
                if force_crisis:
                    triage_output.should_create_crisis = True

                result.observations = triage_output.operational_consequences
                result.summary = triage_output.rationale
                result.gap_proposals = [
                    GapProposal(
                        question=q,
                        uncertainty_score=0.7,
                        decision_impact=0.6,
                        urgency=0.7,
                    )
                    for q in triage_output.initial_questions
                ]
                result.mission_proposals = [
                    {"mission_type": mt, "objective": f"Investigate {hazard_type} event at {location}"}
                    for mt in triage_output.recommended_missions
                ]
                result.metadata = {
                    "should_create_crisis": triage_output.should_create_crisis,
                    "crisis_title": triage_output.crisis_title,
                    "severity_assessment": triage_output.severity_assessment,
                    "force_crisis": force_crisis,
                    "correlation_candidates": triage_output.correlation_candidates,
                }
            else:
                # Deterministic-only triage
                result.metadata = {
                    "should_create_crisis": force_crisis or severity_score >= 5.0,
                    "severity_assessment": (
                        "extreme" if severity_score >= 8
                        else "severe" if severity_score >= 6
                        else "high" if severity_score >= 4
                        else "moderate"
                    ),
                    "force_crisis": force_crisis,
                }
                result.summary = f"Deterministic triage: {hazard_type} at {location}, severity {severity_score}/10"

        except Exception as e:
            logger.error("triage_llm_error", error=str(e))
            # Fall back to deterministic
            result.metadata = {
                "should_create_crisis": force_crisis or severity_score >= 5.0,
                "force_crisis": force_crisis,
                "llm_error": str(e),
            }
            result.summary = f"Deterministic triage (LLM unavailable): severity {severity_score}/10"

        result.status = "completed"
        result.termination_reason = "triage_complete"
        return result
