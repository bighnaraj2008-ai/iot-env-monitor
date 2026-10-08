#ifndef CONFIG_H
#define CONFIG_H

#ifndef WIFI_SSID
#define WIFI_SSID "Wokwi-GUEST"
#endif

#ifndef WIFI_PASSWORD
#define WIFI_PASSWORD ""
#endif

#define WIFI_CONNECT_TIMEOUT_MS 15000

#ifndef MQTT_BROKER
#define MQTT_BROKER "192.168.1.100"
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

#ifndef MQTT_USER
#define MQTT_USER ""
#endif

#ifndef MQTT_PASSWORD
#define MQTT_PASSWORD ""
#endif

#define MQTT_RECONNECT_INTERVAL_MS 5000

#endif // CONFIG_H
