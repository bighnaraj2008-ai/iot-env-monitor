/**
 * @file main.cpp
 * @brief ESP32 IoT Environment Monitor Firmware
 * 
 * Features:
 *  - DHT22 Temperature & Humidity Sensing (with graceful simulation fallback)
 *  - Non-blocking Wi-Fi auto-reconnect logic
 *  - Resilient MQTT client with automatic reconnection
 *  - JSON payload formatting via ArduinoJson
 *  - Periodic telemetry publishing every 5 seconds to "home/room1/env"
 */

#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <DHT.h>
#include <ArduinoJson.h>
#include "config.h"

// =========================================================================
// Global Instances & State
// =========================================================================
WiFiClient espClient;
PubSubClient mqttClient(espClient);
DHT dht(DHT_PIN, DHT_TYPE);

// Timing trackers
unsigned long lastPublishTime = 0;
unsigned long lastMqttRetryTime = 0;
unsigned long lastWifiRetryTime = 0;

// Simulation drift state
float simulatedTemp = 27.4;
float simulatedHum = 61.0;

// =========================================================================
// Helper Functions
// =========================================================================

/**
 * @brief Initialize and manage Wi-Fi connection
 */
void setupWiFi() {
    delay(10);
    Serial.println("\n[WiFi] Initializing Wi-Fi connection...");
    Serial.printf("[WiFi] Connecting to SSID: %s\n", WIFI_SSID);

    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    unsigned long startAttemptTime = millis();

    // Try initial synchronous connect for up to WIFI_CONNECT_TIMEOUT_MS
    while (WiFi.status() != WL_CONNECTED && millis() - startAttemptTime < WIFI_CONNECT_TIMEOUT_MS) {
        delay(500);
        Serial.print(".");
    }

    if (WiFi.status() == WL_CONNECTED) {
        Serial.println("\n[WiFi] Connected successfully!");
        Serial.print("[WiFi] IP Address: ");
        Serial.println(WiFi.localIP());
        Serial.print("[WiFi] RSSI: ");
        Serial.printf("%d dBm\n", WiFi.RSSI());
    } else {
        Serial.println("\n[WiFi] Initial connection timeout. Background reconnect will handle.");
    }
}

/**
 * @brief Reconnect to Wi-Fi if connection was lost
 */
void ensureWiFiConnection() {
    if (WiFi.status() != WL_CONNECTED) {
        unsigned long currentMillis = millis();
        if (currentMillis - lastWifiRetryTime >= 5000) {
            lastWifiRetryTime = currentMillis;
            Serial.println("[WiFi] Connection lost. Attempting reconnect...");
            WiFi.disconnect();
            WiFi.reconnect();
        }
    }
}

/**
 * @brief Reconnect to MQTT broker if disconnected
 */
bool ensureMqttConnection() {
    if (mqttClient.connected()) {
        return true;
    }

    // Only attempt MQTT reconnect if Wi-Fi is active
    if (WiFi.status() != WL_CONNECTED) {
        return false;
    }

    unsigned long currentMillis = millis();
    if (currentMillis - lastMqttRetryTime < MQTT_RECONNECT_INTERVAL_MS) {
        return false; // Wait until retry interval has passed
    }

    lastMqttRetryTime = currentMillis;
    Serial.print("[MQTT] Attempting connection to broker: ");
    Serial.printf("%s:%d ... ", MQTT_BROKER, MQTT_PORT);

    bool connected = false;
    if (strlen(MQTT_USER) > 0) {
        connected = mqttClient.connect(MQTT_CLIENT_ID, MQTT_USER, MQTT_PASSWORD);
    } else {
        connected = mqttClient.connect(MQTT_CLIENT_ID);
    }

    if (connected) {
        Serial.println("CONNECTED!");
        Serial.printf("[MQTT] Client ID: %s\n", MQTT_CLIENT_ID);
        Serial.printf("[MQTT] Telemetry Topic: %s\n", MQTT_TOPIC);
    } else {
        Serial.printf("FAILED (rc=%d). Retrying in %lu ms\n", mqttClient.state(), (unsigned long)MQTT_RECONNECT_INTERVAL_MS);
    }

    return mqttClient.connected();
}

