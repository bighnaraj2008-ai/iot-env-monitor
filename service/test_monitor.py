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


# =========================================================================
# PayloadParser Tests
# =========================================================================

class TestPayloadParser:
    """Tests for JSON payload parsing and data validation."""

    def test_parse_valid_standard_json(self):
        payload = '{"temp": 27.4, "hum": 61}'
        reading = PayloadParser.parse(payload)

        assert reading is not None
        assert reading.temperature == 27.4
        assert reading.humidity == 61.0
        assert reading.raw_payload == payload
        assert reading.timestamp != ""

    def test_parse_valid_bytes(self):
        payload_bytes = b'{"temp": 22.5, "hum": 55.2}'
        reading = PayloadParser.parse(payload_bytes)

        assert reading is not None
        assert reading.temperature == 22.5
        assert reading.humidity == 55.2

    def test_parse_alternative_keys(self):
        payload = '{"temperature": 29.8, "humidity": 70.1}'
        reading = PayloadParser.parse(payload)

        assert reading is not None
        assert reading.temperature == 29.8
        assert reading.humidity == 70.1

    def test_parse_integer_values(self):
        payload = '{"temp": 30, "hum": 50}'
        reading = PayloadParser.parse(payload)

        assert reading is not None
        assert reading.temperature == 30.0
        assert reading.humidity == 50.0

    def test_parse_string_numbers(self):
        payload = '{"temp": "28.5", "hum": "62.4"}'
        reading = PayloadParser.parse(payload)

        assert reading is not None
        assert reading.temperature == 28.5
        assert reading.humidity == 62.4

    def test_parse_invalid_json_syntax(self):
        invalid_payloads = [
            "not a json",
            '{"temp": 27.4,',
            "",
            "   ",
            "{}}",
        ]
        for p in invalid_payloads:
            assert PayloadParser.parse(p) is None

    def test_parse_missing_required_keys(self):
        # Missing hum
        assert PayloadParser.parse('{"temp": 25.0}') is None
        # Missing temp
        assert PayloadParser.parse('{"hum": 60.0}') is None
        # Empty json object
        assert PayloadParser.parse("{}") is None

    def test_parse_non_numeric_values(self):
        assert PayloadParser.parse('{"temp": "cold", "hum": 60}') is None
        assert PayloadParser.parse('{"temp": 25.0, "hum": "wet"}') is None

    def test_parse_nan_values(self):
        assert PayloadParser.parse('{"temp": NaN, "hum": 60}') is None

    def test_parse_non_dict_root(self):
        assert PayloadParser.parse("[27.4, 61]") is None
        assert PayloadParser.parse('"just a string"') is None


# =========================================================================
# AlertEvaluator Tests
# =========================================================================

class TestAlertEvaluator:
    """Tests for threshold evaluation logic."""

    def test_temperature_below_threshold(self):
        evaluator = AlertEvaluator(temp_threshold=30.0)
        reading = TelemetryReading(temperature=27.4, humidity=61.0, raw_payload="{}")
        is_alert, reason = evaluator.evaluate(reading)

        assert is_alert is False
        assert reason is None

    def test_temperature_at_exact_threshold(self):
        evaluator = AlertEvaluator(temp_threshold=30.0)
        reading = TelemetryReading(temperature=30.0, humidity=61.0, raw_payload="{}")
        is_alert, reason = evaluator.evaluate(reading)

        assert is_alert is False
        assert reason is None

    def test_temperature_exceeds_threshold(self):
        evaluator = AlertEvaluator(temp_threshold=30.0)
        reading = TelemetryReading(temperature=31.2, humidity=61.0, raw_payload="{}")
        is_alert, reason = evaluator.evaluate(reading)

        assert is_alert is True
        assert reason is not None
        assert "Temperature (31.2 °C) exceeded threshold (30.0 °C)" in reason

    def test_humidity_threshold_triggered(self):
        evaluator = AlertEvaluator(temp_threshold=35.0, hum_threshold=80.0)
        reading = TelemetryReading(temperature=26.0, humidity=85.5, raw_payload="{}")
        is_alert, reason = evaluator.evaluate(reading)

        assert is_alert is True
        assert "Humidity (85.5 %) exceeded threshold (80.0 %)" in reason

    def test_both_thresholds_exceeded(self):
        evaluator = AlertEvaluator(temp_threshold=30.0, hum_threshold=70.0)
        reading = TelemetryReading(temperature=32.0, humidity=75.0, raw_payload="{}")
        is_alert, reason = evaluator.evaluate(reading)

        assert is_alert is True
        assert "Temperature" in reason
        assert "Humidity" in reason


# =========================================================================
# DatabaseManager Tests
# =========================================================================

