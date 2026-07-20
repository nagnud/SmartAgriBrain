#include "mqtt_client.h"
#include "config.h"
#include <stdio.h>
#include <stdlib.h>
#include "LightSensor.h"
#include "TempSensor.h"
#include "SoilSensor.h"
#include "JW01_CO2.h"
#include <WiFiClientSecure.h>
#include <ArduinoJson.h>

const char *root_ca =
    "-----BEGIN CERTIFICATE-----\n"
    "MIIDjjCCAnagAwIBAgIQAzrx5qcRqaC7KGSxHQn65TANBgkqhkiG9w0BAQsFADBh\n"
    "MQswCQYDVQQGEwJVUzEVMBMGA1UEChMMRGlnaUNlcnQgSW5jMRkwFwYDVQQLExB3\n"
    "d3cuZGlnaWNlcnQuY29tMSAwHgYDVQQDExdEaWdpQ2VydCBHbG9iYWwgUm9vdCBH\n"
    "MjAeFw0xMzA4MDExMjAwMDBaFw0zODAxMTUxMjAwMDBaMGExCzAJBgNVBAYTAlVT\n"
    "MRUwEwYDVQQKEwxEaWdpQ2VydCBJbmMxGTAXBgNVBAsTEHd3dy5kaWdpY2VydC5j\n"
    "b20xIDAeBgNVBAMTF0RpZ2lDZXJ0IEdsb2JhbCBSb290IEcyMIIBIjANBgkqhkiG\n"
    "9w0BAQEFAAOCAQ8AMIIBCgKCAQEAuzfNNNx7a8myaJCtSnX/RrohCgiN9RlUyfuI\n"
    "2/Ou8jqJkTx65qsGGmvPrC3oXgkkRLpimn7Wo6h+4FR1IAWsULecYxpsMNzaHxmx\n"
    "1x7e/dfgy5SDN67sH0NO3Xss0r0upS/kqbitOtSZpLYl6ZtrAGCSYP9PIUkY92eQ\n"
    "q2EGnI/yuum06ZIya7XzV+hdG82MHauVBJVJ8zUtluNJbd134/tJS7SsVQepj5Wz\n"
    "tCO7TG1F8PapspUwtP1MVYwnSlcUfIKdzXOS0xZKBgyMUNGPHgm+F6HmIcr9g+UQ\n"
    "vIOlCsRnKPZzFBQ9RnbDhxSJITRNrw9FDKZJobq7nMWxM4MphQIDAQABo0IwQDAP\n"
    "BgNVHRMBAf8EBTADAQH/MA4GA1UdDwEB/wQEAwIBhjAdBgNVHQ4EFgQUTiJUIBiV\n"
    "5uNu5g/6+rkS7QYXjzkwDQYJKoZIhvcNAQELBQADggEBAGBnKJRvDkhj6zHd6mcY\n"
    "1Yl9PMWLSn/pvtsrF9+wX3N3KjITOYFnQoQj8kVnNeyIv/iPsGEMNKSuIEyExtv4\n"
    "NeF22d+mQrvHRAiGfzZ0JFrabA0UWTW98kndth/Jsw1HKj2ZL7tcu7XUIOGZX1NG\n"
    "Fdtom/DzMNU+MeKNhJ7jitralj41E6Vf8PlwUHBHQRFXGU7Aj64GxJUTFy8bJZ91\n"
    "8rGOmaFvE7FBcf6IKshPECBV1/MUReXgRPTqh5Uykw7+U0b6LJ3/iyK5S9kJRaTe\n"
    "pLiaWN0bfVKfjllDiIGknibVb63dDcY3fe0Dkhvld1927jyNxF1WW6LZZm6zNTfl\n"
    "MrY=\n"
    "-----END CERTIFICATE-----\n";

WiFiClientSecure espClient;
PubSubClient mqttClient(espClient);

long lastReconnectAttempt = 0;
bool pendingLedBlink = false;
bool pendingLedOn = false;
bool pendingLedOff = false;
bool pendingSmartControl = false;
SmartControlCommand pendingSmartControlCommand = {};
SmartControlHandler smartControlHandler = nullptr;

void reconnect_mqtt_nonblocking();
void callback(char *topic, byte *payload, unsigned int length);
void blink_led_local(int times, int speed);
void execute_pending_actions();
bool parse_smart_control(byte *payload, unsigned int length, SmartControlCommand &command);
int read_demand(JsonDocument &doc, const char *rootKey, const char *nestedKey, int defaultValue);
bool has_demand(JsonDocument &doc, const char *rootKey, const char *nestedKey);
int clamp_percent(int value);
int demand_to_pwm(int percent);

