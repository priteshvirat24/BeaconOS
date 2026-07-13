"""Beacon Command — Pydantic Schemas for API & Internal Use."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# --- Hazard Schemas ---

class HazardEventSchema(BaseModel):
    id: uuid.UUID
    source_type: str
    source_event_id: str
    hazard_type: str
    title: str
    description: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    depth_km: Optional[float] = None
    location_name: Optional[str] = None
    magnitude: Optional[float] = None
    severity: Optional[str] = None
    severity_score: Optional[float] = None
    event_time: Optional[datetime] = None
    tsunami_flag: bool = False
    crisis_id: Optional[uuid.UUID] = None

    model_config = {"from_attributes": True}


# --- Crisis Schemas ---

class CrisisCreateSchema(BaseModel):
    title: str
    hazard_type: str
    severity: str = "moderate"
    severity_score: float = 0.0
    primary_latitude: Optional[float] = None
    primary_longitude: Optional[float] = None
    primary_location_name: Optional[str] = None


class CrisisUpdateSchema(BaseModel):
    title: Optional[str] = None
    status: Optional[str] = None
    severity: Optional[str] = None
    summary: Optional[str] = None


class CrisisSummarySchema(BaseModel):
    id: uuid.UUID
    title: str
    status: str
    hazard_type: str
    severity: str
    severity_score: float
    primary_location_name: Optional[str] = None
    evidence_count: int = 0
    claim_count: int = 0
    active_task_count: int = 0

    model_config = {"from_attributes": True}


# --- Evidence Schemas ---

class EvidenceCreateSchema(BaseModel):
    crisis_id: Optional[uuid.UUID] = None
    source_type: str
    source_provider: str
    normalized_content: str
    raw_content_hash: str
    source_uri: Optional[str] = None
    slack_permalink: Optional[str] = None
    reliability_score: float = 0.5
    geographic_scope: Optional[str] = None


class EvidenceSchema(BaseModel):
    id: uuid.UUID
    crisis_id: Optional[uuid.UUID] = None
    source_type: str
    source_provider: str
    normalized_content: str
    reliability_score: float
    freshness_score: float
    observed_at: datetime
    slack_permalink: Optional[str] = None

    model_config = {"from_attributes": True}


# --- Claim Schemas ---

class ClaimSchema(BaseModel):
    id: uuid.UUID
    crisis_id: Optional[uuid.UUID] = None
    statement: str
    epistemic_status: str
    confidence: float
    freshness: float
    supporting_evidence_count: int = 0

    model_config = {"from_attributes": True}


# --- Mission Schemas ---

class MissionCreateSchema(BaseModel):
    crisis_id: Optional[uuid.UUID] = None
    mission_type: str
    objective: str
    priority: float = 0.5
    tool_budget: int = 12


class MissionSchema(BaseModel):
    id: uuid.UUID
    crisis_id: Optional[uuid.UUID] = None
    mission_type: str
    objective: str
    status: str
    priority: float
    assigned_agent: Optional[str] = None

    model_config = {"from_attributes": True}


# --- Task Schemas ---

class TaskCreateSchema(BaseModel):
    crisis_id: uuid.UUID
    title: str
    description: Optional[str] = None
    assigned_name: Optional[str] = None
    deadline: Optional[datetime] = None
    priority: float = 0.5


class TaskSchema(BaseModel):
    id: uuid.UUID
    crisis_id: Optional[uuid.UUID] = None
    title: str
    status: str
    priority: float
    assigned_name: Optional[str] = None
    deadline: Optional[datetime] = None

    model_config = {"from_attributes": True}


# --- Plan Schemas ---

class PlanSchema(BaseModel):
    id: uuid.UUID
    crisis_id: uuid.UUID
    objective: str
    strategy: Optional[str] = None
    status: str
    version: int

    model_config = {"from_attributes": True}


# --- Decision Schemas ---

class DecisionSchema(BaseModel):
    id: uuid.UUID
    crisis_id: uuid.UUID
    decision: str
    rationale: str
    status: str
    approved_by: Optional[str] = None

    model_config = {"from_attributes": True}


# --- Domain Event Schemas ---

class DomainEventSchema(BaseModel):
    id: uuid.UUID
    crisis_id: Optional[uuid.UUID] = None
    event_type: str
    actor_type: str
    actor_id: str
    timestamp: datetime
    payload: dict[str, Any]

    model_config = {"from_attributes": True}


# --- World Model Schemas ---

class WorldModelSnapshotSchema(BaseModel):
    """Complete world model snapshot for a crisis."""

    crisis: dict[str, Any]
    evidence_count: int = 0
    evidence_items: list[dict[str, Any]] = Field(default_factory=list)
    claims: list[dict[str, Any]] = Field(default_factory=list)
    contradictions: list[dict[str, Any]] = Field(default_factory=list)
    intelligence_gaps: list[dict[str, Any]] = Field(default_factory=list)
    hypotheses: list[dict[str, Any]] = Field(default_factory=list)
    active_tasks: list[dict[str, Any]] = Field(default_factory=list)
    active_plans: list[dict[str, Any]] = Field(default_factory=list)


# --- State Patch Schemas ---

class StatePatchSchema(BaseModel):
    """Typed state patch for world model updates."""

    patch_type: str
    target_entity_type: str
    target_entity_id: Optional[str] = None
    changes: dict[str, Any] = Field(default_factory=dict)
    applied_by: str = "system"
    causation_event_id: Optional[str] = None
