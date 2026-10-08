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