void init_mqtt()
{
  espClient.setCACert(root_ca);
  mqttClient.setBufferSize(1024);

  mqttClient.setServer(MQTT_SERVER, MQTT_PORT);
  mqttClient.setCallback(callback);

  Serial.println("[MQTT] 模块初始化完成 (缓冲区已扩容)");
}

void set_smart_control_handler(SmartControlHandler handler)
{
  smartControlHandler = handler;
}

void mqtt_loop()
{
  if (!mqttClient.connected())
  {
    reconnect_mqtt_nonblocking();
  }
  else
  {
    mqttClient.loop();
  }

  execute_pending_actions();
}

void send_sensor_data(SoilSensor *soilSensor, BH1750 *bh1750, TempSensor *tempSensor, JW01_CO2 *co2Sensor)
{
  if (!mqttClient.connected())
  {
    return;
  }

  //float temp = 22.0 + (random(0, 50) / 10.0);
  // float moisture = 50.0 + (random(0, 500) / 10.0);
  // float light = 300.0 + (random(0, 2000) / 10.0);
  // float co2 = 400.0 + (random(0, 2000) / 10.0);
  // float timestamp = millis();
      float moisture = soilSensor->getHumidityPercent();
      float light = bh1750->readLight();
       float temp = tempSensor->getTemperature();
      float co2 = co2Sensor->getCO2();
      float timestamp = millis();

      char msgBuffer[128];
      snprintf(msgBuffer, sizeof(msgBuffer),
               "{\"fieldId\":\"field_001\", \"moisture\": %.1f, \"light\": %.1f, \"temp\": %.1f, \"co2\": %.1f, \"timestamp\": %ld}",
               moisture, light, temp, co2, (long)timestamp);

      Serial.print("\n[发送] 发布数据到 [");
      Serial.print(TOPIC_SENSOR);
      Serial.print("]: ");
      Serial.println(msgBuffer);

      if (mqttClient.publish(TOPIC_SENSOR, msgBuffer))
      {
        Serial.println("[发送] ✅ 成功");
      }
  else
  {
    Serial.println("[发送] ❌ 失败 (可能包太大或连接不稳定)");
  }
}

void trigger_self_test()
{
  Serial.println("[调试] 正在向自己发送测试指令...");
  bool success = mqttClient.publish(TOPIC_CONTROL, "LED_BLINK");

  if (success)
  {
    digitalWrite(LED_PIN, HIGH);
    delay(50);
    digitalWrite(LED_PIN, LOW);
  }
  else
  {
    Serial.println("[调试] ❌ 自测指令发送失败");
  }
}

void reconnect_mqtt_nonblocking()
{
  long now = millis();

  if (now - lastReconnectAttempt > 5000)
  {
    lastReconnectAttempt = now;

    Serial.print("\n[MQTT] 尝试重连 (ClientID: ");
    Serial.print(CLIENT_ID);
    Serial.println(")...");

    if (mqttClient.connect(CLIENT_ID, MQTT_USER, MQTT_PASS))
    {
      Serial.println("[MQTT] ✅ 连接成功!");

      if (mqttClient.subscribe(TOPIC_CONTROL))
      {
        Serial.print("[MQTT] 已订阅 ");
        Serial.println(TOPIC_CONTROL);
        digitalWrite(LED_PIN, HIGH);
      }
      else
      {
        Serial.println("[MQTT] ❌ 订阅失败");
      }
    }
    else
    {
      Serial.print("[MQTT] ❌ 失败，错误码: ");
      Serial.println(mqttClient.state());
      Serial.println("[MQTT] 将在 5 秒后重试... (程序继续运行其他任务)");
    }
  }
}

void callback(char *topic, byte *payload, unsigned int length)
{
  Serial.println("\n------------------------------------------");
  Serial.print("[接收] 主题: ");
  Serial.println(topic);

  String message = "";
  for (int i = 0; i < length; i++)
  {
    message += (char)payload[i];
  }

  Serial.print("[接收] 内容: ");
  Serial.println(message);

  SmartControlCommand command;
  if (parse_smart_control(payload, length, command))
  {
    pendingSmartControlCommand = command;
    pendingSmartControl = true;
    pendingLedOn = false;
    pendingLedOff = false;
    pendingLedBlink = false;

    Serial.printf("[CONTROL] water=%s%d%% light=%s%d%% pan=%s%ddeg tilt=%s%ddeg\n",
                  command.hasWaterDemand ? "" : "unchanged/", command.waterDemand,
                  command.hasLightDemand ? "" : "unchanged/", command.lightDemand,
                  command.hasPanAngle ? "" : "unchanged/", command.panAngle,
                  command.hasTiltAngle ? "" : "unchanged/", command.tiltAngle);

    if (command.hasLegacyTempDemand)
    {
      Serial.printf("[CONTROL] Ignoring legacy tempDemand=%d; GPIO14 is now reserved for lightDemand.\n",
                    command.legacyTempDemand);
    }
  }
  else if (message == "LED_ON")
  {
    pendingLedOn = true;
    pendingLedOff = false;
    pendingLedBlink = false;
  }
  else if (message == "LED_OFF")
  {
    pendingLedOff = true;
    pendingLedOn = false;
    pendingLedBlink = false;
  }
  else if (message == "LED_BLINK")
  {
    pendingLedBlink = true;
    pendingLedOn = false;
    pendingLedOff = false;
  }
  else
  {
    Serial.println("[接收] 未知指令");
  }

  Serial.println("------------------------------------------\n");
}

