"""Beacon Command — USGS Earthquake Feed Poller.

Polls the actual USGS GeoJSON earthquake feed, normalizes events,
deduplicates by source event ID, and persists HazardEvent records.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import httpx
from sqlalchemy import select
from tenacity import retry, stop_after_attempt, wait_exponential

from beacon.db import get_session
from beacon.db.models.crisis import HazardEvent
from beacon.domain.enums import EventSourceType, HazardType
from beacon.events import event_publisher
from beacon.logging import get_logger

if TYPE_CHECKING:
    import uuid

logger = get_logger(__name__)


class USGSPoller:
    """Polls the USGS GeoJSON earthquake feed.

    Feed URL: https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_hour.geojson
    """

    def __init__(self, feed_url: str, min_magnitude: float = 4.0):
        self.feed_url = feed_url
        self.min_magnitude = min_magnitude

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    async def fetch_feed(self) -> dict[str, Any]:
        """Fetch the USGS GeoJSON feed."""
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(self.feed_url)
            response.raise_for_status()
            data: dict[str, Any] = response.json()
            return data

    async def poll(self) -> list[uuid.UUID]:
        """Poll the feed and persist new/updated events.

        Returns:
            List of new HazardEvent IDs created.
        """
        try:
            data = await self.fetch_feed()
        except Exception as e:
            logger.error("usgs_fetch_failed", error=str(e))
            return []

        if not isinstance(data, dict) or "features" not in data:
            keys = list(data.keys()) if isinstance(data, dict) else "not_dict"
            logger.error("usgs_invalid_payload", keys=keys)
            return []

        features = data.get("features", [])
        logger.info("usgs_feed_fetched", feature_count=len(features))

        new_event_ids: list[uuid.UUID] = []

        for feature in features:
            try:
                event_id = await self._process_feature(feature)
                if event_id:
                    new_event_ids.append(event_id)
            except Exception as e:
                logger.error(
                    "usgs_feature_processing_error",
                    error=str(e),
                    feature_id=feature.get("id"),
                )

        if new_event_ids:
            logger.info("usgs_new_events", count=len(new_event_ids))

        return new_event_ids

    def normalize_feature(self, feature: dict[str, Any]) -> dict[str, Any] | None:
        """Normalize a raw USGS GeoJSON feature into a source-agnostic dict.

        Pure function of the input feature (no I/O, no persistence). This is the
        single normalization path shared by live polling (:meth:`_process_feature`)
        and the offline scenario replay harness, so a replayed event traverses the
        exact same extraction, severity, and threshold logic as a live one.

        Returns ``None`` if the feature is unusable or below ``min_magnitude``.
        """
        props = feature.get("properties", {})
        geometry = feature.get("geometry", {})
        source_event_id = feature.get("id", "")

        if not source_event_id:
            return None

        # Extract coordinates [longitude, latitude, depth]
        coords = geometry.get("coordinates", [0, 0, 0])
        longitude = coords[0] if len(coords) > 0 else None
        latitude = coords[1] if len(coords) > 1 else None
        depth_km = coords[2] if len(coords) > 2 else None

        magnitude = props.get("mag")
        if magnitude is not None and magnitude < self.min_magnitude:
            return None

        # Parse timestamps
        event_time_ms = props.get("time")
        event_time = (
            datetime.fromtimestamp(event_time_ms / 1000, tz=UTC)
            if event_time_ms
            else None
        )
        updated_ms = props.get("updated")
        updated_at = (
            datetime.fromtimestamp(updated_ms / 1000, tz=UTC)
            if updated_ms
            else None
        )

        # Compute severity score (0-10)
        severity_score = self._compute_severity(magnitude, depth_km, props)
        severity = self._magnitude_to_severity(magnitude)

        # Raw payload hash for deduplication
        import json
        raw_hash = hashlib.sha256(json.dumps(feature, sort_keys=True).encode()).hexdigest()

        place = props.get("place", "")
        return {
            "source_type": EventSourceType.USGS.value,
            "source_event_id": source_event_id,
            "hazard_type": HazardType.EARTHQUAKE.value,
            "title": props.get("title", f"M{magnitude} Earthquake"),
            "description": place,
            "latitude": latitude,
            "longitude": longitude,
            "depth_km": depth_km,
            "location_name": place,
            "location": place,
            "magnitude": magnitude,
            "severity": severity,
            "severity_score": severity_score,
            "alert_level": props.get("alert"),
            "event_time": event_time,
            "updated_at_source": updated_at,
            "tsunami_flag": bool(props.get("tsunami", 0)),
            "source_url": props.get("url", ""),
            "raw_metadata": props,
            "raw_payload_hash": raw_hash,
        }

    async def _process_feature(self, feature: dict[str, Any]) -> uuid.UUID | None:
        """Process a single GeoJSON feature into a HazardEvent."""
        normalized = self.normalize_feature(feature)
        if normalized is None:
            return None

        source_event_id = normalized["source_event_id"]
        raw_hash = normalized["raw_payload_hash"]
        magnitude = normalized["magnitude"]
        severity_score = normalized["severity_score"]
        severity = normalized["severity"]
        updated_at = normalized["updated_at_source"]

        # Check if already exists
        async with get_session() as session:
            existing = await session.execute(
                select(HazardEvent).where(
                    HazardEvent.source_event_id == source_event_id,
                    HazardEvent.source_type == EventSourceType.USGS.value,
                )
            )
            existing_event = existing.scalar_one_or_none()

            if existing_event:
                # Check if this is an update (different hash)
                if existing_event.raw_payload_hash == raw_hash:
                    return None  # Duplicate, skip

                # Update existing event
                existing_event.magnitude = magnitude
                existing_event.severity_score = severity_score
                existing_event.severity = severity
                existing_event.updated_at_source = updated_at
                existing_event.raw_payload_hash = raw_hash
                existing_event.is_update = True
                existing_event.raw_metadata = normalized["raw_metadata"]

                await event_publisher.publish(
                    "hazard.normalized",
                    {"source": "usgs", "event_id": str(existing_event.id), "is_update": True},
                )
                return None  # Not a new event

            # Create new event
            event = HazardEvent(
                source_type=normalized["source_type"],
                source_event_id=source_event_id,
                hazard_type=normalized["hazard_type"],
                title=normalized["title"],
                description=normalized["description"],
                latitude=normalized["latitude"],
                longitude=normalized["longitude"],
                depth_km=normalized["depth_km"],
                location_name=normalized["location_name"],
                magnitude=magnitude,
                severity=severity,
                severity_score=severity_score,
                alert_level=normalized["alert_level"],
                event_time=normalized["event_time"],
                updated_at_source=updated_at,
                tsunami_flag=normalized["tsunami_flag"],
                raw_payload_hash=raw_hash,
                source_url=normalized["source_url"],
                raw_metadata=normalized["raw_metadata"],
            )
            session.add(event)
            await session.flush()

            await event_publisher.publish(
                "hazard.observed",
                {
                    "source": "usgs",
                    "event_id": str(event.id),
                    "source_event_id": source_event_id,
                    "magnitude": magnitude,
                    "severity_score": severity_score,
                    "location": normalized["location_name"],
                },
            )

            return event.id

    def _compute_severity(
        self,
        magnitude: float | None,
        depth_km: float | None,
        props: dict[str, Any],
    ) -> float:
        """Compute deterministic severity score (0-10)."""
        score = 0.0

        if magnitude is not None:
            # Magnitude contribution (0-6 points)
            if magnitude >= 8.0:
                score += 6.0
            elif magnitude >= 7.0:
                score += 5.0
            elif magnitude >= 6.0:
                score += 4.0
            elif magnitude >= 5.0:
                score += 3.0
            elif magnitude >= 4.0:
                score += 2.0
            else:
                score += 1.0

        # Depth contribution (0-2 points) — shallower is more dangerous
        if depth_km is not None:
            if depth_km < 10:
                score += 2.0
            elif depth_km < 30:
                score += 1.5
            elif depth_km < 70:
                score += 1.0
            else:
                score += 0.5

        # Tsunami flag (0-1 point)
        if props.get("tsunami", 0):
            score += 1.0

        # Alert level from USGS (0-1 point)
        alert = props.get("alert", "")
        if alert == "red":
            score += 1.0
        elif alert == "orange":
            score += 0.7
        elif alert == "yellow":
            score += 0.4

        return min(score, 10.0)

    def _magnitude_to_severity(self, magnitude: float | None) -> str:
        """Map magnitude to severity category."""
        if magnitude is None:
            return "moderate"
        if magnitude >= 7.0:
            return "extreme"
        if magnitude >= 6.0:
            return "severe"
        if magnitude >= 5.0:
            return "high"
        if magnitude >= 4.0:
            return "moderate"
        return "low"
