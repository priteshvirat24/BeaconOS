"""Evidence API endpoints."""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from beacon.db import get_session
from beacon.db.models.evidence import Evidence
from beacon.logging import get_logger
from sqlalchemy import select

logger = get_logger(__name__)

router = APIRouter()


class EvidenceResponse(BaseModel):
    id: uuid.UUID
    crisis_id: Optional[uuid.UUID] = None
    source_type: str
    source_provider: str
    normalized_content: str
    reliability_score: float
    freshness_score: float
    observed_at: str
    slack_permalink: Optional[str] = None
    geographic_scope: Optional[str] = None

    model_config = {"from_attributes": True}


@router.get("", response_model=list[EvidenceResponse])
async def list_evidence(
    crisis_id: Optional[uuid.UUID] = Query(None),
    source_type: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
) -> list[EvidenceResponse]:
    """List evidence with optional filters."""
    async with get_session() as session:
        query = select(Evidence).order_by(Evidence.observed_at.desc())
        if crisis_id:
            query = query.where(Evidence.crisis_id == crisis_id)
        if source_type:
            query = query.where(Evidence.source_type == source_type)
        query = query.limit(limit).offset(offset)
        result = await session.execute(query)
        items = result.scalars().all()
    return [EvidenceResponse.model_validate(e) for e in items]


@router.get("/{evidence_id}", response_model=EvidenceResponse)
async def get_evidence(evidence_id: uuid.UUID) -> EvidenceResponse:
    """Get specific evidence by ID."""
    async with get_session() as session:
        result = await session.execute(select(Evidence).where(Evidence.id == evidence_id))
        ev = result.scalar_one_or_none()
        if not ev:
            raise HTTPException(status_code=404, detail="Evidence not found")
    return EvidenceResponse.model_validate(ev)
