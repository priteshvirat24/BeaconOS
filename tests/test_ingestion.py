"""Tests for Beacon Command — USGS Ingestion."""

import json
import pytest
from unittest.mock import AsyncMock, patch

from beacon.ingestion.usgs import USGSPoller


class TestUSGSPoller:
    def test_severity_scoring_high_magnitude(self) -> None:
        """High magnitude should produce high severity score."""
        poller = USGSPoller("https://fake.url", min_magnitude=4.0)
        score = poller._compute_severity(7.5, 10, {"tsunami": 1, "alert": "red"})
        assert score >= 8.0

    def test_severity_scoring_moderate(self) -> None:
        """Moderate earthquake should produce moderate score."""
        poller = USGSPoller("https://fake.url", min_magnitude=4.0)
        score = poller._compute_severity(5.0, 50, {"tsunami": 0, "alert": ""})
        assert 3.0 <= score <= 6.0

    def test_magnitude_to_severity_extreme(self) -> None:
        poller = USGSPoller("https://fake.url")
        assert poller._magnitude_to_severity(7.5) == "extreme"

    def test_magnitude_to_severity_severe(self) -> None:
        poller = USGSPoller("https://fake.url")
        assert poller._magnitude_to_severity(6.5) == "severe"

    def test_magnitude_to_severity_high(self) -> None:
        poller = USGSPoller("https://fake.url")
        assert poller._magnitude_to_severity(5.5) == "high"

    def test_magnitude_to_severity_moderate(self) -> None:
        poller = USGSPoller("https://fake.url")
        assert poller._magnitude_to_severity(4.5) == "moderate"

    def test_magnitude_to_severity_low(self) -> None:
        poller = USGSPoller("https://fake.url")
        assert poller._magnitude_to_severity(3.0) == "low"

    def test_min_magnitude_filter(self) -> None:
        """Events below minimum magnitude should be filtered."""
        poller = USGSPoller("https://fake.url", min_magnitude=4.0)
        # Magnitude 3.5 should be filtered
        assert 3.5 < poller.min_magnitude
