/*
 * SPDX-FileCopyrightText: 2026
 * SPDX-License-Identifier: Apache-2.0
 */

#include "sensair_iot.h"

#include <stdio.h>
#include <string.h>
#include <time.h>

#include "cJSON.h"
#include "driver/gpio.h"
#include "esp_check.h"
#include "esp_crt_bundle.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_netif_sntp.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include "mqtt_client.h"
#include "nvs_flash.h"

#define COMMAND_PAYLOAD_MAX 512
#define COMMAND_ID_MAX 64
#define COMMAND_NAME_MAX 24

typedef enum {
    ACTUATOR_FAN,
    ACTUATOR_PUMP,
    ACTUATOR_LIGHT,
    ACTUATOR_ALARM,
} actuator_id_t;

typedef struct {
    actuator_id_t actuator;
    bool state;
    char command[COMMAND_NAME_MAX];
    char command_id[COMMAND_ID_MAX];
} actuator_command_t;

typedef struct {
    bool fan;
    bool pump;
    bool light;
    bool alarm;
} actuator_state_t;

static const char *TAG = "sensair_iot";
static portMUX_TYPE s_state_lock = portMUX_INITIALIZER_UNLOCKED;
static sensair_sensor_snapshot_t s_snapshot;
static actuator_state_t s_actuators;
static QueueHandle_t s_command_queue;
static esp_mqtt_client_handle_t s_mqtt_client;
static bool s_wifi_connected;
static bool s_mqtt_connected;
static bool s_sntp_started;
static bool s_started;
static char s_lwt_message[128];

static void publish_ack(const actuator_command_t *command, bool success, const char *message);

void sensair_sensor_get_snapshot(sensair_sensor_snapshot_t *snapshot)
{
    if (snapshot == NULL) {
        return;
    }
    portENTER_CRITICAL(&s_state_lock);
    *snapshot = s_snapshot;
    portEXIT_CRITICAL(&s_state_lock);
}

void sensair_sensor_update_environment(float temperature_c,
                                       float humidity_pct,
                                       float pressure_pa,
                                       float gas_resistance_ohm)
{
    portENTER_CRITICAL(&s_state_lock);
    s_snapshot.temperature_c = temperature_c;
    s_snapshot.humidity_pct = humidity_pct;
    s_snapshot.pressure_kpa = pressure_pa / 1000.0f;
    s_snapshot.gas_resistance_ohm = gas_resistance_ohm;
    s_snapshot.environment_valid = true;
    s_snapshot.environment_updated_us = esp_timer_get_time();
    portEXIT_CRITICAL(&s_state_lock);
}

void sensair_sensor_update_imu(float acc_x_g,
                               float acc_y_g,
                               float acc_z_g,
                               float gyro_x_dps,
                               float gyro_y_dps,
                               float gyro_z_dps)
{
    portENTER_CRITICAL(&s_state_lock);
    s_snapshot.acc_x_g = acc_x_g;
    s_snapshot.acc_y_g = acc_y_g;
    s_snapshot.acc_z_g = acc_z_g;
    s_snapshot.gyro_x_dps = gyro_x_dps;
    s_snapshot.gyro_y_dps = gyro_y_dps;
    s_snapshot.gyro_z_dps = gyro_z_dps;
    s_snapshot.imu_valid = true;
    s_snapshot.imu_updated_us = esp_timer_get_time();
    portEXIT_CRITICAL(&s_state_lock);
}

void sensair_sensor_update_magnetometer(float mag_x_ut,
                                        float mag_y_ut,
                                        float mag_z_ut)
{
    portENTER_CRITICAL(&s_state_lock);
    s_snapshot.mag_x_ut = mag_x_ut;
    s_snapshot.mag_y_ut = mag_y_ut;
    s_snapshot.mag_z_ut = mag_z_ut;
    s_snapshot.magnetometer_valid = true;
    s_snapshot.magnetometer_updated_us = esp_timer_get_time();
    portEXIT_CRITICAL(&s_state_lock);
}

static int64_t unix_timestamp_seconds(void)
{
    time_t now = 0;
    time(&now);
    /* Do not publish the default 1970 timestamp before SNTP succeeds. */
    return now >= 1704067200 ? (int64_t)now : 0;
}

