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
