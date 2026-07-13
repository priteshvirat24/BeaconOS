"""Crisis API endpoints."""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from beacon.db import get_session
from beacon.db.models.crisis import Crisis
from beacon.logging import get_logger
from sqlalchemy import select

logger = get_logger(__name__)

router = APIRouter()


class CrisisResponse(BaseModel):
    id: uuid.UUID
    title: str
    status: str
    hazard_type: str
    severity: str
    severity_score: float
    primary_location_name: Optional[str] = None
    primary_latitude: Optional[float] = None
    primary_longitude: Optional[float] = None
    slack_channel_id: Optional[str] = None
    version: int

    model_config = {"from_attributes": True}


class CrisisListResponse(BaseModel):
    crises: list[CrisisResponse]
    total: int


@router.get("", response_model=CrisisListResponse)
async def list_crises(
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
) -> CrisisListResponse:
    """List crises with optional status filter."""
    async with get_session() as session:
        query = select(Crisis).order_by(Crisis.created_at.desc())
        if status:
            query = query.where(Crisis.status == status)
        query = query.limit(limit).offset(offset)
        result = await session.execute(query)
        crises = result.scalars().all()

        count_query = select(Crisis)
        if status:
            count_query = count_query.where(Crisis.status == status)
        count_result = await session.execute(
            select(__import__("sqlalchemy").func.count()).select_from(count_query.subquery())
        )
        total = count_result.scalar() or 0

    return CrisisListResponse(
        crises=[CrisisResponse.model_validate(c) for c in crises],
        total=total,
    )


@router.get("/{crisis_id}", response_model=CrisisResponse)
async def get_crisis(crisis_id: uuid.UUID) -> CrisisResponse:
    """Get a specific crisis by ID."""
    async with get_session() as session:
        result = await session.execute(select(Crisis).where(Crisis.id == crisis_id))
        crisis = result.scalar_one_or_none()
        if not crisis:
            raise HTTPException(status_code=404, detail="Crisis not found")
    return CrisisResponse.model_validate(crisis)
