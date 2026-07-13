"""Beacon Command — External Intelligence Agent.

Queries external hazard APIs (USGS, GDACS, NWS) through MCP tools
and geospatial services to gather evidence beyond the workspace.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from beacon.agents.base import AgentBase, AgentContext, AgentResult, EvidenceCandidate, ToolTrace
from beacon.logging import get_logger

logger = get_logger(__name__)


class ExternalIntelligenceAgent(AgentBase):
    """Gathers intelligence from external hazard and geospatial services."""

    def __init__(self) -> None:
        super().__init__(
            agent_id="external_intelligence",
            capabilities=["external_query", "hazard_monitoring", "geospatial_analysis"],
        )

    @property
    def system_prompt(self) -> str:
        return """You are the Beacon External Intelligence Agent. You gather information from 
external hazard monitoring systems (USGS, GDACS, NWS) and geospatial services.

Use MCP tools to:
1. Query hazard event databases for related events
2. Perform geospatial analysis (proximity, affected areas, routing)
3. Cross-reference external data with workspace intelligence
4. Identify aftershock sequences, cascading hazards, or compound events"""

    async def execute(self, context: AgentContext) -> AgentResult:
        result = self._empty_result(context)

        try:
            from beacon.mcp.client import mcp_client
            import json

            # Query active hazard events
            tool_result = await mcp_client.invoke(
                "hazard_list_active_events",
                {"min_severity": 3.0, "limit": 20},
                agent_id=self.agent_id,
                mission_id=context.mission_id,
            )

            if tool_result.success and tool_result.result:
                context.budget.tools_used += 1
                events = json.loads(tool_result.result) if isinstance(tool_result.result, str) else tool_result.result
                result.tool_traces.append(ToolTrace(
                    tool_name="hazard_list_active_events",
                    input_params={"min_severity": 3.0},
                    output_summary=f"{len(events)} events",
                    latency_ms=tool_result.latency_ms,
                ))

                for event in events:
                    result.evidence_candidates.append(EvidenceCandidate(
                        source_type="hazard_api",
                        source_provider=event.get("source_type", "unknown"),
                        normalized_content=(
                            f"{event.get('title', 'Unknown Event')}: "
                            f"Magnitude {event.get('magnitude', 'N/A')}, "
                            f"Severity {event.get('severity_score', 0)}/10, "
                            f"Location: {event.get('location', 'Unknown')}"
                        ),
                        raw_content_hash=event.get("event_id", ""),
                        source_uri=event.get("source_url"),
                        reliability_score=0.9,
                        metadata=event,
                    ))

            # If we have crisis coordinates, query for related nearby events
            wm = context.world_model
            if wm.crisis_id and context.budget.tool_budget_remaining > 0:
                # Get geospatial context
                for evidence in wm.evidence_items[:3]:
                    lat = evidence.get("latitude")
                    lon = evidence.get("longitude")
                    if lat and lon:
                        geo_result = await mcp_client.invoke(
                            "hazard_get_related_events",
                            {"latitude": lat, "longitude": lon, "radius_km": 300, "hours": 48},
                            agent_id=self.agent_id,
                        )
                        context.budget.tools_used += 1
                        if geo_result.success:
                            result.tool_traces.append(ToolTrace(
                                tool_name="hazard_get_related_events",
                                input_params={"lat": lat, "lon": lon},
                                output_summary="Related events queried",
                                latency_ms=geo_result.latency_ms,
                            ))
                        break

            result.status = "completed"
            result.summary = f"Gathered {len(result.evidence_candidates)} external evidence items"

        except Exception as e:
            logger.error("external_intel_error", error=str(e))
            result.status = "failed"
            result.termination_reason = str(e)

        return result


from beacon.agents.supervisor import register_agent
register_agent("external_investigation", ExternalIntelligenceAgent)
