"""Tests for Beacon Command — Pydantic Schemas."""

import uuid
from datetime import datetime

from beacon.domain.schemas import (
    CrisisCreateSchema,
    CrisisUpdateSchema,
    EvidenceCreateSchema,
    MissionCreateSchema,
    TaskCreateSchema,
    StatePatchSchema,
    WorldModelSnapshotSchema,
)


class TestCrisisSchemas:
    def test_crisis_create(self) -> None:
        schema = CrisisCreateSchema(
            title="M6.5 Earthquake Turkey",
            hazard_type="earthquake",
            severity="severe",
            severity_score=7.5,
        )
        assert schema.title == "M6.5 Earthquake Turkey"
        assert schema.severity_score == 7.5

    def test_crisis_update(self) -> None:
        schema = CrisisUpdateSchema(status="active")
        assert schema.status == "active"
        assert schema.title is None


class TestEvidenceSchemas:
    def test_evidence_create(self) -> None:
        schema = EvidenceCreateSchema(
            source_type="slack_rts",
            source_provider="slack_search",
            normalized_content="Field hospital operational at grid ref 123456",
            raw_content_hash="abc123",
        )
        assert schema.reliability_score == 0.5


class TestMissionSchemas:
    def test_mission_create(self) -> None:
        schema = MissionCreateSchema(
            mission_type="triage",
            objective="Triage incoming earthquake event",
        )
        assert schema.priority == 0.5
        assert schema.tool_budget == 12


class TestStatePatch:
    def test_state_patch(self) -> None:
        patch = StatePatchSchema(
            patch_type="claim_update",
            target_entity_type="claim",
            target_entity_id=str(uuid.uuid4()),
            changes={"epistemic_status": "verified_fact", "confidence": 0.95},
        )
        assert patch.patch_type == "claim_update"
        assert patch.changes["confidence"] == 0.95


class TestWorldModelSnapshot:
    def test_empty_snapshot(self) -> None:
        snapshot = WorldModelSnapshotSchema(
            crisis={"id": str(uuid.uuid4()), "title": "Test", "status": "active"}
        )
        assert len(snapshot.claims) == 0
        assert len(snapshot.evidence_items) == 0