static cJSON *build_telemetry(void)
{
    sensair_sensor_snapshot_t sensors = {0};
    actuator_state_t actuators = {0};
    sensair_sensor_get_snapshot(&sensors);

    portENTER_CRITICAL(&s_state_lock);
    actuators = s_actuators;
    bool wifi_connected = s_wifi_connected;
    bool mqtt_connected = s_mqtt_connected;
    portEXIT_CRITICAL(&s_state_lock);

    cJSON *root = cJSON_CreateObject();
    cJSON *sensor_object = cJSON_AddObjectToObject(root, "sensors");
    cJSON *status_object = cJSON_AddObjectToObject(root, "status");
    cJSON *valid_object = cJSON_AddObjectToObject(root, "valid");
    if (root == NULL || sensor_object == NULL || status_object == NULL || valid_object == NULL) {
        cJSON_Delete(root);
        return NULL;
    }

    cJSON_AddStringToObject(root, "device_id", CONFIG_SENSAIR_DEVICE_ID);
    cJSON_AddNumberToObject(root, "timestamp", (double)unix_timestamp_seconds());

    cJSON_AddNumberToObject(sensor_object, "temperature", sensors.temperature_c);
    cJSON_AddNumberToObject(sensor_object, "humidity", sensors.humidity_pct);
    cJSON_AddNumberToObject(sensor_object, "pressure", sensors.pressure_kpa);
    cJSON_AddNumberToObject(sensor_object, "gas_resistance", sensors.gas_resistance_ohm);
    cJSON_AddNumberToObject(sensor_object, "acc_x", sensors.acc_x_g);
    cJSON_AddNumberToObject(sensor_object, "acc_y", sensors.acc_y_g);
    cJSON_AddNumberToObject(sensor_object, "acc_z", sensors.acc_z_g);
    cJSON_AddNumberToObject(sensor_object, "gyro_x", sensors.gyro_x_dps);
    cJSON_AddNumberToObject(sensor_object, "gyro_y", sensors.gyro_y_dps);
    cJSON_AddNumberToObject(sensor_object, "gyro_z", sensors.gyro_z_dps);
    cJSON_AddNumberToObject(sensor_object, "mag_x", sensors.mag_x_ut);
    cJSON_AddNumberToObject(sensor_object, "mag_y", sensors.mag_y_ut);
    cJSON_AddNumberToObject(sensor_object, "mag_z", sensors.mag_z_ut);

    cJSON_AddStringToObject(status_object, "wifi", wifi_connected ? "connected" : "disconnected");
    cJSON_AddStringToObject(status_object, "mqtt", mqtt_connected ? "connected" : "disconnected");
    cJSON_AddNumberToObject(status_object, "fan", actuators.fan ? 1 : 0);
    cJSON_AddNumberToObject(status_object, "pump", actuators.pump ? 1 : 0);
    cJSON_AddNumberToObject(status_object, "light", actuators.light ? 1 : 0);
    cJSON_AddNumberToObject(status_object, "alarm", actuators.alarm ? 1 : 0);

    cJSON_AddBoolToObject(valid_object, "environment", sensors.environment_valid);
    cJSON_AddBoolToObject(valid_object, "imu", sensors.imu_valid);
    cJSON_AddBoolToObject(valid_object, "magnetometer", sensors.magnetometer_valid);
    return root;
}

static void telemetry_task(void *arg)
{
    (void)arg;
    while (true) {
        cJSON *root = build_telemetry();
        char *json = root != NULL ? cJSON_PrintUnformatted(root) : NULL;
        if (json != NULL) {
            ESP_LOGI(TAG, "telemetry: %s", json);
            if (s_mqtt_client != NULL && s_mqtt_connected) {
                int message_id = esp_mqtt_client_publish(
                    s_mqtt_client, CONFIG_SENSAIR_TOPIC_TELEMETRY, json, 0, 1, 0);
                if (message_id < 0) {
                    ESP_LOGW(TAG, "Failed to enqueue telemetry");
                }
            }
            cJSON_free(json);
        } else {
            ESP_LOGE(TAG, "Unable to allocate telemetry JSON");
        }
        cJSON_Delete(root);
        vTaskDelay(pdMS_TO_TICKS(CONFIG_SENSAIR_UPLOAD_INTERVAL_MS));
    }
}

