"""Beacon Command — Ingestion Scheduler.

Manages periodic polling of all hazard feed sources.
"""

from __future__ import annotations

import asyncio

from beacon.config import BeaconSettings
from beacon.logging import get_logger

logger = get_logger(__name__)


async def start_ingestion_scheduler(settings: BeaconSettings) -> None:
    """Start all hazard feed pollers on their configured intervals."""

    async def _poll_loop(
        name: str,
        poll_fn: Any,
        interval: int,
    ) -> None:
        """Run a poller on a fixed interval."""
        logger.info("ingestion_poller_started", source=name, interval_seconds=interval)
        while True:
            try:
                result = await poll_fn()
                if result:
                    logger.info("ingestion_poll_result", source=name, new_events=len(result))
            except asyncio.CancelledError:
                logger.info("ingestion_poller_cancelled", source=name)
                return
            except Exception as e:
                logger.error("ingestion_poll_error", source=name, error=str(e))

            await asyncio.sleep(interval)

    tasks = []

    # USGS Earthquake poller
    from beacon.ingestion.usgs import USGSPoller

    usgs = USGSPoller(
        feed_url=settings.usgs_feed_url,
        min_magnitude=settings.hazard_min_magnitude,
    )
    tasks.append(
        asyncio.create_task(
            _poll_loop("usgs", usgs.poll, settings.usgs_poll_interval_seconds)
        )
    )

    # GDACS poller
    if settings.gdacs_feed_url:
        from beacon.ingestion.gdacs import GDACSPoller

        gdacs = GDACSPoller(feed_url=settings.gdacs_feed_url)
        tasks.append(
            asyncio.create_task(
                _poll_loop("gdacs", gdacs.poll, settings.gdacs_poll_interval_seconds)
            )
        )

    # NWS Weather poller
    if settings.weather_provider.value == "nws":
        from beacon.ingestion.nws import NWSPoller

        nws = NWSPoller(base_url=settings.weather_base_url or "https://api.weather.gov")
        tasks.append(
            asyncio.create_task(
                _poll_loop("nws", nws.poll, 300)  # 5 min default for weather
            )
        )

    # Wait for all tasks (they run indefinitely until cancelled)
    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        for task in tasks:
            task.cancel()
        logger.info("ingestion_scheduler_stopped")
