#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <DHT.h>
#include <ArduinoJson.h>
#include "config.h"

WiFiClient espClient;
PubSubClient mqttClient(espClient);
DHT dht(DHT_PIN, DHT_TYPE);

unsigned long lastWifiRetryTime = 0;
unsigned long lastMqttRetryTime = 0;

void setupWiFi() {
    delay(10);
    Serial.println("\n[WiFi] Initializing Wi-Fi connection...");
    Serial.printf("[WiFi] Connecting to SSID: %s\n", WIFI_SSID);

    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    unsigned long startAttemptTime = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - startAttemptTime < WIFI_CONNECT_TIMEOUT_MS) {
        delay(500);
        Serial.print(".");
    }

    if (WiFi.status() == WL_CONNECTED) {
        Serial.println("\n[WiFi] Connected successfully!");
        Serial.print("[WiFi] IP Address: ");
        Serial.println(WiFi.localIP());
    } else {
        Serial.println("\n[WiFi] Initial connection timeout. Background reconnect will handle.");
    }
}

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

bool ensureMqttConnection() {
    if (mqttClient.connected()) {
        return true;
    }
    if (WiFi.status() != WL_CONNECTED) {
        return false;
    }
    unsigned long currentMillis = millis();
    if (currentMillis - lastMqttRetryTime < MQTT_RECONNECT_INTERVAL_MS) {
        return false;
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
    } else {
        Serial.printf("FAILED (rc=%d). Retrying in %lu ms\n", mqttClient.state(), (unsigned long)MQTT_RECONNECT_INTERVAL_MS);
    }
    return mqttClient.connected();
}

bool readEnvironmentalData(float &temperature, float &humidity) {
    float readT = dht.readTemperature();
    float readH = dht.readHumidity();

    if (isnan(readT) || isnan(readH)) {
        Serial.println("[SENSOR ERROR] Failed to read from DHT sensor!");
        return false;
    }
    temperature = round(readT * 10.0) / 10.0;
    humidity = round(readH * 10.0) / 10.0;
    return true;
}

void publishTelemetry(float temperature, float humidity) {
    JsonDocument doc;
    doc["temp"] = temperature;
    doc["hum"] = humidity;

    char jsonBuffer[128];
    serializeJson(doc, jsonBuffer, sizeof(jsonBuffer));

    Serial.printf("[MQTT PUBLISH] Topic: %s | Payload: %s\n", MQTT_TOPIC, jsonBuffer);
    mqttClient.publish(MQTT_TOPIC, jsonBuffer, false);
}

void setup() {
    Serial.begin(115200);
    dht.begin();
    setupWiFi();
    mqttClient.setServer(MQTT_BROKER, MQTT_PORT);
}

void loop() {
    ensureWiFiConnection();
    if (WiFi.status() == WL_CONNECTED) {
        if (!mqttClient.connected()) {
            ensureMqttConnection();
        }
        mqttClient.loop();
    }
    delay(10);
}