static int actuator_gpio(actuator_id_t actuator)
{
    switch (actuator) {
    case ACTUATOR_FAN:
        return CONFIG_SENSAIR_FAN_GPIO;
    case ACTUATOR_PUMP:
        return CONFIG_SENSAIR_PUMP_GPIO;
    case ACTUATOR_LIGHT:
        return CONFIG_SENSAIR_LIGHT_GPIO;
    case ACTUATOR_ALARM:
        return CONFIG_SENSAIR_ALARM_GPIO;
    default:
        return -1;
    }
}

static const char *actuator_name(actuator_id_t actuator)
{
    switch (actuator) {
    case ACTUATOR_FAN:
        return "fan";
    case ACTUATOR_PUMP:
        return "pump";
    case ACTUATOR_LIGHT:
        return "light";
    case ACTUATOR_ALARM:
        return "alarm";
    default:
        return "unknown";
    }
}

static void set_actuator_state(actuator_id_t actuator, bool state)
{
    int gpio = actuator_gpio(actuator);
    if (gpio >= 0) {
        gpio_set_level((gpio_num_t)gpio, state ? 1 : 0);
    }

    portENTER_CRITICAL(&s_state_lock);
    switch (actuator) {
    case ACTUATOR_FAN:
        s_actuators.fan = state;
        break;
    case ACTUATOR_PUMP:
        s_actuators.pump = state;
        break;
    case ACTUATOR_LIGHT:
        s_actuators.light = state;
        break;
    case ACTUATOR_ALARM:
        s_actuators.alarm = state;
        break;
    }
    portEXIT_CRITICAL(&s_state_lock);
}

static void actuator_task(void *arg)
{
    (void)arg;
    actuator_command_t command;
    while (true) {
        if (xQueueReceive(s_command_queue, &command, portMAX_DELAY) == pdTRUE) {
            set_actuator_state(command.actuator, command.state);
            ESP_LOGI(TAG, "%s set to %d%s", actuator_name(command.actuator), command.state,
                     actuator_gpio(command.actuator) < 0 ? " (virtual)" : "");
            publish_ack(&command, true, "executed");
        }
    }
}

