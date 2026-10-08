# 🌡️ IoT Environment Monitor

[![CI Pipeline](https://github.com/example/iot-env-monitor/actions/workflows/ci.yml/badge.svg)](.github/workflows/ci.yml)
[![Python Version](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/)
[![PlatformIO](https://img.shields.io/badge/PlatformIO-ESP32-orange.svg)](https://platformio.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

An end-to-end, production-ready IoT environmental telemetry and threshold alerting system. This project features an **ESP32 firmware node** with DHT22 temperature and humidity sensing, an **Eclipse Mosquitto MQTT broker**, and an asynchronous **Python backend service** storing telemetry into **SQLite** with instant threshold breach alerting, fully containerized with **Docker Compose** and automated via **GitHub Actions CI**.

---

## 📑 Table of Contents

- [System Architecture](#-system-architecture)
- [Project Structure](#-project-structure)
- [Hardware & Simulation Parts List](#-hardware--simulation-parts-list)
  - [Physical Hardware Wiring](#physical-hardware-wiring)
  - [Wokwi Browser Simulation](#wokwi-browser-simulation)
- [Configuration & Environment Variables](#-configuration--environment-variables)
- [Quick Start: Docker & Docker Compose](#-quick-start-docker--docker-compose)
- [Running Python Backend Locally](#-running-python-backend-locally)
- [Unit Testing & Code Coverage](#-unit-testing--code-coverage)
- [ESP32 Firmware Flashing & Build](#-esp32-firmware-flashing--build)
- [Manual Telemetry & Verification](#-manual-telemetry--verification)
- [CI/CD Workflow](#-cicd-workflow)
- [License](#-license)

---

## 🏛 System Architecture

The following block diagram illustrates the data flow from physical/simulated sensing to database persistence and threshold alerting:

```mermaid
graph TD
    subgraph "Edge Device (ESP32 Node)"
        DHT[DHT22 Sensor / AM2302] -->|GPIO 4 (DATA)| MCU[ESP32 Microcontroller]
        MCU -->|Fallback Logic| SIM[Simulated Fallback Generator]
        MCU -->|JSON Serializer| JSON['{"temp": 27.4, "hum": 61}']
        JSON -->|Wi-Fi / TCP| PUB[PubSubClient MQTT Publisher]
    end

    PUB -->|Topic: home/room1/env| BROKER[Eclipse Mosquitto Broker\nPort 1883]

    subgraph "Backend Monitoring Service (Docker / Python)"
        BROKER -->|MQTT Subscribe| SUB[Paho-MQTT v2 Subscriber]
        SUB --> PARSE[Payload Parser & Validator]
        PARSE -->|TelemetryReading| EVAL[Threshold Alert Evaluator]
        EVAL -->|Check: temp > TEMP_THRESHOLD| ALERT{Threshold Breached?}
        ALERT -->|Yes| LOG_ALERT[Log Warning / Alert Event]
        ALERT -->|No| LOG_OK[Log Normal Telemetry]
        LOG_ALERT --> DBM[Database Manager]
        LOG_OK --> DBM
        DBM -->|Thread-safe Insert| SQLITE[(SQLite: env_data.db\nTable: env_readings)]
    end
```

---

## 📁 Project Structure

```text
iot-env-monitor/
├── .github/
│   └── workflows/
│       └── ci.yml               # GitHub Actions CI (pytest + PlatformIO build check)
├── firmware/
│   ├── include/
│   │   └── config.h             # Wi-Fi credentials, MQTT host, pin assignments
│   ├── src/
│   │   └── main.cpp             # ESP32 main program (Wi-Fi, MQTT, DHT22 sensing)
│   ├── diagram.json             # Wokwi simulation circuit configuration
│   ├── wokwi.toml               # Wokwi VS Code integration settings
│   └── platformio.ini           # PlatformIO configuration (ESP32 DevKit, libraries)
├── mosquitto/
│   └── config/
│       └── mosquitto.conf       # Eclipse Mosquitto broker configuration
├── service/
│   ├── __init__.py              # Package init exporting core classes
│   ├── monitor.py               # Python MQTT subscriber, SQLite logger & alerting
│   ├── test_monitor.py          # Pytest unit tests (parsing, DB, thresholds)
│   └── requirements.txt         # Python dependencies
├── .dockerignore                # Docker build ignore patterns
├── .env.example                 # Environment variables template
├── .gitignore                   # Git ignore patterns (virtual environments, DBs, build artifacts)
├── Dockerfile                   # Python monitoring service Docker container definition
├── docker-compose.yml           # Multi-container orchestration (Mosquitto + Python Service)
├── LICENSE                      # MIT Open Source License
└── README.md                    # Project documentation
```

---

## 🔌 Hardware & Simulation Parts List

### Physical Parts List

| Component | Quantity | Specification / Description |
| :--- | :---: | :--- |
| **ESP32 NodeMCU / DevKit V1** | 1 | Dual-core Tensilica Xtensa 32-bit LX6, 2.4 GHz Wi-Fi + BLE |
| **DHT22 (AM2302) Sensor** | 1 | Digital temp & humidity sensor (-40 to 80 °C, 0-100% RH) |
| **Pull-up Resistor** | 1 | 10 kΩ resistor (between 3.3V and DATA pin, not needed if using module board) |
| **Breadboard & Jumpers** | 1 set | Standard solderless breadboard + male-to-male DuPont wires |
| **Micro-USB Cable** | 1 | 5V power supply and serial flashing interface |

### Physical Hardware Wiring

```text
  +-------------------+              +----------------+
  |  ESP32 DevKit V1  |              |  DHT22 Sensor  |
  |                   |              |                |
  |              3V3  |------------->|  Pin 1 (VCC)   |
  |                   |              |                |
  |           GPIO 4  |<------------>|  Pin 2 (DATA)  |
  |                   |   |          |                |
  |                   |  [10kΩ]      |  Pin 3 (NC)    |
  |                   |   |          |                |
  |              GND  |---|--------->|  Pin 4 (GND)   |
  +-------------------+              +----------------+
```

### Wokwi Browser Simulation

Don't have physical hardware on hand? You can test and simulate this project directly in your browser or through the Wokwi VS Code extension:

1. The project includes [diagram.json](firmware/diagram.json) and [wokwi.toml](firmware/wokwi.toml) ready to run.
2. Open [Wokwi.com](https://wokwi.com) or the Wokwi VS Code extension.
3. The DHT22 slider in the Wokwi UI allows you to alter temperature and humidity on the fly to test threshold breach alerts!
4. By default, `firmware/include/config.h` includes an intelligent **simulation fallback generator** that outputs realistic environmental telemetry even if a physical DHT sensor is disconnected or returns `NaN`.

---

## ⚙️ Configuration & Environment Variables

Copy the template environment file to create your active configuration:

```bash
cp .env.example .env
```

### Key Environment Variables

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `MQTT_BROKER` | `localhost` (or `mqtt-broker` in Docker) | MQTT Broker host or IP address |
| `MQTT_PORT` | `1883` | MQTT Broker TCP port |
| `MQTT_TOPIC` | `home/room1/env` | Telemetry topic for environmental readings |
| `MQTT_CLIENT_ID`| `python-env-monitor-subscriber` | MQTT client identification string |
| `TEMP_THRESHOLD`| `30.0` | Temperature alert threshold in °C (alerts if exceeded) |
| `HUM_THRESHOLD` | `85.0` | Humidity alert threshold in % RH |
| `DB_PATH` | `env_data.db` (`/data/env_data.db` in Docker) | Path to SQLite database file |
| `LOG_LEVEL` | `INFO` | Console logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

---

## 🚀 Quick Start: Docker & Docker Compose

Launch the complete stack (Eclipse Mosquitto broker + Python monitor service) with a single command:

```bash
# 1. Build and run containers in detached mode
docker compose up -d --build

# 2. Inspect real-time service logs
docker compose logs -f env-monitor

# 3. Stop containers and preserve database volumes
docker compose down
```

The SQLite database is persisted inside a Docker named volume (`monitor_data`), mounted at `/data/env_data.db`.

---

## 🐍 Running Python Backend Locally

### 1. Prerequisites
- Python 3.12+
- A running MQTT broker (e.g., local Mosquitto or Docker broker on port 1883)

### 2. Setup Virtual Environment
```bash
# Navigate to project folder
cd iot-env-monitor

# Create and activate virtual environment
python -m venv venv
# On Linux/macOS:
source venv/bin/activate
# On Windows:
.\venv\Scripts\activate

# Install dependencies
pip install -r service/requirements.txt
```

### 3. Start the Monitoring Service
```bash
python -m service.monitor
```

Command-line overrides are also supported:
```bash
python -m service.monitor --broker localhost --port 1883 --topic home/room1/env --temp-threshold 28.5 --db env_data.db
```

---

