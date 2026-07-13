"""Beacon Command — Workspace Investigator Agent.

Iterative agentic Slack search that uses LLM to determine queries,
evaluates results, and decides next actions. This is load-bearing functionality.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field

from beacon.agents.base import (
    AgentBase,
    AgentContext,
    AgentResult,
    EvidenceCandidate,
    ClaimProposal,
    GapProposal,
    ToolTrace,
)
from beacon.logging import get_logger

logger = get_logger(__name__)


class SearchDecision(BaseModel):
    """LLM decision about the next search action."""

    action: str = "search"  # search, reformulate, broaden, narrow, complete, create_gap
    query: str = ""
    rationale: str = ""
    information_needs: list[str] = Field(default_factory=list)
    confidence_in_coverage: float = 0.0
    should_continue: bool = True


class WorkspaceInvestigator(AgentBase):
    """Iterative Slack workspace search agent.

    The agent loop:
    1. Identify unresolved information needs from the world model
    2. Construct search queries using the LLM
    3. Execute actual Slack search
    4. Convert results into evidence candidates
    5. Evaluate novelty and information gain
    6. Decide whether to continue, reformulate, or complete
    """

    def __init__(self) -> None:
        super().__init__(
            agent_id="workspace_investigator",
            capabilities=["slack_search", "evidence_creation", "investigation"],
        )

    @property
    def system_prompt(self) -> str:
        return """You are the Beacon Workspace Investigator. You search the organization's Slack 
workspace to find information relevant to an active crisis.

You operate iteratively:
1. Review the current world model and identify what information is missing
2. Construct a targeted Slack search query
3. Evaluate search results for relevance, novelty, and contradiction potential
4. Decide whether to search again, reformulate, or complete

CRITICAL RULES:
- Do NOT hardcode search queries. Each query must be derived from current information needs.
- You ONLY see what the coordinator's Slack token can access. Note access scope limitations.
- Convert search results into structured evidence, not raw prose.
- Track which information needs have been addressed and which remain.
- Stop when: success criteria met, information gain is low, or budget exhausted.