static void init_actuator_gpio(int gpio)
{
    if (gpio < 0) {
        return;
    }
    gpio_config_t config = {
        .pin_bit_mask = 1ULL << gpio,
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    ESP_ERROR_CHECK(gpio_config(&config));
    gpio_set_level((gpio_num_t)gpio, 0);
}

static bool decode_command_name(const char *name, int value, actuator_id_t *actuator, bool *state)
{
    struct command_mapping {
        const char *name;
        actuator_id_t actuator;
        bool state;
    } mappings[] = {
        {"fan_on", ACTUATOR_FAN, true},       {"fan_off", ACTUATOR_FAN, false},
        {"pump_on", ACTUATOR_PUMP, true},     {"pump_off", ACTUATOR_PUMP, false},
        {"light_on", ACTUATOR_LIGHT, true},   {"light_off", ACTUATOR_LIGHT, false},
        {"alarm_on", ACTUATOR_ALARM, true},   {"alarm_off", ACTUATOR_ALARM, false},
    };
    for (size_t i = 0; i < sizeof(mappings) / sizeof(mappings[0]); ++i) {
        if (strcmp(name, mappings[i].name) == 0) {
            *actuator = mappings[i].actuator;
            *state = mappings[i].state;
            return true;
        }
    }

    if (strcmp(name, "fan") == 0) {
        *actuator = ACTUATOR_FAN;
    } else if (strcmp(name, "pump") == 0) {
        *actuator = ACTUATOR_PUMP;
    } else if (strcmp(name, "light") == 0) {
        *actuator = ACTUATOR_LIGHT;
    } else if (strcmp(name, "alarm") == 0) {
        *actuator = ACTUATOR_ALARM;
    } else {
        return false;
    }
    *state = value != 0;
    return true;
}

static void publish_parse_error(const char *command_id, const char *command_name, const char *message)
{
    actuator_command_t command = {0};
    strlcpy(command.command_id, command_id != NULL ? command_id : "", sizeof(command.command_id));
    strlcpy(command.command, command_name != NULL ? command_name : "", sizeof(command.command));
    publish_ack(&command, false, message);
}

static void handle_command_payload(const char *payload, size_t payload_length)
{
    cJSON *root = cJSON_ParseWithLength(payload, payload_length);
    if (root == NULL) {
        publish_parse_error("", "", "invalid_json");
        return;
    }

    cJSON *device_id_json = cJSON_GetObjectItemCaseSensitive(root, "device_id");
    cJSON *command_id_json = cJSON_GetObjectItemCaseSensitive(root, "command_id");
    cJSON *command_json = cJSON_GetObjectItemCaseSensitive(root, "command");
    cJSON *value_json = cJSON_GetObjectItemCaseSensitive(root, "value");
    const char *device_id = cJSON_IsString(device_id_json) ? device_id_json->valuestring : "";
    const char *command_id = cJSON_IsString(command_id_json) ? command_id_json->valuestring : "";
    const char *command_name = cJSON_IsString(command_json) ? command_json->valuestring : "";
    int value = cJSON_IsNumber(value_json) ? value_json->valueint : 0;

    if (device_id[0] != '\0' && strcmp(device_id, CONFIG_SENSAIR_DEVICE_ID) != 0 && strcmp(device_id, "*") != 0) {
        cJSON_Delete(root);
        return;
    }

    actuator_command_t command = {0};
    if (!decode_command_name(command_name, value, &command.actuator, &command.state)) {
        publish_parse_error(command_id, command_name, "unsupported_command");
        cJSON_Delete(root);
        return;
    }

    strlcpy(command.command, command_name, sizeof(command.command));
    strlcpy(command.command_id, command_id, sizeof(command.command_id));
    if (xQueueSend(s_command_queue, &command, 0) != pdTRUE) {
        publish_ack(&command, false, "command_queue_full");
    }
    cJSON_Delete(root);
}

static void publish_ack(const actuator_command_t *command, bool success, const char *message)
{
    if (s_mqtt_client == NULL || !s_mqtt_connected) {
        return;
    }
    cJSON *root = cJSON_CreateObject();
    if (root == NULL) {
        return;
    }
    cJSON_AddStringToObject(root, "device_id", CONFIG_SENSAIR_DEVICE_ID);
    cJSON_AddStringToObject(root, "command_id", command->command_id);
    cJSON_AddStringToObject(root, "command", command->command);
    cJSON_AddBoolToObject(root, "success", success);
    cJSON_AddNumberToObject(root, "value", command->state ? 1 : 0);
    cJSON_AddStringToObject(root, "message", message);
    cJSON_AddNumberToObject(root, "timestamp", (double)unix_timestamp_seconds());

    char *json = cJSON_PrintUnformatted(root);
    if (json != NULL) {
        esp_mqtt_client_publish(s_mqtt_client, CONFIG_SENSAIR_TOPIC_ACK, json, 0, 1, 0);
        cJSON_free(json);
    }
    cJSON_Delete(root);
}

static bool topic_equals(const esp_mqtt_event_handle_t event, const char *expected)
{
    size_t expected_length = strlen(expected);
    return event->topic_len == (int)expected_length &&
           memcmp(event->topic, expected, expected_length) == 0;
}

static void mqtt_event_handler(void *handler_args, esp_event_base_t base, int32_t event_id, void *event_data)
{
    (void)handler_args;
    (void)base;
    esp_mqtt_event_handle_t event = event_data;

    switch ((esp_mqtt_event_id_t)event_id) {
    case MQTT_EVENT_CONNECTED: {
        portENTER_CRITICAL(&s_state_lock);
        s_mqtt_connected = true;
        portEXIT_CRITICAL(&s_state_lock);
        esp_mqtt_client_subscribe(event->client, CONFIG_SENSAIR_TOPIC_COMMAND, 1);
        char online[128];
        snprintf(online, sizeof(online), "{\"device_id\":\"%s\",\"online\":true}", CONFIG_SENSAIR_DEVICE_ID);
        esp_mqtt_client_publish(event->client, CONFIG_SENSAIR_TOPIC_STATUS, online, 0, 1, 1);
        ESP_LOGI(TAG, "MQTT connected; subscribed to %s", CONFIG_SENSAIR_TOPIC_COMMAND);
        break;
    }
    case MQTT_EVENT_DISCONNECTED:
        portENTER_CRITICAL(&s_state_lock);
        s_mqtt_connected = false;
        portEXIT_CRITICAL(&s_state_lock);
        ESP_LOGW(TAG, "MQTT disconnected");
        break;
    case MQTT_EVENT_DATA:
        if (topic_equals(event, CONFIG_SENSAIR_TOPIC_COMMAND)) {
            if (event->current_data_offset == 0 && event->data_len == event->total_data_len &&
                    event->data_len > 0 && event->data_len <= COMMAND_PAYLOAD_MAX) {
                handle_command_payload(event->data, (size_t)event->data_len);
            } else {
                ESP_LOGW(TAG, "Rejected fragmented or oversized command (%d bytes)", event->total_data_len);
            }
        }
        break;
    case MQTT_EVENT_ERROR:
        ESP_LOGE(TAG, "MQTT transport error");
        break;
    default:
        break;
    }
}

static esp_err_t start_mqtt(void)
{
    if (s_mqtt_client != NULL || CONFIG_SENSAIR_MQTT_URI[0] == '\0') {
        return ESP_OK;
    }

    if (strstr(CONFIG_SENSAIR_MQTT_URI, "://") == NULL) {
        ESP_LOGE(TAG, "Invalid MQTT URI. Use mqtt://host:port or mqtts://host:port");
        return ESP_ERR_INVALID_ARG;
    }

    snprintf(s_lwt_message, sizeof(s_lwt_message),
             "{\"device_id\":\"%s\",\"online\":false}", CONFIG_SENSAIR_DEVICE_ID);

    const esp_mqtt_client_config_t mqtt_config = {
        .broker = {
            .address.uri = CONFIG_SENSAIR_MQTT_URI,
            .verification.crt_bundle_attach = esp_crt_bundle_attach,
        },
        .credentials = {
            .username = CONFIG_SENSAIR_MQTT_USERNAME,
            .authentication.password = CONFIG_SENSAIR_MQTT_PASSWORD,
        },
        .session = {
            .last_will = {
                .topic = CONFIG_SENSAIR_TOPIC_STATUS,
                .msg = s_lwt_message,
                .qos = 1,
                .retain = 1,
            },
            .keepalive = 60,
        },
        .network.reconnect_timeout_ms = 5000,
        .task.stack_size = 6144,
        .buffer.size = 2048,
    };

    s_mqtt_client = esp_mqtt_client_init(&mqtt_config);
    if (s_mqtt_client == NULL) {
        ESP_LOGE(TAG, "MQTT client init failed; check broker URI and configuration");
        return ESP_FAIL;
    }
    ESP_RETURN_ON_ERROR(
        esp_mqtt_client_register_event(s_mqtt_client, ESP_EVENT_ANY_ID, mqtt_event_handler, NULL),
        TAG, "Register MQTT event handler failed");
    return esp_mqtt_client_start(s_mqtt_client);
}

static void start_sntp(void)
{
    if (s_sntp_started) {
        return;
    }
    esp_sntp_config_t config = ESP_NETIF_SNTP_DEFAULT_CONFIG(CONFIG_SENSAIR_SNTP_SERVER);
    esp_err_t error = esp_netif_sntp_init(&config);
    if (error == ESP_OK) {
        s_sntp_started = true;
        ESP_LOGI(TAG, "SNTP started with %s", CONFIG_SENSAIR_SNTP_SERVER);
    } else {
        ESP_LOGW(TAG, "SNTP start failed: %s", esp_err_to_name(error));
    }
}

static void network_event_handler(void *arg, esp_event_base_t event_base, int32_t event_id, void *event_data)
{
    (void)arg;
    (void)event_data;
    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_START) {
        esp_wifi_connect();
    } else if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_DISCONNECTED) {
        portENTER_CRITICAL(&s_state_lock);
        s_wifi_connected = false;
        portEXIT_CRITICAL(&s_state_lock);
        esp_wifi_connect();
    } else if (event_base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
        portENTER_CRITICAL(&s_state_lock);
        s_wifi_connected = true;
        portEXIT_CRITICAL(&s_state_lock);
        ESP_LOGI(TAG, "Wi-Fi connected");
        start_sntp();
        esp_err_t error = start_mqtt();
        if (error != ESP_OK) {
            ESP_LOGE(TAG, "MQTT start failed: %s", esp_err_to_name(error));
        }
    }
}

