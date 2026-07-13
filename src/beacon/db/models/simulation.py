"""Simulation, critique, and risk assessment models."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from beacon.db.base import Base, TimestampMixin, UUIDMixin


class SimulationRun(Base, UUIDMixin, TimestampMixin):
    """A bounded simulation run of a response plan."""

    __tablename__ = "simulation_runs"

    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("response_plans.id"), nullable=False
    )
    crisis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crises.id"), nullable=False
    )

    simulation_type: Mapped[str] = mapped_column(String(100), nullable=False)
    parameters: Mapped[dict | None] = mapped_column(JSONB)
    perturbations: Mapped[list | None] = mapped_column(JSONB)

    status: Mapped[str] = mapped_column(String(50), default="running")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_by_agent: Mapped[str | None] = mapped_column(String(100))
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, default=dict)


class SimulationResult(Base, UUIDMixin, TimestampMixin):
    """Result of a simulation run."""

    __tablename__ = "simulation_results"

    simulation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("simulation_runs.id"), nullable=False
    )

    scenario_name: Mapped[str] = mapped_column(String(255), nullable=False)
    perturbation_applied: Mapped[dict | None] = mapped_column(JSONB)

    # Results
    critical_path: Mapped[list | None] = mapped_column(JSONB)
    bottlenecks: Mapped[list | None] = mapped_column(JSONB)
    resource_conflicts: Mapped[list | None] = mapped_column(JSONB)
    single_points_of_failure: Mapped[list | None] = mapped_column(JSONB)
    deadline_feasibility: Mapped[dict | None] = mapped_column(JSONB)
    failure_propagation: Mapped[list | None] = mapped_column(JSONB)

    overall_feasibility: Mapped[float] = mapped_column(Float, default=0.5)
    risk_score: Mapped[float] = mapped_column(Float, default=0.5)
    summary: Mapped[str | None] = mapped_column(Text)

    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, default=dict)


class PlanCritique(Base, UUIDMixin, TimestampMixin):
    """Red-team critique of a response plan."""

    __tablename__ = "plan_critiques"

    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("response_plans.id"), nullable=False
    )

    # Findings
    unsupported_assumptions: Mapped[list | None] = mapped_column(JSONB)
    stale_evidence: Mapped[list | None] = mapped_column(JSONB)
    unresolved_contradictions: Mapped[list | None] = mapped_column(JSONB)
    critical_unknowns: Mapped[list | None] = mapped_column(JSONB)
    resource_conflicts: Mapped[list | None] = mapped_column(JSONB)
    missing_owners: Mapped[list | None] = mapped_column(JSONB)
    irreversible_actions: Mapped[list | None] = mapped_column(JSONB)
    policy_violations: Mapped[list | None] = mapped_column(JSONB)
    dependency_bottlenecks: Mapped[list | None] = mapped_column(JSONB)
    single_points_of_failure: Mapped[list | None] = mapped_column(JSONB)
    weak_evidence_chains: Mapped[list | None] = mapped_column(JSONB)
    missing_fallbacks: Mapped[list | None] = mapped_column(JSONB)

    severity_score: Mapped[float] = mapped_column(Float, default=0.5)
    recommendation: Mapped[str | None] = mapped_column(Text)
    created_by_agent: Mapped[str | None] = mapped_column(String(100))

    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, default=dict)


class RiskAssessment(Base, UUIDMixin, TimestampMixin):
    """Typed risk assessment across multiple dimensions."""

    __tablename__ = "risk_assessments"

    plan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("response_plans.id"), nullable=True
    )
    crisis_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crises.id"), nullable=True
    )

    # Risk dimensions (0.0-1.0 scores — NOT calibrated probabilities)
    human_safety_risk: Mapped[float] = mapped_column(Float, default=0.0)
    operational_risk: Mapped[float] = mapped_column(Float, default=0.0)
    evidence_risk: Mapped[float] = mapped_column(Float, default=0.0)
    execution_risk: Mapped[float] = mapped_column(Float, default=0.0)
    coordination_risk: Mapped[float] = mapped_column(Float, default=0.0)
    dependency_risk: Mapped[float] = mapped_column(Float, default=0.0)
    uncertainty_risk: Mapped[float] = mapped_column(Float, default=0.0)

    overall_risk: Mapped[float] = mapped_column(Float, default=0.0)
    failure_modes: Mapped[list | None] = mapped_column(JSONB)
    mitigations: Mapped[list | None] = mapped_column(JSONB)
    summary: Mapped[str | None] = mapped_column(Text)

    created_by_agent: Mapped[str | None] = mapped_column(String(100))
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, default=dict)
