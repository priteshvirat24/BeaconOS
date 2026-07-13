"""Tests for Beacon Command — Domain Enumerations."""

from beacon.domain.enums import (
    CrisisStatus,
    HazardType,
    HazardSeverity,
    MissionType,
    MissionStatus,
    ClaimEpistemicStatus,
    AuthorityLevel,
    DomainEventType,
    TaskStatus,
    PlanStatus,
)


class TestDomainEnums:
    def test_crisis_status_values(self) -> None:
        assert CrisisStatus.DETECTED.value == "detected"
        assert CrisisStatus.ACTIVE.value == "active"
        assert CrisisStatus.RESOLVED.value == "resolved"

    def test_hazard_types(self) -> None:
        assert HazardType.EARTHQUAKE.value == "earthquake"
        assert HazardType.FLOOD.value == "flood"
        assert HazardType.CYCLONE.value == "cyclone"

    def test_severity_levels(self) -> None:
        assert HazardSeverity.LOW.value == "low"
        assert HazardSeverity.EXTREME.value == "extreme"

    def test_mission_types(self) -> None:
        assert MissionType.TRIAGE.value == "triage"
        assert MissionType.WORKSPACE_INVESTIGATION.value == "workspace_investigation"
        assert MissionType.PLAN_GENERATION.value == "plan_generation"

    def test_epistemic_status(self) -> None:
        assert ClaimEpistemicStatus.VERIFIED_FACT.value == "verified_fact"
        assert ClaimEpistemicStatus.CONTESTED.value == "contested"

    def test_authority_levels(self) -> None:
        assert AuthorityLevel.L0_OBSERVE.value == "L0_OBSERVE"
        assert AuthorityLevel.L5_PROHIBITED.value == "L5_PROHIBITED"

    def test_domain_event_types(self) -> None:
        assert DomainEventType.CRISIS_CREATED.value == "crisis.created"
        assert DomainEventType.HAZARD_OBSERVED.value == "hazard.observed"
        assert DomainEventType.TOOL_REQUESTED.value == "tool.requested"
