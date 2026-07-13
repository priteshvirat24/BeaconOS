"""Beacon Command — GDACS Feed Parser.

Polls the GDACS RSS/GeoRSS feed for global disaster alerts.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
import feedparser
from tenacity import retry, stop_after_attempt, wait_exponential

from beacon.db import get_session
from beacon.db.models.crisis import HazardEvent
from beacon.domain.enums import EventSourceType, HazardType
from beacon.events import event_publisher
from beacon.logging import get_logger
from sqlalchemy import select

logger = get_logger(__name__)

# Map GDACS event types to HazardType
_GDACS_TYPE_MAP = {
    "EQ": HazardType.EARTHQUAKE,
    "TC": HazardType.CYCLONE,
    "FL": HazardType.FLOOD,
    "VO": HazardType.VOLCANO,
    "DR": HazardType.DROUGHT,
    "WF": HazardType.WILDFIRE,
    "TS": HazardType.TSUNAMI,
}


class GDACSPoller:
    """Polls the GDACS RSS feed for global disaster alerts."""

    def __init__(self, feed_url: str = "https://www.gdacs.org/xml/rss.xml"):
        self.feed_url = feed_url

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    async def fetch_feed(self) -> str:
        """Fetch the raw RSS feed."""
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(self.feed_url)
            response.raise_for_status()
            return response.text

    async def poll(self) -> list[uuid.UUID]:
        """Poll the GDACS feed and persist new events."""
        try:
            raw_feed = await self.fetch_feed()
        except Exception as e:
            logger.error("gdacs_fetch_failed", error=str(e))
            return []

        feed = feedparser.parse(raw_feed)
        entries = feed.get("entries", [])
        logger.info("gdacs_feed_fetched", entry_count=len(entries))

        new_event_ids: list[uuid.UUID] = []

        for entry in entries:
            try:
                event_id = await self._process_entry(entry)
                if event_id:
                    new_event_ids.append(event_id)
            except Exception as e:
                logger.error("gdacs_entry_error", error=str(e), entry_id=entry.get("id"))

        return new_event_ids

    async def _process_entry(self, entry: dict[str, Any]) -> Optional[uuid.UUID]:
        """Process a single GDACS RSS entry."""
        source_event_id = entry.get("id", entry.get("link", ""))
        if not source_event_id:
            return None

        title = entry.get("title", "Unknown Event")
        description = entry.get("summary", "")

        # Extract GDACS-specific fields
        gdacs_data = {}
        for key in entry:
            if key.startswith("gdacs_"):
                gdacs_data[key] = entry[key]

        # Determine hazard type
        event_type_str = gdacs_data.get("gdacs_eventtype", "")
        hazard_type = _GDACS_TYPE_MAP.get(event_type_str, HazardType.OTHER)

        # Extract severity
        severity_str = gdacs_data.get("gdacs_alertlevel", "").lower()
        severity = severity_str if severity_str in ("green", "orange", "red") else "moderate"
        severity_score = {"red": 8.0, "orange": 5.0, "green": 2.0}.get(severity, 3.0)

        # Extract geography from GeoRSS
        lat = None
        lon = None
        if "geo_lat" in entry:
            try:
                lat = float(entry["geo_lat"])
            except (ValueError, TypeError):
                pass
        if "geo_long" in entry:
            try:
                lon = float(entry["geo_long"])
            except (ValueError, TypeError):
                pass

        # Alternatively check georss_point
        if lat is None and "georss_point" in entry:
            try:
                parts = entry["georss_point"].split()
                lat, lon = float(parts[0]), float(parts[1])
            except (ValueError, IndexError):
                pass

        # Parse publish date
        event_time = None
        if entry.get("published_parsed"):
            try:
                import time
                event_time = datetime.fromtimestamp(
                    time.mktime(entry["published_parsed"]), tz=timezone.utc
                )
            except Exception:
                pass

        # Compute content hash
        import json
        raw_hash = hashlib.sha256(json.dumps(entry, sort_keys=True, default=str).encode()).hexdigest()

        # Check for duplicate
        async with get_session() as session:
            existing = await session.execute(
                select(HazardEvent).where(
                    HazardEvent.source_event_id == source_event_id,
                    HazardEvent.source_type == EventSourceType.GDACS.value,
                )
            )
            if existing.scalar_one_or_none():
                return None  # Already exists

            event = HazardEvent(
                source_type=EventSourceType.GDACS.value,
                source_event_id=source_event_id,
                hazard_type=hazard_type.value,
                title=title,
                description=description,
                latitude=lat,
                longitude=lon,
                location_name=gdacs_data.get("gdacs_country", ""),
                severity=severity,
                severity_score=severity_score,
                alert_level=severity_str,
                event_time=event_time,
                raw_payload_hash=raw_hash,
                source_url=entry.get("link", ""),
                raw_metadata=gdacs_data,
            )
            session.add(event)
            await session.flush()

            await event_publisher.publish(
                "hazard.observed",
                {
                    "source": "gdacs",
                    "event_id": str(event.id),
                    "source_event_id": source_event_id,
                    "hazard_type": hazard_type.value,
                    "severity_score": severity_score,
                },
            )
            return event.id