/**
 * @brief Read temperature and humidity from DHT22 or fallback to simulation
 */
bool readEnvironmentalData(float &temperature, float &humidity) {
    float readT = dht.readTemperature();
    float readH = dht.readHumidity();

    if (isnan(readT) || isnan(readH)) {
        if (ENABLE_SIMULATION_FALLBACK) {
            // Apply slight realistic Brownian drift (+/- 0.2)
            float tempDelta = ((float)random(-20, 21)) / 100.0;
            float humDelta = ((float)random(-30, 31)) / 100.0;
            
            simulatedTemp = constrain(simulatedTemp + tempDelta, 18.0, 38.0);
            simulatedHum = constrain(simulatedHum + humDelta, 30.0, 90.0);

            temperature = round(simulatedTemp * 10.0) / 10.0;
            humidity = round(simulatedHum * 10.0) / 10.0;

            Serial.printf("[SENSOR WARNING] DHT22 not detected / NaN. Using simulated fallback: Temp=%.1f C, Hum=%.1f %%\n",
                          temperature, humidity);
            return true;
        } else {
            Serial.println("[SENSOR ERROR] Failed to read from DHT sensor!");
            return false;
        }
    }

    temperature = round(readT * 10.0) / 10.0;
    humidity = round(readH * 10.0) / 10.0;
    return true;
}

/**
 * @brief Publish telemetry payload to MQTT broker
 */
void publishTelemetry(float temperature, float humidity) {
    JsonDocument doc;
    doc["temp"] = temperature;
    doc["hum"] = humidity;

    char jsonBuffer[128];
    serializeJson(doc, jsonBuffer, sizeof(jsonBuffer));

    Serial.printf("[MQTT PUBLISH] Topic: %s | Payload: %s\n", MQTT_TOPIC, jsonBuffer);

    if (mqttClient.publish(MQTT_TOPIC, jsonBuffer, false)) {
        Serial.println("[MQTT PUBLISH] Payload sent successfully.");
    } else {
        Serial.println("[MQTT PUBLISH ERROR] Failed to publish message.");
    }
}

// =========================================================================
// Setup and Main Loop
// =========================================================================

void setup() {
    Serial.begin(115200);
    while (!Serial && millis() < 2000); // Allow time for serial terminal attachment

    Serial.println("\n==============================================");
    Serial.println("   ESP32 IoT Environment Monitor Starting    ");
    Serial.println("==============================================");

    // Initialize DHT22 hardware pin
    dht.begin();
    Serial.printf("[SENSOR] DHT22 initialized on GPIO %d\n", DHT_PIN);

    // Initialize Wi-Fi
    setupWiFi();

    // Configure MQTT client
    mqttClient.setServer(MQTT_BROKER, MQTT_PORT);
    mqttClient.setBufferSize(256);
}

void loop() {
    // 1. Maintain Wi-Fi and MQTT connectivity
    ensureWiFiConnection();
    
    if (WiFi.status() == WL_CONNECTED) {
        if (!mqttClient.connected()) {
            ensureMqttConnection();
        }
        // Process incoming/outgoing MQTT background packets
        mqttClient.loop();
    }

    // 2. Periodic environmental telemetry reading and publication
    unsigned long currentMillis = millis();
    if (currentMillis - lastPublishTime >= PUBLISH_INTERVAL_MS) {
        lastPublishTime = currentMillis;

        float temperature = 0.0;
        float humidity = 0.0;

        if (readEnvironmentalData(temperature, humidity)) {
            if (mqttClient.connected()) {
                publishTelemetry(temperature, humidity);
            } else {
                Serial.println("[WARN] Telemetry acquired but MQTT is disconnected. Skipping publish.");
            }
        }
    }

    // Brief yield to avoid starving ESP32 RTOS watchdog
    delay(10);
}
