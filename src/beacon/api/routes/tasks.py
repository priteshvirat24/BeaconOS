"""Task API endpoints."""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from beacon.db import get_session
from beacon.db.models.tasks import Task
from sqlalchemy import select

router = APIRouter()


class TaskResponse(BaseModel):
    id: uuid.UUID
    crisis_id: Optional[uuid.UUID] = None
    title: str
    status: str
    priority: float
    assigned_name: Optional[str] = None

    model_config = {"from_attributes": True}


@router.get("", response_model=list[TaskResponse])
async def list_tasks(
    crisis_id: Optional[uuid.UUID] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
) -> list[TaskResponse]:
    """List tasks."""
    async with get_session() as session:
        query = select(Task).order_by(Task.created_at.desc())
        if crisis_id:
            query = query.where(Task.crisis_id == crisis_id)
        if status:
            query = query.where(Task.status == status)
        result = await session.execute(query.limit(limit))
        items = result.scalars().all()
    return [TaskResponse.model_validate(t) for t in items]
