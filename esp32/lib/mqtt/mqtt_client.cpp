#include "iot_mqtt_client.h"

#include <ArduinoJson.h>
#include <WiFi.h>
#include <math.h>
#include <mqtt_client.h>
#include <time.h>

#include "config.h"
#include "emqx_ca_cert.h"

namespace
{
constexpr size_t MQTT_IO_BUFFER_SIZE = 4096;
constexpr size_t RAW_COMMAND_MAX_BYTES = 3072;
constexpr size_t RAW_COMMAND_QUEUE_DEPTH = 4;
constexpr unsigned long COMMAND_CACHE_TTL_MS = 10UL * 60UL * 1000UL;
constexpr size_t COMMAND_CACHE_SIZE = 50;

/**
 * MQTT 网络任务向 Arduino loop 传递的原始命令。
 * payload 在这里仍是 UTF-8 JSON；网络回调只负责拼接分片，不解析业务字段，
 * 避免在 ESP-IDF MQTT 任务中执行舵机、PWM 或耗时 JSON 状态机逻辑。
 */
struct RawCommandMessage
{
  uint16_t length = 0;
  uint8_t qos = 0;
  bool duplicate = false;
  char payload[RAW_COMMAND_MAX_BYTES + 1] = {};
};

/** 已完成命令的 ACK 缓存。QoS 1 重发同一 command_id 时直接重发原 ACK。 */
struct CommandCacheEntry
{
  bool used = false;
  String commandId;
  uint32_t fingerprint = 0;
  String ackPayload;
  unsigned long storedAt = 0;
};

esp_mqtt_client_handle_t mqttClient = nullptr;
QueueHandle_t rawCommandQueue = nullptr;

char telemetryTopic[128];
char statusTopic[128];
char capabilitiesTopic[128];
char commandTopic[128];
char commandAckTopic[128];
char clientId[80];

volatile bool mqttConnected = false;
volatile bool publishConnectSnapshotRequested = false;
volatile bool safetyStopRequested = false;

IotCommandHandler commandHandler = nullptr;
ActuatorStateProvider actuatorStateProvider = nullptr;
SafetyStopHandler safetyStopHandler = nullptr;
CommandCacheEntry commandCache[COMMAND_CACHE_SIZE];

// 当前只允许一个需要异步状态机完成的命令。普通同步命令不占用该槽位。
bool inFlightCommandUsed = false;
String inFlightCommandId;
uint32_t inFlightFingerprint = 0;

// MQTT_EVENT_DATA 可能把一个大 JSON 拆成多段；以下缓冲只由 MQTT 任务访问。
char assemblingPayload[RAW_COMMAND_MAX_BYTES + 1];
size_t assemblingExpectedLength = 0;
size_t assemblingReceivedLength = 0;
bool assemblingCommandTopic = false;

String mqttWillPayload;

// Default public CA retained for the already configured EMQX endpoint. A
// deployment-specific CA generated into emqx_ca_cert.h overrides it below.
const char *legacyRootCa =
    "-----BEGIN CERTIFICATE-----\n"
    "MIIDjjCCAnagAwIBAgIQAzrx5qcRqaC7KGSxHQn65TANBgkqhkiG9w0BAQsFADBh\n"
    "MQswCQYDVQQGEwJVUzEVMBMGA1UEChMMRGlnaUNlcnQgSW5jMRkwFwYDVQQLExB3\n"
    "d3cuZGlnaUNlcnQuY29tMSAwHgYDVQQDExdEaWdpQ2VydCBHbG9iYWwgUm9vdCBH\n"
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
// The EMQX server CA is local deployment data. It is generated into the
// ignored emqx_ca_cert.h file so a cloud certificate change does not require
// committing credentials or a vendor-specific CA to the repository.
const char *rootCa = MQTT_ROOT_CA_CONFIGURED ? MQTT_ROOT_CA_PEM : legacyRootCa;

/** 返回可信的 Unix Epoch 毫秒；SNTP 未完成时返回 0。 */
uint64_t epochMilliseconds()
{
  const time_t now = time(nullptr);
  if (now < 1704067200) // 2024-01-01 之前视为设备尚未完成 SNTP。
  {
    return 0;
  }
  return static_cast<uint64_t>(now) * 1000ULL;
}

const char *targetName(IotCommandTarget target)
{
  switch (target)
  {
  case IotCommandTarget::GrowLight:
    return "grow_light";
  case IotCommandTarget::Position:
    return "position";
  default:
    return "unknown";
  }
}

bool parseSetTarget(const char *value, IotCommandTarget &target)
{
  if (strcmp(value, "grow_light") == 0)
  {
    target = IotCommandTarget::GrowLight;
  }
  else
  {
    target = IotCommandTarget::Unknown;
    return false;
  }
  return true;
}

/** 校验标准 UUID v4；统一使用小写十六进制，避免同一 ID 多种文本形式。 */
bool isUuidV4(const String &value)
{
  if (value.length() != 36 || value.charAt(14) != '4' ||
      (value.charAt(19) != '8' && value.charAt(19) != '9' &&
       value.charAt(19) != 'a' && value.charAt(19) != 'b'))
  {
    return false;
  }

  for (size_t index = 0; index < value.length(); ++index)
  {
    if (index == 8 || index == 13 || index == 18 || index == 23)
    {
      if (value.charAt(index) != '-')
      {
        return false;
      }
      continue;
    }
    const char character = value.charAt(index);
    if (!((character >= '0' && character <= '9') || (character >= 'a' && character <= 'f')))
    {
      return false;
    }
  }
  return true;
}

/** 前端旧水枪队列使用十进制 ID；限制为 1..20 位，防止无界字符串占用 RAM。 */
bool isDecimalCommandId(const String &value)
{
  if (value.length() == 0 || value.length() > 20)
  {
    return false;
  }
  for (size_t index = 0; index < value.length(); ++index)
  {
    if (value.charAt(index) < '0' || value.charAt(index) > '9')
    {
      return false;
    }
  }
  return true;
}

bool isValidCommandId(const String &value)
{
  return isUuidV4(value) || isDecimalCommandId(value);
}

uint32_t payloadFingerprint(const char *payload, size_t length)
{
  uint32_t hash = 2166136261UL;
  for (size_t index = 0; index < length; ++index)
  {
    hash ^= static_cast<uint8_t>(payload[index]);
    hash *= 16777619UL;
  }
  return hash;
}

CommandCacheEntry *findCachedCommand(const String &commandId)
{
  const unsigned long now = millis();
  for (CommandCacheEntry &entry : commandCache)
  {
    if (entry.used && now - entry.storedAt > COMMAND_CACHE_TTL_MS)
    {
      entry.used = false;
      entry.commandId = "";
      entry.ackPayload = "";
    }
    if (entry.used && entry.commandId == commandId)
    {
      return &entry;
    }
  }
  return nullptr;
}

void cacheAck(const IotCommand &command, const String &ackPayload)
{
  CommandCacheEntry *slot = nullptr;
  for (CommandCacheEntry &entry : commandCache)
  {
    if (!entry.used)
    {
      slot = &entry;
      break;
    }
  }
  if (slot == nullptr)
  {
    slot = &commandCache[0];
    for (CommandCacheEntry &entry : commandCache)
    {
      if (entry.storedAt < slot->storedAt)
      {
        slot = &entry;
      }
    }
  }

  slot->used = true;
  slot->commandId = command.commandId;
  slot->fingerprint = command.fingerprint;
  slot->ackPayload = ackPayload;
  slot->storedAt = millis();
}

String makeUuidV4()
{
  uint8_t bytes[16];
  for (uint8_t &value : bytes)
  {
    value = static_cast<uint8_t>(esp_random() & 0xFF);
  }
  bytes[6] = static_cast<uint8_t>((bytes[6] & 0x0F) | 0x40);
  bytes[8] = static_cast<uint8_t>((bytes[8] & 0x3F) | 0x80);

  char output[37];
  snprintf(output, sizeof(output),
           "%02x%02x%02x%02x-%02x%02x-%02x%02x-%02x%02x-%02x%02x%02x%02x%02x%02x",
           bytes[0], bytes[1], bytes[2], bytes[3], bytes[4], bytes[5], bytes[6], bytes[7],
           bytes[8], bytes[9], bytes[10], bytes[11], bytes[12], bytes[13], bytes[14], bytes[15]);
  return String(output);
}

ActuatorState currentActuatorState()
{
  return actuatorStateProvider == nullptr ? ActuatorState{} : actuatorStateProvider();
}

/**
 * 将消息加入 ESP-IDF MQTT outbox。qos 固定为 1；返回的 messageId 用于日志，
 * 真正 PUBACK 由 MQTT 任务异步处理，不阻塞 Arduino 主循环等待网络。
 */
bool publishQos1(const char *topic, const String &payload, bool retain, const char *label)
{
  if (!mqttConnected || mqttClient == nullptr)
  {
    Serial.printf("[MQTT][PUBLISH_SKIP] type=%s reason=disconnected\n", label);
    return false;
  }

  const int messageId = esp_mqtt_client_enqueue(
      mqttClient, topic, payload.c_str(), payload.length(), SAB_MQTT_QOS, retain ? 1 : 0, true);
  if (messageId < 0)
  {
    Serial.printf("[MQTT][PUBLISH_FAIL] type=%s qos=%u retain=%u bytes=%u\n",
                  label, SAB_MQTT_QOS, retain ? 1U : 0U, payload.length());
    return false;
  }

  Serial.printf("[MQTT][PUBLISH_QUEUED] type=%s msg_id=%d qos=%u retain=%u bytes=%u\n",
                label, messageId, SAB_MQTT_QOS, retain ? 1U : 0U, payload.length());
  return true;
}

void publishStatus(bool online, const char *reason)
{
  JsonDocument document;
  // 协议版本和设备 ID 已包含在 Topic 中；状态消息只携带状态本身。
  document["reported_at"] = epochMilliseconds();
  document["online"] = online;
  document["reason"] = reason;
  String payload;
  serializeJson(document, payload);
  publishQos1(statusTopic, payload, true, "status");
}

void publishCapabilities()
{
  JsonDocument document;
  // capabilities 为 retained 快照，只在连接时发送；不重复 Topic 已提供的版本和设备 ID。
  document["reported_at"] = epochMilliseconds();
  JsonObject firmware = document["firmware"].to<JsonObject>();
  firmware["version"] = SAB_FIRMWARE_VERSION;
  firmware["target"] = "esp32";

  JsonObject sensors = document["sensors"].to<JsonObject>();
  sensors["humidity_pct"] = true;
  sensors["illuminance_lux"] = true;
  sensors["temperature_c"] = true;
  sensors["co2_ppm"] = true;

  JsonObject actuators = document["actuators"].to<JsonObject>();
  JsonObject lamp = actuators["grow_light"].to<JsonObject>();
  lamp["supported"] = true;
  lamp["type"] = "percent";
  lamp["min"] = 0;
  lamp["max"] = SAB_GROW_LIGHT_MAX_PERCENT;

  JsonObject positioning = document["positioning"].to<JsonObject>();
  positioning["target_position_supported"] = true;
  positioning["water_gun_control_supported"] = true;
  positioning["water_gun_timed_spray_supported"] = true;
  positioning["water_gun_max_duration_seconds"] = SAB_TIMED_SPRAY_MAX_SECONDS;
  positioning["dynamic_max_hz"] = 5;
  positioning["calibration"] = "UN_CALIBRATED_PLACEHOLDER";

  String payload;
  serializeJson(document, payload);
  publishQos1(capabilitiesTopic, payload, true, "capabilities");
}

String buildAckPayload(const IotCommand &command, bool executed, int actualValue, const char *errorCode)
{
  JsonDocument document;
  // 后端已按 command_id 保存原命令，ACK 只返回最终结果，不回显整条命令。
  document["command_id"] = command.commandId;
  document["acknowledged_at"] = epochMilliseconds();
  document["state"] = executed ? "executed" : "rejected";
  if (executed)
  {
    document["actual_value"] = actualValue;
  }
  else
  {
    document["actual_value"] = nullptr;
  }
  document["feedback_verified"] = false;

  if (executed)
  {
    document["error"] = nullptr;
  }
  else
  {
    JsonObject error = document["error"].to<JsonObject>();
    error["code"] = errorCode;
  }

  String payload;
  serializeJson(document, payload);
  return payload;
}

void publishAckWithoutCaching(const IotCommand &command, bool executed, int actualValue, const char *errorCode)
{
  publishQos1(commandAckTopic, buildAckPayload(command, executed, actualValue, errorCode), false, "command_ack");
}

void publishAckAndCache(const IotCommand &command, bool executed, int actualValue, const char *errorCode)
{
  const String payload = buildAckPayload(command, executed, actualValue, errorCode);
  publishQos1(commandAckTopic, payload, false, "command_ack");
  cacheAck(command, payload);
}

/**
 * 校验精简命令信封。
 *
 * 协议版本和设备身份由精确订阅 Topic
 * smartagribrain/v1/devices/{device_id}/command 确定，因此 JSON 不再重复携带
 * schema_version、device_id、site_id、issued_at、source 和 reason。
 */
bool validateEnvelope(JsonDocument &document, IotCommand &command, bool &identityValidated, const char *&errorCode)
{
  identityValidated = false;
  if (!document["command_id"].is<const char *>() ||
      !document["expires_at"].is<uint64_t>() ||
      !document["command"].is<JsonObject>())
  {
    errorCode = "INVALID_COMMAND";
    Serial.println("[CMD][ENVELOPE_FAIL] field=required_common_field code=INVALID_COMMAND");
    return false;
  }

  command.commandId = document["command_id"].as<String>();
  command.expiresAt = document["expires_at"].as<uint64_t>();

  if (!isValidCommandId(command.commandId))
  {
    errorCode = "INVALID_COMMAND";
    Serial.printf("[CMD][ENVELOPE_FAIL] command_id=%s field=command_id code=INVALID_COMMAND\n", command.commandId.c_str());
    return false;
  }

  const uint64_t now = epochMilliseconds();
  if (now == 0)
  {
    errorCode = "DEVICE_TIME_UNSYNCED";
    Serial.printf("[CMD][ENVELOPE_FAIL] command_id=%s field=device_time code=%s\n", command.commandId.c_str(), errorCode);
    return false;
  }
  if (now > command.expiresAt)
  {
    errorCode = "COMMAND_EXPIRED";
    Serial.printf("[CMD][ENVELOPE_FAIL] command_id=%s field=expires_at code=%s\n", command.commandId.c_str(), errorCode);
    return false;
  }
  if (command.expiresAt - now > 300000ULL)
  {
    errorCode = "INVALID_COMMAND";
    Serial.printf("[CMD][ENVELOPE_FAIL] command_id=%s field=expires_at_too_far code=INVALID_COMMAND\n",
                  command.commandId.c_str());
    return false;
  }

  // 消息已由 MQTT 客户端在本设备的精确 command Topic 上接收，可触发非法水枪命令的安全停泵。
  identityValidated = true;
  return true;
}

bool parseSetCommand(JsonObject commandObject, IotCommand &command, const char *&errorCode)
{
  if (!commandObject["target"].is<const char *>() || !commandObject["value"].is<int>())
  {
    errorCode = "INVALID_COMMAND";
    return false;
  }
  if (!parseSetTarget(commandObject["target"].as<const char *>(), command.target))
  {
    errorCode = "CAPABILITY_UNSUPPORTED";
    return false;
  }

  command.kind = IotCommandKind::SetActuator;
  command.value = commandObject["value"].as<int>();
  const bool lampValid = command.target == IotCommandTarget::GrowLight && command.value >= 0 && command.value <= SAB_GROW_LIGHT_MAX_PERCENT;
  if (!lampValid)
  {
    errorCode = "INVALID_COMMAND";
    return false;
  }
  return true;
}

bool parseWaterGunCommand(JsonObject commandObject, IotCommand &command, const char *&errorCode)
{
  command.kind = IotCommandKind::TargetPosition;
  command.target = IotCommandTarget::Position;

  if (!commandObject["target"].is<const char *>() || strcmp(commandObject["target"].as<const char *>(), "position") != 0 ||
      !commandObject["position"].is<JsonObject>() || !commandObject["water_gun"].is<JsonObject>())
  {
    errorCode = "INVALID_COMMAND";
    return false;
  }

  command.value = commandObject["value"].is<int>() ? commandObject["value"].as<int>() : 1;
  JsonObject position = commandObject["position"].as<JsonObject>();
  JsonObject waterGun = commandObject["water_gun"].as<JsonObject>();

  if (!position["ground_range_mm"].is<float>() || !position["bearing_deg"].is<float>() ||
      !waterGun["mode"].is<const char *>() || !waterGun["spray_enabled"].is<bool>() ||
      !waterGun["pump_control_percent"].is<float>() ||
      !waterGun["sequence"].is<uint32_t>() || !waterGun["spray_schedule"].is<const char *>())
  {
    errorCode = "INVALID_COMMAND";
    return false;
  }

  command.groundRangeMm = position["ground_range_mm"].as<float>();
  command.bearingDeg = position["bearing_deg"].as<float>();
  command.sprayEnabled = waterGun["spray_enabled"].as<bool>();
  command.pumpControlPercent = waterGun["pump_control_percent"].as<float>();
  command.sequence = waterGun["sequence"].as<uint32_t>();

  const char *mode = waterGun["mode"].as<const char *>();
  if (strcmp(mode, "static") == 0)
  {
    command.waterGunMode = WaterGunMode::Static;
  }
  else if (strcmp(mode, "dynamic") == 0)
  {
    command.waterGunMode = WaterGunMode::Dynamic;
  }
  else
  {
    errorCode = "INVALID_COMMAND";
    return false;
  }

  const char *schedule = waterGun["spray_schedule"].as<const char *>();
  if (strcmp(schedule, "continuous") == 0)
  {
    command.spraySchedule = SpraySchedule::Continuous;
  }
  else if (strcmp(schedule, "timed") == 0)
  {
    command.spraySchedule = SpraySchedule::Timed;
  }
  else
  {
    errorCode = "INVALID_COMMAND";
    return false;
  }

  command.sessionId = waterGun["session_id"].is<const char *>() ? waterGun["session_id"].as<String>() : String();
  command.sprayDurationPresent = !waterGun["spray_duration_seconds"].isNull();
  command.sprayEndsAtPresent = !waterGun["spray_ends_at"].isNull();
  if (command.sprayDurationPresent)
  {
    if (!waterGun["spray_duration_seconds"].is<uint32_t>())
    {
      errorCode = "INVALID_COMMAND";
      return false;
    }
    command.sprayDurationSeconds = waterGun["spray_duration_seconds"].as<uint32_t>();
  }
  if (command.sprayEndsAtPresent)
  {
    if (!waterGun["spray_ends_at"].is<uint64_t>())
    {
      errorCode = "INVALID_COMMAND";
      return false;
    }
    command.sprayEndsAt = waterGun["spray_ends_at"].as<uint64_t>();
  }

  if (!isfinite(command.groundRangeMm) || !isfinite(command.bearingDeg) || !isfinite(command.pumpControlPercent) ||
      command.groundRangeMm < SAB_PLACEHOLDER_RANGE_MIN_MM || command.groundRangeMm > SAB_PLACEHOLDER_RANGE_MAX_MM ||
      command.bearingDeg < SAB_PLACEHOLDER_BEARING_MIN_DEG || command.bearingDeg > SAB_PLACEHOLDER_BEARING_MAX_DEG ||
      command.pumpControlPercent < 0.0F || command.pumpControlPercent > 100.0F)
  {
    errorCode = "TARGET_OUT_OF_RANGE";
    return false;
  }

  if (command.waterGunMode == WaterGunMode::Dynamic)
  {
    if (command.sessionId.length() == 0 || command.sessionId.length() > 79 || command.sequence == 0 ||
        command.spraySchedule != SpraySchedule::Continuous ||
        command.sprayDurationPresent || command.sprayEndsAtPresent)
    {
      errorCode = "INVALID_COMMAND";
      return false;
    }
  }
  else if (command.sessionId.length() != 0)
  {
    errorCode = "INVALID_COMMAND";
    return false;
  }

  // 停止包优先语义：允许 timed + 原 duration + ends_at=null，不要求重新构造有效截止时间。
  if (!command.sprayEnabled)
  {
    if (command.pumpControlPercent != 0.0F)
    {
      errorCode = "INVALID_COMMAND";
      return false;
    }
    return true;
  }

  if (command.pumpControlPercent <= 0.0F)
  {
    errorCode = "INVALID_COMMAND";
    return false;
  }
  if (command.spraySchedule == SpraySchedule::Continuous)
  {
    if (command.sprayDurationPresent || command.sprayEndsAtPresent)
    {
      errorCode = "INVALID_COMMAND";
      return false;
    }
    return true;
  }

  if (!command.sprayDurationPresent || !command.sprayEndsAtPresent || command.sprayDurationSeconds < 1 ||
      command.sprayDurationSeconds > SAB_TIMED_SPRAY_MAX_SECONDS)
  {
    errorCode = "INVALID_COMMAND";
    return false;
  }

  const uint64_t now = epochMilliseconds();
  if (now == 0)
  {
    errorCode = "DEVICE_TIME_UNSYNCED";
    return false;
  }
  if (command.sprayEndsAt <= now)
  {
    errorCode = "TIMED_SPRAY_EXPIRED";
    return false;
  }
  const uint64_t remainingMs = command.sprayEndsAt - now;
  const uint64_t configuredMs = static_cast<uint64_t>(command.sprayDurationSeconds) * 1000ULL;
  if (remainingMs > configuredMs + 2000ULL)
  {
    errorCode = "INVALID_COMMAND";
    return false;
  }
  return true;
}

bool validateCommand(JsonDocument &document, IotCommand &command, bool &identityValidated,
                     bool &waterGunRecognized, const char *&errorCode)
{
  if (!validateEnvelope(document, command, identityValidated, errorCode))
  {
    return false;
  }

  JsonObject commandObject = document["command"].as<JsonObject>();
  if (!commandObject["operation"].is<const char *>())
  {
    errorCode = "INVALID_COMMAND";
    return false;
  }

  const char *operation = commandObject["operation"].as<const char *>();
  waterGunRecognized = strcmp(operation, "target_position") == 0;
  if (strcmp(operation, "set") == 0)
  {
    return parseSetCommand(commandObject, command, errorCode);
  }
  if (waterGunRecognized)
  {
    return parseWaterGunCommand(commandObject, command, errorCode);
  }
  errorCode = "CAPABILITY_UNSUPPORTED";
  return false;
}

void dispatchCommand(const IotCommand &command)
{
  int actualValue = 0;
  const char *errorCode = "INTERNAL_ERROR";
  if (commandHandler == nullptr)
  {
    Serial.printf("[CMD][DISPATCH_FAIL] command_id=%s code=INTERNAL_ERROR reason=no_handler\n", command.commandId.c_str());
    publishAckAndCache(command, false, 0, errorCode);
    return;
  }

  Serial.printf("[CMD][DISPATCH] command_id=%s kind=%s target=%s\n",
                command.commandId.c_str(),
                command.kind == IotCommandKind::TargetPosition ? "target_position" : "set",
                targetName(command.target));
  const IotCommandResult result = commandHandler(command, actualValue, errorCode);
  if (result == IotCommandResult::Executed)
  {
    Serial.printf("[CMD][EXECUTED] command_id=%s actual_value=%d\n", command.commandId.c_str(), actualValue);
    publishAckAndCache(command, true, actualValue, nullptr);
  }
  else if (result == IotCommandResult::Rejected)
  {
    Serial.printf("[CMD][REJECTED] command_id=%s code=%s\n", command.commandId.c_str(), errorCode);
    publishAckAndCache(command, false, 0, errorCode);
  }
  else
  {
    inFlightCommandUsed = true;
    inFlightCommandId = command.commandId;
    inFlightFingerprint = command.fingerprint;
    Serial.printf("[CMD][PENDING] command_id=%s reason=non_blocking_state_machine\n", command.commandId.c_str());
  }
}

void processRawCommand(const RawCommandMessage &raw)
{
  Serial.printf("[CMD][RECEIVED] bytes=%u qos=%u dup=%u\n", raw.length, raw.qos, raw.duplicate ? 1U : 0U);
  JsonDocument document;
  const DeserializationError parseError = deserializeJson(document, raw.payload, raw.length);
  if (parseError)
  {
    Serial.printf("[CMD][JSON_FAIL] code=INVALID_COMMAND detail=%s action=ignore_no_gpio\n", parseError.c_str());
    return;
  }

  IotCommand command;
  if (document["command_id"].is<const char *>())
  {
    command.commandId = document["command_id"].as<String>();
  }
  command.fingerprint = payloadFingerprint(raw.payload, raw.length);

  if (isValidCommandId(command.commandId))
  {
    CommandCacheEntry *cached = findCachedCommand(command.commandId);
    if (cached != nullptr)
    {
      if (cached->fingerprint == command.fingerprint)
      {
        Serial.printf("[CMD][DUPLICATE] command_id=%s action=resend_cached_ack\n", command.commandId.c_str());
        publishQos1(commandAckTopic, cached->ackPayload, false, "command_ack_duplicate");
      }
      else
      {
        Serial.printf("[CMD][ID_COLLISION] command_id=%s action=reject_preserve_cache\n", command.commandId.c_str());
        publishAckWithoutCaching(command, false, 0, "INVALID_COMMAND");
      }
      return;
    }

    if (inFlightCommandUsed && inFlightCommandId == command.commandId)
    {
      if (inFlightFingerprint == command.fingerprint)
      {
        Serial.printf("[CMD][DUPLICATE_PENDING] command_id=%s action=wait_original_ack\n", command.commandId.c_str());
      }
      else
      {
        Serial.printf("[CMD][ID_COLLISION_PENDING] command_id=%s action=reject\n", command.commandId.c_str());
        publishAckWithoutCaching(command, false, 0, "INVALID_COMMAND");
      }
      return;
    }
  }

  bool identityValidated = false;
  bool waterGunRecognized = false;
  const char *errorCode = "INVALID_COMMAND";
  if (!validateCommand(document, command, identityValidated, waterGunRecognized, errorCode))
  {
    Serial.printf("[CMD][VALIDATION_FAIL] command_id=%s identity=%u water_gun=%u code=%s\n",
                  command.commandId.c_str(), identityValidated ? 1U : 0U, waterGunRecognized ? 1U : 0U, errorCode);
    if (identityValidated && waterGunRecognized)
    {
      safetyStopRequested = true;
      Serial.println("[CMD][FAIL_SAFE_REQUEST] reason=authenticated_invalid_water_gun_command");
    }
    if (isValidCommandId(command.commandId))
    {
      publishAckAndCache(command, false, 0, errorCode);
    }
    return;
  }

  Serial.printf("[CMD][VALIDATED] command_id=%s ttl_remaining_ms=%llu\n",
                command.commandId.c_str(), command.expiresAt - epochMilliseconds());
  dispatchCommand(command);
}

/** MQTT 数据事件分片拼接完成后，把完整 JSON 放入主循环队列。 */
void queueMqttDataEvent(esp_mqtt_event_handle_t event)
{
  if (event->current_data_offset == 0)
  {
    assemblingExpectedLength = static_cast<size_t>(event->total_data_len);
    assemblingReceivedLength = 0;
    assemblingCommandTopic = event->topic != nullptr &&
                             event->topic_len == static_cast<int>(strlen(commandTopic)) &&
                             memcmp(event->topic, commandTopic, event->topic_len) == 0;
  }

  if (!assemblingCommandTopic)
  {
    return;
  }
  if (assemblingExpectedLength == 0 || assemblingExpectedLength > RAW_COMMAND_MAX_BYTES ||
      event->current_data_offset < 0 || event->data_len < 0 ||
      static_cast<size_t>(event->current_data_offset + event->data_len) > RAW_COMMAND_MAX_BYTES)
  {
    Serial.printf("[MQTT][RX_DROP] reason=payload_too_large total=%d max=%u\n",
                  event->total_data_len, RAW_COMMAND_MAX_BYTES);
    assemblingCommandTopic = false;
    safetyStopRequested = true;
    return;
  }

  memcpy(assemblingPayload + event->current_data_offset, event->data, event->data_len);
  assemblingReceivedLength += static_cast<size_t>(event->data_len);
  if (assemblingReceivedLength < assemblingExpectedLength)
  {
    return;
  }

  assemblingPayload[assemblingExpectedLength] = '\0';
  RawCommandMessage message;
  message.length = static_cast<uint16_t>(assemblingExpectedLength);
  message.qos = static_cast<uint8_t>(event->qos);
  message.duplicate = event->dup;
  memcpy(message.payload, assemblingPayload, assemblingExpectedLength + 1);
  if (rawCommandQueue == nullptr || xQueueSend(rawCommandQueue, &message, 0) != pdTRUE)
  {
    Serial.println("[MQTT][RX_DROP] reason=command_queue_full action=request_safety_stop");
    safetyStopRequested = true;
  }
  else
  {
    Serial.printf("[MQTT][RX_QUEUED] bytes=%u qos=%u dup=%u\n",
                  message.length, message.qos, message.duplicate ? 1U : 0U);
  }
  assemblingCommandTopic = false;
}

void mqttEventHandler(void *, esp_event_base_t, int32_t eventId, void *eventData)
{
  esp_mqtt_event_handle_t event = static_cast<esp_mqtt_event_handle_t>(eventData);
  switch (static_cast<esp_mqtt_event_id_t>(eventId))
  {
  case MQTT_EVENT_CONNECTED:
  {
    mqttConnected = true;
    const int subscribeId = esp_mqtt_client_subscribe(event->client, commandTopic, SAB_MQTT_QOS);
    publishConnectSnapshotRequested = true;
    Serial.printf("[MQTT][CONNECTED] session_present=%d subscribe_msg_id=%d topic=%s qos=%u\n",
                  event->session_present, subscribeId, commandTopic, SAB_MQTT_QOS);
    break;
  }
  case MQTT_EVENT_DISCONNECTED:
    mqttConnected = false;
    safetyStopRequested = true;
    Serial.println("[MQTT][DISCONNECTED] action=request_safety_stop auto_reconnect=enabled");
    break;
  case MQTT_EVENT_DATA:
    queueMqttDataEvent(event);
    break;
  case MQTT_EVENT_PUBLISHED:
    Serial.printf("[MQTT][PUBACK] msg_id=%d\n", event->msg_id);
    break;
  case MQTT_EVENT_ERROR:
    if (event->error_handle != nullptr)
    {
      Serial.printf("[MQTT][ERROR] type=%d tls=0x%x stack=0x%x socket=%d connect_code=%d\n",
                    event->error_handle->error_type,
                    event->error_handle->esp_tls_last_esp_err,
                    event->error_handle->esp_tls_stack_err,
                    event->error_handle->esp_transport_sock_errno,
                    event->error_handle->connect_return_code);
    }
    break;
  default:
    break;
  }
}
} // namespace

