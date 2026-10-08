"""
Unit and Integration Tests for IoT Environment Monitor Service
"""

import os
import sqlite3
# pyrefly: ignore [missing-import]
import pytest
from unittest.mock import MagicMock, patch

from service.monitor import (
    Config,
    TelemetryReading,
    PayloadParser,
    AlertEvaluator,
    DatabaseManager,
    EnvironmentMonitor,
)

class TestPayloadParser:
    def test_parse_valid_standard_json(self):
        payload = '{"temp": 27.4, "hum": 61}'
        reading = PayloadParser.parse(payload)
        assert reading is not None
        assert reading.temperature == 27.4
        assert reading.humidity == 61.0

    def test_parse_invalid_json_syntax(self):
        assert PayloadParser.parse("bad json") is None
