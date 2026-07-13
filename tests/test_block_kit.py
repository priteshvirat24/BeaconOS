"""Tests for Beacon Command — Block Kit Builders."""

from beacon.slack.block_kit import (
    BlockBuilder,
    hazard_alert_blocks,
    situation_brief_blocks,
    intelligence_request_blocks,
    approval_request_blocks,
    task_card_blocks,
    error_blocks,
    commitment_confirmation_blocks,
    app_home_blocks,
)


class TestBlockBuilder:
    def test_header(self) -> None:
        blocks = BlockBuilder().header("Test Header").build()
        assert len(blocks) == 1
        assert blocks[0]["type"] == "header"
        assert blocks[0]["text"]["text"] == "Test Header"

    def test_section(self) -> None:
        blocks = BlockBuilder().section("Test content").build()
        assert blocks[0]["type"] == "section"
        assert blocks[0]["text"]["type"] == "mrkdwn"

    def test_fields(self) -> None:
        blocks = BlockBuilder().fields([("Label", "Value")]).build()
        assert blocks[0]["type"] == "section"
        assert len(blocks[0]["fields"]) == 1

    def test_divider(self) -> None:
        blocks = BlockBuilder().divider().build()
        assert blocks[0]["type"] == "divider"

    def test_chained_building(self) -> None:
        blocks = (
            BlockBuilder()
            .header("Title")
            .divider()
            .section("Content")
            .context("Context text")
            .build()
        )
        assert len(blocks) == 4


class TestSurfaces:
    def test_hazard_alert_blocks(self) -> None:
        blocks = hazard_alert_blocks(
            title="M6.5 Earthquake",
            hazard_type="earthquake",
            severity="severe",
            magnitude=6.5,
            location="Eastern Turkey",
            event_time="2024-01-15T10:30:00Z",
            source="USGS",
            crisis_id="abc-123",
        )
        assert len(blocks) > 0
        assert blocks[0]["type"] == "header"

    def test_situation_brief_blocks(self) -> None:
        blocks = situation_brief_blocks(
            crisis_title="Turkey Earthquake",
            status="active",
            summary="Major earthquake response ongoing",
            evidence_count=42,
            verified_claims=15,
            contested_claims=3,
            critical_gaps=5,
            active_tasks=12,
            crisis_id="abc-123",
        )
        assert len(blocks) > 0

    def test_intelligence_request_blocks(self) -> None:
        blocks = intelligence_request_blocks(
            question="What medical facilities are operational?",
            why_needed="Need to route casualties",
            crisis_title="Turkey Earthquake",
            urgency="high",
            request_id="req-123",
        )
        assert len(blocks) > 0

    def test_approval_request_blocks(self) -> None:
        blocks = approval_request_blocks(
            action_description="Post situation update to #general",
            rationale="Organizational awareness",
            risks="May cause unnecessary alarm",
            authority_required="L3_EXECUTE_REVERSIBLE",
            approval_id="appr-123",
        )
        assert len(blocks) > 0

    def test_app_home_blocks(self) -> None:
        blocks = app_home_blocks(
            active_crises=[{"id": "1", "title": "Crisis", "status": "active", "severity": "high"}],
            pending_approvals=3,
            at_risk_tasks=2,
            overdue_tasks=1,
            active_missions=5,
        )
        assert len(blocks) > 0