void init_mqtt()
{
  snprintf(telemetryTopic, sizeof(telemetryTopic), "%s/devices/%s/telemetry", SAB_TOPIC_PREFIX, SAB_DEVICE_ID);
  snprintf(statusTopic, sizeof(statusTopic), "%s/devices/%s/status", SAB_TOPIC_PREFIX, SAB_DEVICE_ID);
  snprintf(capabilitiesTopic, sizeof(capabilitiesTopic), "%s/devices/%s/capabilities", SAB_TOPIC_PREFIX, SAB_DEVICE_ID);
  snprintf(commandTopic, sizeof(commandTopic), "%s/devices/%s/command", SAB_TOPIC_PREFIX, SAB_DEVICE_ID);
  snprintf(commandAckTopic, sizeof(commandAckTopic), "%s/devices/%s/command_ack", SAB_TOPIC_PREFIX, SAB_DEVICE_ID);
  snprintf(clientId, sizeof(clientId), "sab-dev-%s", SAB_DEVICE_ID);

  if (rawCommandQueue == nullptr)
  {
    rawCommandQueue = xQueueCreate(RAW_COMMAND_QUEUE_DEPTH, sizeof(RawCommandMessage));
  }
  if (rawCommandQueue == nullptr)
  {
    Serial.println("[MQTT][INIT_FAIL] stage=create_command_queue");
    return;
  }

  configTime(0, 0, "pool.ntp.org", "time.nist.gov");

  JsonDocument willDocument;
  // LWT 的设备身份来自 lwt_topic；只保留后端判断离线所需的最小状态。
  willDocument["reported_at"] = 0;
  willDocument["online"] = false;
  willDocument["reason"] = "unexpected_disconnect";
  mqttWillPayload = "";
  serializeJson(willDocument, mqttWillPayload);

  esp_mqtt_client_config_t config = {};
  config.host = MQTT_SERVER;
  config.port = MQTT_PORT;
  config.transport = MQTT_TRANSPORT_OVER_SSL;
  config.client_id = clientId;
  config.username = MQTT_USER;
  config.password = MQTT_PASS;
  config.cert_pem = rootCa;
  config.lwt_topic = statusTopic;
  config.lwt_msg = mqttWillPayload.c_str();
  config.lwt_msg_len = mqttWillPayload.length();
  config.lwt_qos = SAB_MQTT_QOS;
  config.lwt_retain = 1;
  config.disable_clean_session = 1; // false clean-session，即 Broker 保留 QoS 1 会话状态。
  config.keepalive = 30;
  config.task_stack = 8192; // DATA 事件需临时复制最多 3072 字节命令，扩大 MQTT 任务栈避免溢出。
  config.buffer_size = MQTT_IO_BUFFER_SIZE;
  config.out_buffer_size = MQTT_IO_BUFFER_SIZE;
  config.reconnect_timeout_ms = 5000;
  config.protocol_ver = MQTT_PROTOCOL_V_3_1_1;

  mqttClient = esp_mqtt_client_init(&config);
  if (mqttClient == nullptr)
  {
    Serial.println("[MQTT][INIT_FAIL] stage=esp_mqtt_client_init");
    return;
  }
  esp_mqtt_client_register_event(mqttClient, MQTT_EVENT_ANY, mqttEventHandler, nullptr);
  const esp_err_t startResult = esp_mqtt_client_start(mqttClient);
  Serial.printf("[MQTT][INIT] client_id=%s host=%s port=%u qos=%u persistent_session=1 result=%s\n",
                clientId, MQTT_SERVER, MQTT_PORT, SAB_MQTT_QOS, esp_err_to_name(startResult));
}