static esp_err_t start_wifi(void)
{
    if (CONFIG_SENSAIR_WIFI_SSID[0] == '\0') {
        ESP_LOGW(TAG, "Wi-Fi SSID is empty; serial telemetry remains enabled");
        return ESP_OK;
    }

    ESP_RETURN_ON_ERROR(esp_netif_init(), TAG, "esp_netif_init failed");
    esp_err_t error = esp_event_loop_create_default();
    if (error != ESP_OK && error != ESP_ERR_INVALID_STATE) {
        return error;
    }
    esp_netif_create_default_wifi_sta();

    wifi_init_config_t init_config = WIFI_INIT_CONFIG_DEFAULT();
    ESP_RETURN_ON_ERROR(esp_wifi_init(&init_config), TAG, "esp_wifi_init failed");
    ESP_RETURN_ON_ERROR(
        esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, network_event_handler, NULL),
        TAG, "Register Wi-Fi event handler failed");
    ESP_RETURN_ON_ERROR(
        esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, network_event_handler, NULL),
        TAG, "Register IP event handler failed");

    wifi_config_t wifi_config = {0};
    strlcpy((char *)wifi_config.sta.ssid, CONFIG_SENSAIR_WIFI_SSID, sizeof(wifi_config.sta.ssid));
    strlcpy((char *)wifi_config.sta.password, CONFIG_SENSAIR_WIFI_PASSWORD, sizeof(wifi_config.sta.password));
    wifi_config.sta.threshold.authmode = WIFI_AUTH_WPA2_PSK;
    wifi_config.sta.sae_pwe_h2e = WPA3_SAE_PWE_BOTH;

    ESP_RETURN_ON_ERROR(esp_wifi_set_mode(WIFI_MODE_STA), TAG, "Set station mode failed");
    ESP_RETURN_ON_ERROR(esp_wifi_set_config(WIFI_IF_STA, &wifi_config), TAG, "Set Wi-Fi config failed");
    return esp_wifi_start();
}

