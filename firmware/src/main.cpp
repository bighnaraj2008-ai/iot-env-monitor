#include <Arduino.h>
#include <WiFi.h>
#include "config.h"

unsigned long lastWifiRetryTime = 0;

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

void setup() {
    Serial.begin(115200);
    setupWiFi();
}

void loop() {
    ensureWiFiConnection();
    delay(10);
}