For each search decision, explain your rationale for the chosen query.
Do NOT search for the same query twice unless you're paginating results."""

    async def execute(self, context: AgentContext) -> AgentResult:
        """Execute iterative workspace investigation."""
        result = self._empty_result(context)
        result.evidence_candidates = []
        result.claim_proposals = []
        result.gap_proposals = []
        result.tool_traces = []
        result.observations = []

        seen_queries: set[str] = set()
        iteration = 0
        max_iterations = min(context.budget.tool_budget, 8)

        while iteration < max_iterations and not context.budget.is_budget_exhausted:
            iteration += 1

            # Use LLM to decide next search action
            try:
                decision = await self._decide_next_action(
                    context, result, seen_queries, iteration
                )
            except Exception as e:
                logger.error("investigator_decision_error", error=str(e), iteration=iteration)
                result.observations.append(f"LLM decision failed at iteration {iteration}: {e}")
                break

            if not decision.should_continue or decision.action == "complete":
                result.observations.append(f"Investigation complete: {decision.rationale}")
                break

            if decision.action in ("search", "reformulate", "broaden", "narrow"):
                if not decision.query or decision.query in seen_queries:
                    result.observations.append("No new query to execute, completing")
                    break

                seen_queries.add(decision.query)
                context.budget.tools_used += 1

                # Execute actual Slack search
                search_results, trace = await self._execute_search(decision.query)
                result.tool_traces.append(trace)

                if search_results:
                    # Convert to evidence candidates
                    for sr in search_results:
                        ev = EvidenceCandidate(
                            source_type="slack_rts",
                            source_provider="slack_search",
                            normalized_content=sr["text"][:5000],
                            raw_content_hash=hashlib.sha256(sr["text"].encode()).hexdigest(),
                            source_uri=sr.get("permalink"),
                            slack_permalink=sr.get("permalink"),
                            reliability_score=0.6,
                            metadata={
                                "channel_id": sr.get("channel_id"),
                                "channel_name": sr.get("channel_name"),
                                "user": sr.get("username"),
                                "timestamp": sr.get("timestamp"),
                                "query": decision.query,
                            },
                        )
                        result.evidence_candidates.append(ev)

                    result.observations.append(
                        f"Search '{decision.query}': {len(search_results)} results"
                    )
                else:
                    result.observations.append(f"Search '{decision.query}': no results")

            elif decision.action == "create_gap":
                result.gap_proposals.append(GapProposal(
                    question=decision.rationale,
                    uncertainty_score=0.7,
                    decision_impact=0.5,
                    urgency=0.5,
                    candidate_strategies=["targeted_human_request", "coordinator_escalation"],
                ))

        result.status = "completed"
        result.termination_reason = (
            "budget_exhausted" if context.budget.is_budget_exhausted
            else f"completed_after_{iteration}_iterations"
        )
        result.summary = (
            f"Investigated workspace with {iteration} searches, "
            f"found {len(result.evidence_candidates)} evidence candidates"
        )
        return result

    async def _decide_next_action(
        self,
        context: AgentContext,
        current_result: AgentResult,
        seen_queries: set[str],
        iteration: int,
    ) -> SearchDecision:
        """Use LLM to decide the next search action."""
        try:
            from beacon.llm import create_llm_provider, StructuredLLMClient
            from beacon.config import get_settings

            settings = get_settings()
            if not settings.is_llm_configured:
                # Fallback: generate query from objective
                return SearchDecision(
                    action="search",
                    query=context.objective[:100],
                    rationale="LLM not configured, using objective as query",
                    should_continue=iteration <= 1,
                )

            provider = create_llm_provider(settings)
            client = StructuredLLMClient(provider)

            messages = [
                {"role": "system", "content": self.system_prompt},
                {
                    "role": "user",
                    "content": (
                        f"Mission: {context.objective}\n"
                        f"Crisis: {context.world_model.crisis_title or 'Unknown'}\n"
                        f"Iteration: {iteration}\n"
                        f"Previous queries: {list(seen_queries)}\n"
                        f"Evidence found so far: {len(current_result.evidence_candidates)}\n"
                        f"Observations: {current_result.observations[-3:]}\n"
                        f"Budget remaining: {context.budget.tool_budget_remaining} searches\n"
                        f"Known claims: {[c.get('statement', '')[:100] for c in context.world_model.claims[:5]]}\n"
                        f"Known gaps: {[g.get('question', '')[:100] for g in context.world_model.intelligence_gaps[:5]]}\n\n"
                        f"What should be the next search action?"
                    ),
                },
            ]

            decision, _ = await client.generate_structured(
                messages, SearchDecision, agent_id=self.agent_id
            )
            return decision

        except Exception as e:
            logger.warning("investigator_llm_fallback", error=str(e))
            return SearchDecision(
                action="complete",
                rationale=f"LLM error: {e}",
                should_continue=False,
            )

    async def _execute_search(
        self, query: str
    ) -> tuple[list[dict[str, Any]], ToolTrace]:
        """Execute a real Slack search."""
        start = time.monotonic()
        results: list[dict[str, Any]] = []

        try:
            from beacon.config import get_settings
            from beacon.slack import EnvCoordinatorTokenProvider
            from beacon.slack.search import SlackSearchProvider

            settings = get_settings()
            if settings.slack_coordinator_user_token:
                token_provider = EnvCoordinatorTokenProvider(
                    bot_token=settings.slack_bot_token,
                    user_token=settings.slack_coordinator_user_token,
                    signing_secret=settings.slack_signing_secret,
                )
                search = SlackSearchProvider(
                    token_provider,
                    timeout_seconds=settings.slack_rts_timeout_seconds,
                )
                search_results, total = await search.search(query, count=10)

                for sr in search_results:
                    results.append({
                        "text": sr.text,
                        "channel_id": sr.channel_id,
                        "channel_name": sr.channel_name,
                        "username": sr.username,
                        "timestamp": sr.timestamp,
                        "permalink": sr.permalink,
                    })

            latency = int((time.monotonic() - start) * 1000)
            trace = ToolTrace(
                tool_name="slack_search",
                input_params={"query": query},
                output_summary=f"{len(results)} results",
                latency_ms=latency,
                status="success",
            )
            return results, trace

        except Exception as e:
            latency = int((time.monotonic() - start) * 1000)
            trace = ToolTrace(
                tool_name="slack_search",
                input_params={"query": query},
                output_summary="",
                latency_ms=latency,
                status="error",
                error=str(e),
            )
            logger.error("slack_search_error", query=query, error=str(e))
            return [], trace
