"""Tests for Beacon Command — Agent Base & Contracts."""

import uuid

from beacon.agents.base import (
    AgentBudget,
    AgentContext,
    AgentResult,
    ClaimProposal,
    EvidenceCandidate,
    GapProposal,
    PolicyContext,
    WorldModelSlice,
)


class TestAgentBudget:
    def test_tool_budget_remaining(self) -> None:
        budget = AgentBudget(tool_budget=10, tools_used=3)
        assert budget.tool_budget_remaining == 7

    def test_budget_exhausted(self) -> None:
        budget = AgentBudget(tool_budget=5, tools_used=5)
        assert budget.is_budget_exhausted is True

    def test_budget_not_exhausted(self) -> None:
        budget = AgentBudget(tool_budget=5, tools_used=4)
        assert budget.is_budget_exhausted is False


class TestAgentContext:
    def test_context_creation(self) -> None:
        ctx = AgentContext(
            mission_id=uuid.uuid4(),
            mission_type="triage",
            objective="Triage earthquake event",
            world_model=WorldModelSlice(),
            budget=AgentBudget(),
            policy=PolicyContext(),
        )
        assert ctx.mission_type == "triage"
        assert ctx.budget.tool_budget == 12

    def test_world_model_slice(self) -> None:
        wm = WorldModelSlice(
            crisis_id=uuid.uuid4(),
            crisis_title="M6.5 Earthquake",
            crisis_status="active",
        )
        assert wm.crisis_title == "M6.5 Earthquake"
        assert len(wm.evidence_items) == 0


class TestAgentResult:
    def test_result_with_proposals(self) -> None:
        result = AgentResult(
            mission_id=uuid.uuid4(),
            agent_id="test_agent",
            status="completed",
        )
        result.evidence_candidates.append(EvidenceCandidate(
            source_type="hazard_api",
            source_provider="usgs",
            normalized_content="M6.5 earthquake in Turkey",
            raw_content_hash="abc123",
        ))
        result.claim_proposals.append(ClaimProposal(
            statement="Magnitude 6.5 earthquake struck eastern Turkey",
            epistemic_status="supported_inference",
            confidence=0.8,
        ))
        result.gap_proposals.append(GapProposal(
            question="What is the population in the affected area?",
            decision_impact=0.8,
        ))

        assert len(result.evidence_candidates) == 1
        assert len(result.claim_proposals) == 1
        assert len(result.gap_proposals) == 1
        assert result.claim_proposals[0].confidence == 0.8
