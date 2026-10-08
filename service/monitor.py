"""
IoT Environment Monitor - Backend Service

Subscribes to MQTT environmental telemetry (from ESP32 / DHT22),
stores readings into an SQLite database, evaluates values against
thresholds, and triggers alerts upon threshold breach.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
import math
import os
import signal
import sqlite3
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

# Optional dotenv support
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# MQTT client import with cross-version compatibility (Paho MQTT v1 and v2)
try:
    # pyrefly: ignore [missing-import]
    import paho.mqtt.client as mqtt
    try:
        # pyrefly: ignore [missing-import]
        from paho.mqtt.enums import CallbackAPIVersion
        PAHO_V2 = True
    except (ImportError, AttributeError):
        PAHO_V2 = False
except ImportError:
    mqtt = None
    PAHO_V2 = False


# =========================================================================
# Configuration
# =========================================================================

@dataclass
class Config:
    """Runtime configuration container loaded from environment variables."""
    broker: str = os.getenv("MQTT_BROKER", "localhost")
    port: int = int(os.getenv("MQTT_PORT", "1883"))
    topic: str = os.getenv("MQTT_TOPIC", "home/room1/env")
    client_id: str = os.getenv("MQTT_CLIENT_ID", f"python-env-monitor-{os.getpid()}")
    keepalive: int = int(os.getenv("MQTT_KEEPALIVE", "60"))
    username: Optional[str] = os.getenv("MQTT_USERNAME", None) or None
    password: Optional[str] = os.getenv("MQTT_PASSWORD", None) or None
    temp_threshold: float = float(os.getenv("TEMP_THRESHOLD", "30.0"))
    hum_threshold: Optional[float] = float(os.getenv("HUM_THRESHOLD", "85.0")) if os.getenv("HUM_THRESHOLD") else None
    db_path: str = os.getenv("DB_PATH", "env_data.db")
    log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> Config:
        """Create Config instance merging CLI arguments with environment variables."""
        return cls(
            broker=args.broker or os.getenv("MQTT_BROKER", "localhost"),
            port=int(args.port or os.getenv("MQTT_PORT", "1883")),
            topic=args.topic or os.getenv("MQTT_TOPIC", "home/room1/env"),
            temp_threshold=float(args.temp_threshold if args.temp_threshold is not None else os.getenv("TEMP_THRESHOLD", "30.0")),
            db_path=args.db or os.getenv("DB_PATH", "env_data.db"),
            log_level=(args.log_level or os.getenv("LOG_LEVEL", "INFO")).upper(),
        )


# =========================================================================
# Telemetry Models & Parsing
# =========================================================================

@dataclass
class TelemetryReading:
    """Structured telemetry reading from environmental sensor."""
    temperature: float
    humidity: float
    raw_payload: str
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


class PayloadParser:
    """Safely decodes and validates incoming JSON sensor payloads."""

    @staticmethod
    def parse(raw_data: str | bytes) -> Optional[TelemetryReading]:
        """
        Parses raw payload into a TelemetryReading.
        
        Expected JSON format: {"temp": 27.4, "hum": 61}
        Also accepts alternative keys like "temperature" and "humidity".
        """
        try:
            if isinstance(raw_data, bytes):
                decoded_str = raw_data.decode("utf-8", errors="replace")
            else:
                decoded_str = str(raw_data)

            if not decoded_str.strip():
                logging.warning("[PARSER] Received empty payload string")
                return None

            data = json.loads(decoded_str)
            if not isinstance(data, dict):
                logging.warning("[PARSER] JSON root is not an object: %s", decoded_str)
                return None

            # Retrieve temperature with fallback keys
            raw_temp = data.get("temp", data.get("temperature"))
            raw_hum = data.get("hum", data.get("humidity"))

            if raw_temp is None or raw_hum is None:
                logging.warning(
                    "[PARSER] Missing required keys ('temp'/'temperature' or 'hum'/'humidity'): %s",
                    decoded_str,
                )
                return None

            temperature = float(raw_temp)
            humidity = float(raw_hum)

            if math.isnan(temperature) or math.isnan(humidity):
                logging.warning("[PARSER] Discarded NaN sensor readings: %s", decoded_str)
                return None

            return TelemetryReading(
                temperature=round(temperature, 2),
                humidity=round(humidity, 2),
                raw_payload=decoded_str,
            )

        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            logging.error("[PARSER] Failed to parse payload: %s | Error: %s", raw_data, exc)
            return None


# =========================================================================
# Alert Evaluation
# =========================================================================

class AlertEvaluator:
    """Evaluates environmental readings against configured threshold rules."""

    def __init__(self, temp_threshold: float = 30.0, hum_threshold: Optional[float] = None):
        self.temp_threshold = temp_threshold
        self.hum_threshold = hum_threshold

    def evaluate(self, reading: TelemetryReading) -> Tuple[bool, Optional[str]]:
        """
        Evaluates a reading. Returns (is_alert, alert_reason).
        """
        reasons = []

        if reading.temperature > self.temp_threshold:
            reasons.append(
                f"Temperature ({reading.temperature:.1f} °C) exceeded threshold ({self.temp_threshold:.1f} °C)"
            )

        if self.hum_threshold is not None and reading.humidity > self.hum_threshold:
            reasons.append(
                f"Humidity ({reading.humidity:.1f} %) exceeded threshold ({self.hum_threshold:.1f} %)"
            )

        if reasons:
            combined_reason = "; ".join(reasons)
            logging.warning("[ALERT TRIGGERED] %s", combined_reason)
            return True, combined_reason

        return False, None


# =========================================================================
# Database Storage (SQLite)
# =========================================================================

class DatabaseManager:
    """Manages SQLite storage for environmental telemetry readings."""

    def __init__(self, db_path: str = "env_data.db"):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._connection: Optional[sqlite3.Connection] = None
        self._init_database()

    def _get_connection(self) -> sqlite3.Connection:
        """Returns or creates the database connection."""
        if self._connection is None:
            # check_same_thread=False allows sharing across MQTT worker threads with our mutex
            self._connection = sqlite3.connect(self.db_path, check_same_thread=False)
            self._connection.row_factory = sqlite3.Row
        return self._connection

    def _init_database(self) -> None:
        """Initializes database schema and indices."""
        with self._lock:
            conn = self._get_connection()
            with conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS env_readings (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        topic TEXT NOT NULL,
                        temperature REAL NOT NULL,
                        humidity REAL NOT NULL,
                        is_alert INTEGER NOT NULL DEFAULT 0,
                        alert_reason TEXT,
                        raw_payload TEXT
                    )
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON env_readings (timestamp)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_is_alert ON env_readings (is_alert)")
        logging.info("[DATABASE] Initialized SQLite database at '%s'", self.db_path)

    def insert_reading(
        self,
        topic: str,
        reading: TelemetryReading,
        is_alert: bool,
        alert_reason: Optional[str] = None,
    ) -> int:
        """Inserts a new environmental reading record and returns the inserted row ID."""
        with self._lock:
            conn = self._get_connection()
            with conn:
                cursor = conn.execute(
                    """
                    INSERT INTO env_readings (
                        timestamp, topic, temperature, humidity, is_alert, alert_reason, raw_payload
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        reading.timestamp,
                        topic,
                        reading.temperature,
                        reading.humidity,
                        1 if is_alert else 0,
                        alert_reason,
                        reading.raw_payload,
                    ),
                )
                return cursor.lastrowid

    def get_recent_readings(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Retrieves the most recent telemetry readings."""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.execute(
                """
                SELECT id, timestamp, topic, temperature, humidity, is_alert, alert_reason, raw_payload
                FROM env_readings
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def count_readings(self) -> int:
        """Returns total number of recorded telemetry entries."""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.execute("SELECT COUNT(*) FROM env_readings")
            return cursor.fetchone()[0]

    def count_alerts(self) -> int:
        """Returns total number of alert records."""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.execute("SELECT COUNT(*) FROM env_readings WHERE is_alert = 1")
            return cursor.fetchone()[0]

    def close(self) -> None:
        """Closes the underlying database connection."""
        with self._lock:
            if self._connection:
                self._connection.close()
                self._connection = None
                logging.info("[DATABASE] Closed SQLite connection.")


# =========================================================================
# MQTT Monitor Service Orchestrator
# =========================================================================

class EnvironmentMonitor:
    """Core MQTT service that subscribes, logs, and checks threshold alerts."""

    def __init__(self, config: Config, db_manager: Optional[DatabaseManager] = None):
        self.config = config
        self.db = db_manager or DatabaseManager(config.db_path)
        self.evaluator = AlertEvaluator(config.temp_threshold, config.hum_threshold)
        self.parser = PayloadParser()
        self._running = False
        self._mqtt_client: Any = None
        self._setup_mqtt_client()

    def _setup_mqtt_client(self) -> None:
        """Configures the Paho MQTT client."""
        if mqtt is None:
            logging.error("[MQTT] paho-mqtt package is not installed!")
            return

        if PAHO_V2:
            self._mqtt_client = mqtt.Client(
                CallbackAPIVersion.VERSION2,
                client_id=self.config.client_id,
            )
        else:
            self._mqtt_client = mqtt.Client(client_id=self.config.client_id)

        if self.config.username:
            self._mqtt_client.username_pw_set(self.config.username, self.config.password)

        self._mqtt_client.on_connect = self._on_connect
        self._mqtt_client.on_disconnect = self._on_disconnect
        self._mqtt_client.on_message = self._on_message

    def _on_connect(self, client: Any, userdata: Any, flags: Any, rc: Any, *args: Any) -> None:
        """Callback when connection to MQTT broker is established."""
        reason_code = rc if isinstance(rc, int) else getattr(rc, "value", rc)
        if reason_code == 0:
            logging.info("[MQTT] Connected successfully to broker %s:%d", self.config.broker, self.config.port)
            client.subscribe(self.config.topic)
            logging.info("[MQTT] Subscribed to topic: %s", self.config.topic)
        else:
            logging.error("[MQTT] Connection failed with code: %s", rc)

    def _on_disconnect(self, client: Any, userdata: Any, *args: Any) -> None:
        """Callback on disconnect."""
        logging.warning("[MQTT] Disconnected from broker. Auto-reconnect active.")

    def _on_message(self, client: Any, userdata: Any, message: Any) -> None:
        """Handles incoming MQTT telemetry message."""
        topic = message.topic
        payload = message.payload.decode("utf-8", errors="replace")
        logging.debug("[MQTT MESSAGE] Topic: %s | Payload: %s", topic, payload)

        self.process_payload(topic, payload)

    def process_payload(self, topic: str, payload: str | bytes) -> Optional[int]:
        """
        Parses, evaluates, and stores a telemetry message.
        Returns the inserted record ID or None if parsing failed.
        """
        reading = self.parser.parse(payload)
        if not reading:
            return None

        is_alert, alert_reason = self.evaluator.evaluate(reading)

        row_id = self.db.insert_reading(
            topic=topic,
            reading=reading,
            is_alert=is_alert,
            alert_reason=alert_reason,
        )

        status_tag = "ALERT" if is_alert else "OK"
        logging.info(
            "[%s] Stored reading #%d: Temp=%.1f°C, Hum=%.1f%% (Topic: %s)",
            status_tag,
            row_id,
            reading.temperature,
            reading.humidity,
            topic,
        )
        return row_id

    def start(self, blocking: bool = True) -> None:
        """Starts the MQTT loop."""
        if not self._mqtt_client:
            raise RuntimeError("MQTT Client is not initialized.")

        self._running = True
        logging.info("[MONITOR] Connecting to MQTT broker at %s:%d...", self.config.broker, self.config.port)

        try:
            self._mqtt_client.connect(
                self.config.broker,
                self.config.port,
                keepalive=self.config.keepalive,
            )
        except Exception as exc:
            logging.error("[MONITOR] Could not initiate connection to MQTT broker: %s", exc)
            if blocking:
                raise

        if blocking:
            logging.info("[MONITOR] Starting blocking event loop...")
            try:
                self._mqtt_client.loop_forever()
            except KeyboardInterrupt:
                logging.info("[MONITOR] Interrupted by user.")
            finally:
                self.stop()
        else:
            self._mqtt_client.loop_start()

    def stop(self) -> None:
        """Stops the MQTT client and closes the database connection."""
        if self._running:
            self._running = False
            logging.info("[MONITOR] Shutting down monitor service...")
            if self._mqtt_client:
                try:
                    self._mqtt_client.unsubscribe(self.config.topic)
                    self._mqtt_client.disconnect()
                    self._mqtt_client.loop_stop()
                except Exception as exc:
                    logging.debug("Error during MQTT disconnect: %s", exc)
            self.db.close()
            logging.info("[MONITOR] Shutdown complete.")


# =========================================================================
# CLI and Signal Handling
# =========================================================================

def setup_logging(level_name: str) -> None:
    """Configures structured console logging."""
    numeric_level = getattr(logging, level_name.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        force=True,
    )
    logging.getLogger().setLevel(numeric_level)


def parse_arguments() -> argparse.Namespace:
    """Parses command-line arguments."""
    parser = argparse.ArgumentParser(
        description="IoT Environment Monitor - MQTT Subscriber & Alerting Service"
    )
    parser.add_argument("--broker", help="MQTT Broker host (default from env or localhost)")
    parser.add_argument("--port", type=int, help="MQTT Broker port (default 1883)")
    parser.add_argument("--topic", help="MQTT telemetry topic (default home/room1/env)")
    parser.add_argument("--temp-threshold", type=float, help="Temperature alert threshold in Celsius")
    parser.add_argument("--db", help="Path to SQLite database file (default env_data.db)")
    parser.add_argument("--log-level", default=None, help="Logging level (DEBUG, INFO, WARNING, ERROR)")
    return parser.parse_args()


def main() -> None:
    """Main CLI entrypoint."""
    args = parse_arguments()
    config = Config.from_args(args)
    setup_logging(config.log_level)

    logging.info("==========================================")
    logging.info("   IoT Environment Monitor Service        ")
    logging.info("==========================================")
    logging.info("MQTT Broker:     %s:%d", config.broker, config.port)
    logging.info("MQTT Topic:      %s", config.topic)
    logging.info("Temp Threshold:  %.1f °C", config.temp_threshold)
    logging.info("Database Path:   %s", config.db_path)

    monitor = EnvironmentMonitor(config)

    def signal_handler(signum, frame):
        logging.info("Received termination signal (%s). Exiting...", signum)
        monitor.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        monitor.start(blocking=True)
    except Exception as exc:
        logging.critical("Fatal error in monitor service: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
