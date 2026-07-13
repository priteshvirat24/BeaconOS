"""Resource and Constraint models."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, Boolean
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from beacon.db.base import Base, TimestampMixin, UUIDMixin


class Resource(Base, UUIDMixin, TimestampMixin):
    """Operational resource (supply, vehicle, facility, personnel group)."""

    __tablename__ = "resources"

    name: Mapped[str] = mapped_column(String(500), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)

    # Location
    location_name: Mapped[str | None] = mapped_column(String(500))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)

    # Capacity
    total_capacity: Mapped[int | None] = mapped_column(Integer)
    available_capacity: Mapped[int | None] = mapped_column(Integer)
    unit: Mapped[str | None] = mapped_column(String(50))

    # Status
    status: Mapped[str] = mapped_column(String(50), default="available")
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    evidence_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evidence.id"), nullable=True
    )

    # Ownership
    owner_actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("actors.id"), nullable=True
    )
    organization_name: Mapped[str | None] = mapped_column(String(500))

    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, default=dict)


class Constraint(Base, UUIDMixin, TimestampMixin):
    """Operational constraint affecting crisis response."""

    __tablename__ = "constraints"

    crisis_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crises.id"), nullable=True
    )

    name: Mapped[str] = mapped_column(String(500), nullable=False)
    constraint_type: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    severity: Mapped[float] = mapped_column(Float, default=0.5)
    is_hard: Mapped[bool] = mapped_column(Boolean, default=False)  # hard vs soft constraint

    affects_resources: Mapped[list | None] = mapped_column(JSONB)
    affects_locations: Mapped[list | None] = mapped_column(JSONB)
    affects_plans: Mapped[list | None] = mapped_column(JSONB)

    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    evidence_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evidence.id"), nullable=True
    )

    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, default=dict)
