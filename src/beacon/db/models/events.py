"""DomainEvent, StateRevision, and AuditRecord models."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from beacon.db.base import Base, UUIDMixin


class DomainEvent(Base, UUIDMixin):
    """Append-only domain event log for operationally significant transitions."""

    __tablename__ = "domain_events"

    crisis_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    actor_type: Mapped[str] = mapped_column(String(50), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(255), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    causation_id: Mapped[str | None] = mapped_column(String(64))
    correlation_id: Mapped[str | None] = mapped_column(String(64), index=True)
    trace_id: Mapped[str | None] = mapped_column(String(64))

    state_version_before: Mapped[int | None] = mapped_column(Integer)
    state_version_after: Mapped[int | None] = mapped_column(Integer)

    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, default=dict)


class StateRevision(Base, UUIDMixin):
    """State revision history for world model versioning."""

    __tablename__ = "state_revisions"

    crisis_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    patch_type: Mapped[str] = mapped_column(String(100), nullable=False)
    patch_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    applied_by: Mapped[str] = mapped_column(String(100), nullable=False)
    causation_event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, default=dict)


class AuditRecord(Base, UUIDMixin):
    """Audit trail record for compliance and debugging."""

    __tablename__ = "audit_records"

    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    actor_type: Mapped[str] = mapped_column(String(50), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(255), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(100))
    target_id: Mapped[str | None] = mapped_column(String(255))
    detail: Mapped[str | None] = mapped_column(Text)
    result: Mapped[str] = mapped_column(String(50), nullable=False)  # success, failure, denied
    crisis_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(64))

    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, default=dict)
