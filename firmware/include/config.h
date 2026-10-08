#ifndef CONFIG_H
#define CONFIG_H

// =========================================================================
// Wi-Fi Configuration
// =========================================================================
#ifndef WIFI_SSID
#define WIFI_SSID "Wokwi-GUEST"          // Default to Wokwi simulation network
#endif

#ifndef WIFI_PASSWORD
#define WIFI_PASSWORD ""                 // Password for Wi-Fi network
#endif

// Wi-Fi Connection retry timeout in milliseconds
#define WIFI_CONNECT_TIMEOUT_MS 15000

// =========================================================================
// MQTT Broker Configuration
// =========================================================================
#ifndef MQTT_BROKER
#define MQTT_BROKER "192.168.1.100"      // IP address or hostname of MQTT broker (or "test.mosquitto.org" / "broker.emqx.io")
#endif

#ifndef MQTT_PORT
#define MQTT_PORT 1883
#endif

#ifndef MQTT_CLIENT_ID
#define MQTT_CLIENT_ID "esp32-env-node-01"
#endif

#ifndef MQTT_TOPIC
#define MQTT_TOPIC "home/room1/env"
#endif

// Optional MQTT Credentials (leave empty if broker allows anonymous)
#ifndef MQTT_USER
#define MQTT_USER ""
#endif

#ifndef MQTT_PASSWORD
#define MQTT_PASSWORD ""
#endif

// MQTT Reconnection interval in milliseconds
#define MQTT_RECONNECT_INTERVAL_MS 5000

// =========================================================================
// Sensor & Telemetry Configuration
// =========================================================================
#define DHT_PIN 4                       // GPIO pin connected to DHT22 DATA
#define DHT_TYPE DHT22                  // Sensor model: DHT22 (AM2302)

// Telemetry publication interval (5 seconds = 5000 ms)
#define PUBLISH_INTERVAL_MS 5000

// Enable simulation fallback if physical DHT sensor is not detected (NaN readings)
#define ENABLE_SIMULATION_FALLBACK true

#endif // CONFIG_H
