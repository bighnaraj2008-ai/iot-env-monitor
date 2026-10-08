"""
IoT Environment Monitor - Backend Service
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

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
        return cls(
            broker=args.broker or os.getenv("MQTT_BROKER", "localhost"),
            port=int(args.port or os.getenv("MQTT_PORT", "1883")),
            topic=args.topic or os.getenv("MQTT_TOPIC", "home/room1/env"),
            temp_threshold=float(args.temp_threshold if args.temp_threshold is not None else os.getenv("TEMP_THRESHOLD", "30.0")),
            db_path=args.db or os.getenv("DB_PATH", "env_data.db"),
            log_level=(args.log_level or os.getenv("LOG_LEVEL", "INFO")).upper(),
        )

import sqlite3
import threading
import logging

class DatabaseManager:
    """Manages SQLite storage for environmental telemetry readings."""

    def __init__(self, db_path: str = "env_data.db"):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._connection: Optional[sqlite3.Connection] = None
        self._init_database()

    def _get_connection(self) -> sqlite3.Connection:
        if self._connection is None:
            self._connection = sqlite3.connect(self.db_path, check_same_thread=False)
            self._connection.row_factory = sqlite3.Row
        return self._connection

    def _init_database(self) -> None:
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
