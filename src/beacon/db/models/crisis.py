"""Crisis and hazard event models."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, Boolean
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from beacon.db.base import Base, TimestampMixin, UUIDMixin, VersionMixin
from beacon.domain.enums import CrisisStatus, EventSourceType, HazardSeverity, HazardType


class HazardEvent(Base, UUIDMixin, TimestampMixin):
    """Raw hazard event from external sources (USGS, GDACS, NWS)."""

    __tablename__ = "hazard_events"

    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_event_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    hazard_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(1000), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    # Geography
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    depth_km: Mapped[float | None] = mapped_column(Float)
    location_name: Mapped[str | None] = mapped_column(String(500))
    affected_area: Mapped[dict | None] = mapped_column(JSONB)

    # Severity
    magnitude: Mapped[float | None] = mapped_column(Float)
    severity: Mapped[str | None] = mapped_column(String(50))
    severity_score: Mapped[float | None] = mapped_column(Float)
    alert_level: Mapped[str | None] = mapped_column(String(50))

    # Temporal
    event_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at_source: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Flags
    tsunami_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    is_update: Mapped[bool] = mapped_column(Boolean, default=False)

    # Raw data
    raw_payload_hash: Mapped[str | None] = mapped_column(String(64))
    source_url: Mapped[str | None] = mapped_column(String(2000))
    raw_metadata: Mapped[dict | None] = mapped_column(JSONB, default=dict)

    # Correlation
    crisis_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crises.id"), nullable=True
    )
    correlation_confidence: Mapped[float | None] = mapped_column(Float)

    crisis: Mapped[Crisis | None] = relationship(back_populates="hazard_events")


class ExternalEvent(Base, UUIDMixin, TimestampMixin):
    """Normalized external event for correlation."""

    __tablename__ = "external_events"

    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_event_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    hazard_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(1000), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    severity_score: Mapped[float] = mapped_column(Float, default=0.0)
    event_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw_metadata: Mapped[dict | None] = mapped_column(JSONB, default=dict)

    crisis_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crises.id"), nullable=True
    )


class Crisis(Base, UUIDMixin, TimestampMixin, VersionMixin):
    """Central crisis entity — the operational context for all Beacon activities."""

    __tablename__ = "crises"

    title: Mapped[str] = mapped_column(String(1000), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(50), default=CrisisStatus.DETECTED.value, nullable=False
    )
    hazard_type: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(
        String(50), default=HazardSeverity.MODERATE.value
    )
    severity_score: Mapped[float] = mapped_column(Float, default=0.0)

    # Geography
    primary_latitude: Mapped[float | None] = mapped_column(Float)
    primary_longitude: Mapped[float | None] = mapped_column(Float)
    primary_location_name: Mapped[str | None] = mapped_column(String(500))
    affected_regions: Mapped[list | None] = mapped_column(JSONB)

    # Slack integration
    slack_channel_id: Mapped[str | None] = mapped_column(String(50))
    slack_channel_name: Mapped[str | None] = mapped_column(String(255))

    # Timing
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Source
    primary_source_event_id: Mapped[str | None] = mapped_column(String(255))
    primary_source_type: Mapped[str | None] = mapped_column(String(50))

    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, default=dict)

    # Relationships
    hazard_events: Mapped[list[HazardEvent]] = relationship(back_populates="crisis")
    missions: Mapped[list] = relationship("Mission", back_populates="crisis")
    evidence_items: Mapped[list] = relationship("Evidence", back_populates="crisis")
    claims: Mapped[list] = relationship("Claim", back_populates="crisis")
    tasks: Mapped[list] = relationship("Task", back_populates="crisis")
    plans: Mapped[list] = relationship("ResponsePlan", back_populates="crisis")
    decisions: Mapped[list] = relationship("Decision", back_populates="crisis")