void execute_pending_actions()
{
  if (pendingSmartControl)
  {
    if (smartControlHandler != nullptr)
    {
      smartControlHandler(pendingSmartControlCommand);
    }
    else
    {
      Serial.println("[CONTROL] No smart control handler registered");
    }
    pendingSmartControl = false;
  }

  if (pendingLedOn)
  {
    Serial.println("[执行] 开灯");
    digitalWrite(LED_PIN, HIGH);
    pendingLedOn = false;
  }

  if (pendingLedOff)
  {
    Serial.println("[执行] 关灯");
    digitalWrite(LED_PIN, LOW);
    pendingLedOff = false;
  }

  if (pendingLedBlink)
  {
    Serial.println("[执行] 闪烁");
    blink_led_local(BLINK_TIMES, 200);
    pendingLedBlink = false;
  }
}

bool parse_smart_control(byte *payload, unsigned int length, SmartControlCommand &command)
{
  JsonDocument doc;
  DeserializationError error = deserializeJson(doc, payload, length);
  if (error)
  {
    return false;
  }

  const bool hasWaterDemand = has_demand(doc, "waterDemand", "water");
  const bool hasLightDemand = has_demand(doc, "lightDemand", "light");
  const bool hasPanAngle = doc["panAngle"].is<int>();
  const bool hasTiltAngle = doc["tiltAngle"].is<int>();
  const bool hasLegacyTempDemand = doc["tempDemand"].is<int>() ||
                                    doc["heatDemand"].is<int>() ||
                                    doc["demands"]["heat"].is<int>();
  const bool hasControlFields = hasWaterDemand || hasLightDemand || hasPanAngle || hasTiltAngle || hasLegacyTempDemand;

  if (!hasControlFields)
  {
    return false;
  }

  command = {};
  command.hasWaterDemand = hasWaterDemand;
  command.hasLightDemand = hasLightDemand;
  command.hasPanAngle = hasPanAngle;
  command.hasTiltAngle = hasTiltAngle;
  command.hasLegacyTempDemand = hasLegacyTempDemand;

  if (command.hasWaterDemand)
  {
    command.waterDemand = clamp_percent(read_demand(doc, "waterDemand", "water", 0));
    command.waterPwm = demand_to_pwm(command.waterDemand);
  }
  if (command.hasLightDemand)
  {
    command.lightDemand = clamp_percent(read_demand(doc, "lightDemand", "light", 0));
  }
  if (command.hasPanAngle)
  {
    command.panAngle = doc["panAngle"] | 0;
  }
  if (command.hasTiltAngle)
  {
    command.tiltAngle = doc["tiltAngle"] | 0;
  }
  if (command.hasLegacyTempDemand)
  {
    command.legacyTempDemand = read_demand(doc, "tempDemand", "heat", 0);
    if (!doc["tempDemand"].is<int>() && doc["heatDemand"].is<int>())
    {
      command.legacyTempDemand = doc["heatDemand"] | 0;
    }
  }

  return true;
}

int read_demand(JsonDocument &doc, const char *rootKey, const char *nestedKey, int defaultValue)
{
  if (doc[rootKey].is<int>())
  {
    return doc[rootKey] | defaultValue;
  }

  JsonVariant demands = doc["demands"];
  if (!demands.isNull() && demands[nestedKey].is<int>())
  {
    return demands[nestedKey] | defaultValue;
  }

  return defaultValue;
}

bool has_demand(JsonDocument &doc, const char *rootKey, const char *nestedKey)
{
  return doc[rootKey].is<int>() || doc["demands"][nestedKey].is<int>();
}

int clamp_percent(int value)
{
  if (value < 0)
  {
    return 0;
  }
  if (value > 100)
  {
    return 100;
  }
  return value;
}

int demand_to_pwm(int percent)
{
  percent = clamp_percent(percent);
  if (percent >= 100)
  {
    return 255;
  }
  return (percent * 5) / 2;
}

void blink_led_local(int times, int speed)
{
  for (int i = 0; i < times; i++)
  {
    digitalWrite(LED_PIN, HIGH);
    delay(speed);
    digitalWrite(LED_PIN, LOW);
    delay(speed);
  }
}
