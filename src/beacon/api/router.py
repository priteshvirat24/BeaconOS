"""Beacon Command — API Router.

Aggregates all endpoint routers with the /api/v1 prefix.
"""

from __future__ import annotations

from fastapi import APIRouter

from beacon.api.routes import health, crises, evidence, missions, plans, tasks, decisions, events

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(health.router, tags=["health"])
api_router.include_router(crises.router, prefix="/crises", tags=["crises"])
api_router.include_router(evidence.router, prefix="/evidence", tags=["evidence"])
api_router.include_router(missions.router, prefix="/missions", tags=["missions"])
api_router.include_router(plans.router, prefix="/plans", tags=["plans"])
api_router.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
api_router.include_router(decisions.router, prefix="/decisions", tags=["decisions"])
api_router.include_router(events.router, prefix="/events", tags=["events"])
