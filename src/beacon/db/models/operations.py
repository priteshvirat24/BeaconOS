"""Operations models: ToolInvocation, ModelInvocation, RTSSearch."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from beacon.db.base import Base, TimestampMixin, UUIDMixin


class ToolInvocation(Base, UUIDMixin, TimestampMixin):
    """Record of a tool invocation through MCP or internal registry."""

    __tablename__ = "tool_invocations"

    mission_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("missions.id"), nullable=True
    )
    crisis_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crises.id"), nullable=True
    )

    tool_name: Mapped[str] = mapped_column(String(255), nullable=False)
    tool_server: Mapped[str | None] = mapped_column(String(100))
    input_params: Mapped[dict | None] = mapped_column(JSONB)
    output_result: Mapped[dict | None] = mapped_column(JSONB)

    status: Mapped[str] = mapped_column(String(50), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    latency_ms: Mapped[int | None] = mapped_column(Integer)

    agent_id: Mapped[str | None] = mapped_column(String(100))
    trace_id: Mapped[str | None] = mapped_column(String(64))
    correlation_id: Mapped[str | None] = mapped_column(String(64))

    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, default=dict)


class ModelInvocation(Base, UUIDMixin, TimestampMixin):
    """Record of an LLM model invocation."""

    __tablename__ = "model_invocations"

    mission_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("missions.id"), nullable=True
    )
    crisis_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crises.id"), nullable=True
    )

    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[int | None] = mapped_column(Integer)

    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    total_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[float | None] = mapped_column(Float)

    status: Mapped[str] = mapped_column(String(50), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)

    agent_id: Mapped[str | None] = mapped_column(String(100))
    trace_id: Mapped[str | None] = mapped_column(String(64))

    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, default=dict)


class RTSSearch(Base, UUIDMixin, TimestampMixin):
    """Record of a Slack RTS/search.messages invocation."""

    __tablename__ = "rts_searches"

    mission_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("missions.id"), nullable=True
    )
    crisis_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crises.id"), nullable=True
    )

    query: Mapped[str] = mapped_column(Text, nullable=False)
    query_params: Mapped[dict | None] = mapped_column(JSONB)
    result_count: Mapped[int] = mapped_column(Integer, default=0)
    result_message_ids: Mapped[list | None] = mapped_column(JSONB)
    evidence_ids_created: Mapped[list | None] = mapped_column(JSONB)

    # Quality metrics
    novelty_score: Mapped[float | None] = mapped_column(Float)
    relevance_score: Mapped[float | None] = mapped_column(Float)
    information_gain: Mapped[float | None] = mapped_column(Float)

    latency_ms: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    access_scope: Mapped[str | None] = mapped_column(String(255))

    agent_id: Mapped[str | None] = mapped_column(String(100))
    trace_id: Mapped[str | None] = mapped_column(String(64))

    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, default=dict)