class TestDatabaseManager:
    """Tests for SQLite database operations."""

    @pytest.fixture
    def in_memory_db(self):
        """Creates an in-memory DatabaseManager for testing."""
        db = DatabaseManager(db_path=":memory:")
        yield db
        db.close()

    def test_database_initialization_schema(self, in_memory_db):
        conn = in_memory_db._get_connection()
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='env_readings'"
        )
        assert cursor.fetchone() is not None

    def test_insert_reading_normal(self, in_memory_db):
        reading = TelemetryReading(
            temperature=24.5,
            humidity=55.0,
            raw_payload='{"temp": 24.5, "hum": 55.0}',
        )
        row_id = in_memory_db.insert_reading(
            topic="home/room1/env",
            reading=reading,
            is_alert=False,
        )

        assert row_id == 1
        assert in_memory_db.count_readings() == 1
        assert in_memory_db.count_alerts() == 0

        recent = in_memory_db.get_recent_readings(limit=10)
        assert len(recent) == 1
        record = recent[0]
        assert record["temperature"] == 24.5
        assert record["humidity"] == 55.0
        assert record["is_alert"] == 0
        assert record["alert_reason"] is None

    def test_insert_reading_alert(self, in_memory_db):
        reading = TelemetryReading(
            temperature=33.1,
            humidity=60.0,
            raw_payload='{"temp": 33.1, "hum": 60.0}',
        )
        row_id = in_memory_db.insert_reading(
            topic="home/room1/env",
            reading=reading,
            is_alert=True,
            alert_reason="Temperature (33.1 °C) exceeded threshold (30.0 °C)",
        )

        assert row_id == 1
        assert in_memory_db.count_readings() == 1
        assert in_memory_db.count_alerts() == 1

        recent = in_memory_db.get_recent_readings(limit=1)
        assert recent[0]["is_alert"] == 1
        assert "exceeded threshold" in recent[0]["alert_reason"]

    def test_query_recent_readings_limit(self, in_memory_db):
        for i in range(5):
            reading = TelemetryReading(
                temperature=20.0 + i,
                humidity=50.0,
                raw_payload=f'{{"temp": {20.0 + i}, "hum": 50.0}}',
            )
            in_memory_db.insert_reading("home/room1/env", reading, is_alert=False)

        assert in_memory_db.count_readings() == 5
        records = in_memory_db.get_recent_readings(limit=3)
        assert len(records) == 3
        # Most recent should be temperature 24.0
        assert records[0]["temperature"] == 24.0


# =========================================================================
# EnvironmentMonitor Integration Tests
# =========================================================================

class TestEnvironmentMonitor:
    """Tests for EnvironmentMonitor orchestrator logic."""

    @pytest.fixture
    def monitor_service(self):
        config = Config(
            broker="localhost",
            port=1883,
            topic="home/room1/env",
            temp_threshold=30.0,
            db_path=":memory:",
        )
        db = DatabaseManager(db_path=":memory:")
        monitor = EnvironmentMonitor(config=config, db_manager=db)
        yield monitor
        monitor.stop()

    def test_process_payload_valid_normal(self, monitor_service):
        row_id = monitor_service.process_payload(
            topic="home/room1/env",
            payload='{"temp": 26.5, "hum": 58}',
        )
        assert row_id is not None
        assert monitor_service.db.count_readings() == 1
        assert monitor_service.db.count_alerts() == 0

    def test_process_payload_triggers_alert(self, monitor_service):
        row_id = monitor_service.process_payload(
            topic="home/room1/env",
            payload='{"temp": 34.2, "hum": 62}',
        )
        assert row_id is not None
        assert monitor_service.db.count_readings() == 1
        assert monitor_service.db.count_alerts() == 1

        recent = monitor_service.db.get_recent_readings(1)
        assert recent[0]["is_alert"] == 1
        assert "34.2" in recent[0]["alert_reason"]

    def test_process_payload_corrupted_does_not_insert(self, monitor_service):
        row_id = monitor_service.process_payload(
            topic="home/room1/env",
            payload='{"broken_json": ',
        )
        assert row_id is None
        assert monitor_service.db.count_readings() == 0

    def test_mqtt_message_callback(self, monitor_service):
        mock_msg = MagicMock()
        mock_msg.topic = "home/room1/env"
        mock_msg.payload = b'{"temp": 28.0, "hum": 65}'

        monitor_service._on_message(None, None, mock_msg)
        assert monitor_service.db.count_readings() == 1


# =========================================================================
# Configuration Tests
# =========================================================================

class TestConfig:
    """Tests for configuration parsing."""

    def test_default_config(self):
        config = Config()
        assert config.broker == "localhost"
        assert config.port == 1883
        assert config.topic == "home/room1/env"
        assert config.temp_threshold == 30.0
        assert config.db_path == "env_data.db"

    def test_from_args_custom(self):
        import argparse
        args = argparse.Namespace(
            broker="10.0.0.1",
            port=1885,
            topic="custom/topic",
            temp_threshold=32.5,
            db="custom.db",
            log_level="DEBUG",
        )
        config = Config.from_args(args)
        assert config.broker == "10.0.0.1"
        assert config.port == 1885
        assert config.topic == "custom/topic"
        assert config.temp_threshold == 32.5
        assert config.db_path == "custom.db"
        assert config.log_level == "DEBUG"

    def test_from_args_empty_defaults(self):
        import argparse
        args = argparse.Namespace(
            broker=None,
            port=None,
            topic=None,
            temp_threshold=None,
            db=None,
            log_level=None,
        )
        config = Config.from_args(args)
        assert config.broker == "localhost"
        assert config.port == 1883


# =========================================================================
# CLI and Helper Tests
# =========================================================================

class TestCliHelpers:
    """Tests for CLI arguments and logging initialization."""

    def test_setup_logging(self):
        from service.monitor import setup_logging
        import logging
        setup_logging("DEBUG")
        assert logging.getLogger().level == logging.DEBUG
        setup_logging("INFO")
        assert logging.getLogger().level == logging.INFO

    def test_parse_arguments(self):
        from service.monitor import parse_arguments
        with patch("sys.argv", ["monitor.py", "--broker", "test.mosquitto.org", "--port", "1883"]):
            args = parse_arguments()
            assert args.broker == "test.mosquitto.org"
            assert args.port == 1883