void mqtt_loop()
{
  // 阶段 1：网络事件只设置标志；硬件安全动作统一在 Arduino 主循环执行。
  if (safetyStopRequested)
  {
    safetyStopRequested = false;
    if (safetyStopHandler != nullptr)
    {
      Serial.println("[SAFETY][EXECUTE] source=mqtt_or_invalid_command action=emergency_stop");
      safetyStopHandler();
    }
  }

  // 阶段 2：连接成功后发布 retained 在线状态与真实能力声明。
  if (publishConnectSnapshotRequested && mqttConnected)
  {
    publishConnectSnapshotRequested = false;
    publishCapabilities();
    publishStatus(true, "connected");
  }

  // 阶段 3：消费完整 JSON；解析、校验和应用回调均在主循环上下文执行。
  RawCommandMessage message;
  while (rawCommandQueue != nullptr && xQueueReceive(rawCommandQueue, &message, 0) == pdTRUE)
  {
    processRawCommand(message);
  }
}

void mqtt_notify_wifi_disconnected()
{
  mqttConnected = false;
  safetyStopRequested = true;
}

void set_iot_command_handler(IotCommandHandler handler)
{
  commandHandler = handler;
}

void set_actuator_state_provider(ActuatorStateProvider provider)
{
  actuatorStateProvider = provider;
}