esp_err_t sensair_iot_start(void)
{
#if !CONFIG_SENSAIR_IOT_ENABLE
    ESP_LOGI(TAG, "Sensair IoT is disabled");
    return ESP_OK;
#else
    if (s_started) {
        return ESP_OK;
    }

    esp_err_t error = nvs_flash_init();
    if (error == ESP_ERR_NVS_NO_FREE_PAGES || error == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_RETURN_ON_ERROR(nvs_flash_erase(), TAG, "NVS erase failed");
        error = nvs_flash_init();
    }
    ESP_RETURN_ON_ERROR(error, TAG, "NVS init failed");

    s_command_queue = xQueueCreate(8, sizeof(actuator_command_t));
    if (s_command_queue == NULL) {
        return ESP_ERR_NO_MEM;
    }

    init_actuator_gpio(CONFIG_SENSAIR_FAN_GPIO);
    init_actuator_gpio(CONFIG_SENSAIR_PUMP_GPIO);
    init_actuator_gpio(CONFIG_SENSAIR_LIGHT_GPIO);
    init_actuator_gpio(CONFIG_SENSAIR_ALARM_GPIO);

    if (xTaskCreate(actuator_task, "sensair_actuator", 4096, NULL, 5, NULL) != pdPASS ||
            xTaskCreate(telemetry_task, "sensair_telemetry", 6144, NULL, 4, NULL) != pdPASS) {
        return ESP_ERR_NO_MEM;
    }

    s_started = true;
    ESP_LOGI(TAG, "Sensair IoT started for %s", CONFIG_SENSAIR_DEVICE_ID);
    return start_wifi();
#endif
}
