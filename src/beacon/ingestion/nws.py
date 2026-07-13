"""Beacon Command — NWS Weather Alerts Provider.

Polls the US National Weather Service API for active weather alerts.
Free, no API key required.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from beacon.db import get_session
from beacon.db.models.crisis import HazardEvent
from beacon.domain.enums import EventSourceType, HazardType
from beacon.events import event_publisher
from beacon.logging import get_logger
from sqlalchemy import select

logger = get_logger(__name__)

# NWS severity mapping
_NWS_SEVERITY_MAP = {
    "Extreme": ("extreme", 9.0),
    "Severe": ("severe", 7.0),
    "Moderate": ("moderate", 5.0),
    "Minor": ("low", 3.0),
    "Unknown": ("moderate", 4.0),
}


class NWSPoller:
    """Polls NWS API for active weather alerts.

    Uses: https://api.weather.gov/alerts/active
    """

    def __init__(self, base_url: str = "https://api.weather.gov"):
        self.base_url = base_url

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    async def fetch_alerts(self) -> dict[str, Any]:
        """Fetch active weather alerts."""
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{self.base_url}/alerts/active",
                headers={
                    "User-Agent": "BeaconCommand/1.0 (beacon-crisis-intelligence)",
                    "Accept": "application/geo+json",
                },
            )
            response.raise_for_status()
            return response.json()

    async def poll(self) -> list[uuid.UUID]:
        """Poll NWS alerts and persist new events."""
        try:
            data = await self.fetch_alerts()
        except Exception as e:
            logger.error("nws_fetch_failed", error=str(e))
            return []

        features = data.get("features", [])
        logger.info("nws_alerts_fetched", count=len(features))

        new_ids: list[uuid.UUID] = []
        for feature in features:
            try:
                eid = await self._process_alert(feature)
                if eid:
                    new_ids.append(eid)
            except Exception as e:
                logger.error("nws_alert_error", error=str(e))

        return new_ids

    async def _process_alert(self, feature: dict[str, Any]) -> Optional[uuid.UUID]:
        """Process a single NWS alert feature."""
        props = feature.get("properties", {})
        source_event_id = props.get("id", "")
        if not source_event_id:
            return None

        title = props.get("headline", props.get("event", "Weather Alert"))
        description = props.get("description", "")
        severity_str = props.get("severity", "Unknown")
        severity, severity_score = _NWS_SEVERITY_MAP.get(severity_str, ("moderate", 4.0))

        # Extract geography
        geometry = feature.get("geometry")
        lat, lon = None, None
        if geometry and geometry.get("type") == "Point":
            coords = geometry.get("coordinates", [])
            if len(coords) >= 2:
                lon, lat = coords[0], coords[1]

        # Parse times
        effective = props.get("effective")
        event_time = None
        if effective:
            try:
                event_time = datetime.fromisoformat(effective)
            except (ValueError, TypeError):
                pass

        import json
        raw_hash = hashlib.sha256(json.dumps(props, sort_keys=True, default=str).encode()).hexdigest()

        async with get_session() as session:
            existing = await session.execute(
                select(HazardEvent).where(
                    HazardEvent.source_event_id == source_event_id,
                    HazardEvent.source_type == EventSourceType.NWS.value,
                )
            )
            if existing.scalar_one_or_none():
                return None

            event = HazardEvent(
                source_type=EventSourceType.NWS.value,
                source_event_id=source_event_id,
                hazard_type=HazardType.SEVERE_WEATHER.value,
                title=title[:1000],
                description=description[:5000] if description else None,
                latitude=lat,
                longitude=lon,
                location_name=", ".join(props.get("areaDesc", "").split(",")[:3]),
                severity=severity,
                severity_score=severity_score,
                alert_level=severity_str,
                event_time=event_time,
                raw_payload_hash=raw_hash,
                source_url=props.get("@id", ""),
                raw_metadata={
                    "event": props.get("event"),
                    "urgency": props.get("urgency"),
                    "certainty": props.get("certainty"),
                    "category": props.get("category"),
                    "sender": props.get("senderName"),
                },
            )
            session.add(event)
            await session.flush()

            await event_publisher.publish(
                "hazard.observed",
                {
                    "source": "nws",
                    "event_id": str(event.id),
                    "event_type": props.get("event", "weather"),
                    "severity_score": severity_score,
                },
            )
            return event.id