void set_safety_stop_handler(SafetyStopHandler handler)
{
  safetyStopHandler = handler;
}

void mqtt_complete_command(const IotCommand &command, bool executed, int actualValue, const char *errorCode)
{
  if (executed)
  {
    Serial.printf("[CMD][ASYNC_EXECUTED] command_id=%s actual_value=%d\n", command.commandId.c_str(), actualValue);
    publishAckAndCache(command, true, actualValue, nullptr);
  }
  else
  {
    const char *stableError = errorCode == nullptr ? "INTERNAL_ERROR" : errorCode;
    Serial.printf("[CMD][ASYNC_REJECTED] command_id=%s code=%s\n", command.commandId.c_str(), stableError);
    publishAckAndCache(command, false, 0, stableError);
  }

  if (inFlightCommandUsed && inFlightCommandId == command.commandId)
  {
    inFlightCommandUsed = false;
    inFlightCommandId = "";
    inFlightFingerprint = 0;
  }
}

void send_sensor_data(Dht11Sensor *dht11Sensor, BH1750 *bh1750, JW01_CO2 *co2Sensor)
{
  if (!mqttConnected)
  {
    Serial.println("[TELEMETRY][SKIP] reason=mqtt_disconnected");
    return;
  }

  const ActuatorState state = currentActuatorState();
  JsonDocument document;
  // message_id 用于 QoS 1 去重；设备 ID 和协议版本已由 Topic 唯一确定。
  document["message_id"] = makeUuidV4();
  document["sampled_at"] = epochMilliseconds();

  JsonObject sensors = document["sensors"].to<JsonObject>();
  JsonObject quality = document["quality"].to<JsonObject>();
  // Keep sensor value and quality inseparable. A non-finite driver result is
  // published as JSON null so the backend never treats an invalid ADC/I2C
  // reading as a real environmental measurement.
  const auto publishSensor = [&sensors, &quality](const char *name, float value) {
    if (isfinite(value))
    {
      sensors[name] = value;
      quality[name] = "ok";
    }
    else
    {
      sensors[name] = nullptr;
      quality[name] = "invalid";
    }
  };
  publishSensor("humidity_pct", dht11Sensor->getHumidityPercent());
  publishSensor("illuminance_lux", bh1750->readLight());
  publishSensor("temperature_c", dht11Sensor->getTemperatureC());
  publishSensor("co2_ppm", co2Sensor->getCO2());

  JsonObject actuators = document["actuators"].to<JsonObject>();
  // 补光灯没有反馈线，单个百分比表示 ESP32 当前写入 GPIO14 的 PWM 目标值。
  actuators["grow_light"] = state.growLightPercent;

  JsonObject positioning = document["positioning"].to<JsonObject>();
  positioning["pan_deg"] = state.panAngleDeg;
  positioning["tilt_deg"] = state.tiltAngleDeg;
  positioning["calibration"] = "UN_CALIBRATED_PLACEHOLDER";
  JsonObject waterGun = positioning["water_gun"].to<JsonObject>();
  waterGun["active"] = state.waterGunActive;
  waterGun["timed"] = state.waterGunTimed;
  waterGun["dynamic"] = state.waterGunDynamic;
  if (state.sprayEndsAt == 0)
  {
    waterGun["spray_ends_at"] = nullptr;
  }
  else
  {
    waterGun["spray_ends_at"] = state.sprayEndsAt;
  }
  waterGun["sequence"] = state.waterGunSequence;

  JsonObject connectivity = document["connectivity"].to<JsonObject>();
  // 能收到本消息已能证明发送时 Wi-Fi/MQTT 可用，只保留无法从 Topic 推导的 RSSI。
  connectivity["rssi_dbm"] = WiFi.RSSI();

  String payload;
  serializeJson(document, payload);
  publishQos1(telemetryTopic, payload, false, "telemetry");
}
