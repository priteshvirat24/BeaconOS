"""Beacon Command — GDACS Feed Parser.

Polls the GDACS RSS/GeoRSS feed for global disaster alerts.
"""

from __future__ import annotations

import contextlib
import hashlib
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import feedparser  # type: ignore[import-untyped]
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

    def normalize_entry(self, entry: dict[str, Any]) -> dict[str, Any] | None:
        """Normalize a raw GDACS feed entry into a source-agnostic dict.

        Pure function of the input entry (no I/O). Shared by live polling
        (:meth:`_process_entry`) and the offline scenario replay harness so both
        paths apply identical hazard-type, severity, and geography extraction.
        """
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
            with contextlib.suppress(ValueError, TypeError):
                lat = float(entry["geo_lat"])
        if "geo_long" in entry:
            with contextlib.suppress(ValueError, TypeError):
                lon = float(entry["geo_long"])

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
                    time.mktime(entry["published_parsed"]), tz=UTC
                )
            except Exception:
                pass

        # Compute content hash
        import json
        raw_bytes = json.dumps(entry, sort_keys=True, default=str).encode()
        raw_hash = hashlib.sha256(raw_bytes).hexdigest()

        country = gdacs_data.get("gdacs_country", "")
        return {
            "source_type": EventSourceType.GDACS.value,
            "source_event_id": source_event_id,
            "hazard_type": hazard_type.value,
            "title": title,
            "description": description,
            "latitude": lat,
            "longitude": lon,
            "location_name": country,
            "location": country or title,
            "magnitude": None,
            "severity": severity,
            "severity_score": severity_score,
            "alert_level": severity_str,
            "event_time": event_time,
            "source_url": entry.get("link", ""),
            "raw_metadata": gdacs_data,
            "raw_payload_hash": raw_hash,
        }

    async def _process_entry(self, entry: dict[str, Any]) -> uuid.UUID | None:
        """Process a single GDACS RSS entry."""
        normalized = self.normalize_entry(entry)
        if normalized is None:
            return None

        source_event_id = normalized["source_event_id"]

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
                source_type=normalized["source_type"],
                source_event_id=source_event_id,
                hazard_type=normalized["hazard_type"],
                title=normalized["title"],
                description=normalized["description"],
                latitude=normalized["latitude"],
                longitude=normalized["longitude"],
                location_name=normalized["location_name"],
                severity=normalized["severity"],
                severity_score=normalized["severity_score"],
                alert_level=normalized["alert_level"],
                event_time=normalized["event_time"],
                raw_payload_hash=normalized["raw_payload_hash"],
                source_url=normalized["source_url"],
                raw_metadata=normalized["raw_metadata"],
            )
            session.add(event)
            await session.flush()

            await event_publisher.publish(
                "hazard.observed",
                {
                    "source": "gdacs",
                    "event_id": str(event.id),
                    "source_event_id": source_event_id,
                    "hazard_type": normalized["hazard_type"],
                    "severity_score": normalized["severity_score"],
                },
            )
            return event.id
