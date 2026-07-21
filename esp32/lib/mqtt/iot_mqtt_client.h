#ifndef IOT_MQTT_CLIENT_H
#define IOT_MQTT_CLIENT_H

#include <Arduino.h>

#include "JW01_CO2.h"
#include "LightSensor.h"
#include "SoilSensor.h"
#include "TempSensor.h"
#include "iot_contract.h"

/** MQTT 命令的业务类型。普通执行器使用 SetActuator；水枪使用 TargetPosition。 */
enum class IotCommandKind : uint8_t
{
  SetActuator,
  TargetPosition,
};

/** 普通 set 命令的目标。Position 只用于复合水枪命令，不直接代表一个 GPIO。 */
enum class IotCommandTarget : uint8_t
{
  Pump,
  GrowLight,
  Pan,
  Tilt,
  Position,
  Unknown,
};

/** 水枪工作方式：Static 表示定点控制，Dynamic 表示需要会话保活的连续跟踪。 */
enum class WaterGunMode : uint8_t
{
  Static,
  Dynamic,
};

/** 喷水时间方案：Continuous 持续到停止命令；Timed 由设备本地截止计时器停止。 */
enum class SpraySchedule : uint8_t
{
  Continuous,
  Timed,
};

/**
 * 已通过 MQTT 基础校验的命令。
 *
 * 所有时间字段均为 UTC Unix Epoch 毫秒；角度单位为 deg；距离单位为 mm；
 * 百分比范围为 0..100。has* 字段用于区分 JSON null/缺失与数值 0。
 */
struct IotCommand
{
  String commandId;                 // UUID v4 或仅含十进制数字的非空字符串，作为幂等键。
  String deviceId;                  // 必须等于 SAB_DEVICE_ID，否则报文不能驱动硬件。
  String siteId;                    // 可选站点字段；出现时必须等于 SAB_SITE_ID。
  String source;                    // web_manual/web_automation/ai/edge_voice/system。
  String reason;                    // 后端给出的可读原因，只用于日志和审计，不参与控制判断。
  uint64_t issuedAt = 0;            // 命令创建时间，Unix Epoch 毫秒。
  uint64_t expiresAt = 0;           // 命令失效时间，必须晚于 issuedAt 且 TTL 为 5..300 秒。
  uint32_t fingerprint = 0;         // 原始 JSON 的 FNV-1a 指纹，用于检测同 ID 不同内容。

  IotCommandKind kind = IotCommandKind::SetActuator;
  IotCommandTarget target = IotCommandTarget::Unknown;
  int value = 0;                    // 普通 set 值；水枪命令固定为 1，仅保留用于协议回显。

  float groundRangeMm = 0.0F;       // 水枪原点到目标地面点的水平距离，临时允许 300..1200 mm。
  float bearingDeg = 0.0F;          // 目标方向角，临时允许 -45..45 deg，0 表示正前方。
  WaterGunMode waterGunMode = WaterGunMode::Static;
  bool sprayEnabled = false;        // false 表示有效命令完成基础校验后必须优先停泵。
  bool simulationOnly = true;       // true 时禁止写舵机和水泵，仅验证协议并返回 ACK。
  float pumpControlPercent = 0.0F;  // 后端临时目标百分比；设备四舍五入并应用最小 40%。
  String sessionId;                 // Dynamic 必填；Static 必须为空字符串。
  uint32_t sequence = 0;            // 同一动态会话严格递增，用于拒绝乱序和 QoS 1 重发。
  SpraySchedule spraySchedule = SpraySchedule::Continuous;
  bool sprayDurationPresent = false;
  uint32_t sprayDurationSeconds = 0; // Timed 必填，范围 1..86399 秒。
  bool sprayEndsAtPresent = false;
  uint64_t sprayEndsAt = 0;         // Timed 开泵时必填；停止包允许缺失/null。
};

/** 供 telemetry 使用的执行器快照；值来自统一硬件状态，不从最近命令反推。 */
struct ActuatorState
{
  int pumpPercent = 0;
  int growLightPercent = 0;
  int panAngleDeg = 90;
  int tiltAngleDeg = 90;
  bool waterGunActive = false;
  bool waterGunTimed = false;
  bool waterGunDynamic = false;
  uint64_t sprayEndsAt = 0;
  uint32_t waterGunSequence = 0;
};

/** 命令处理返回值：同步完成、已进入非阻塞状态机、或明确拒绝。 */
enum class IotCommandResult : uint8_t
{
  Executed,
  Pending,
  Rejected,
};

/**
 * 应用层命令处理器。
 * @param command 已完成协议和值域校验的命令，只在 Arduino 主循环调用。
 * @param actualValue 同步完成时写入真实应用值；异步命令在完成函数中提供。
 * @param errorCode 拒绝时指向稳定错误码字符串；成功时保持 nullptr。
 */
using IotCommandHandler = IotCommandResult (*)(const IotCommand &command, int &actualValue, const char *&errorCode);
using ActuatorStateProvider = ActuatorState (*)();
using SafetyStopHandler = void (*)();

/** 初始化 Topic、SNTP、QoS 1 持久 MQTT 会话和接收队列；setup 中调用一次。 */
void init_mqtt();

/** 推进 MQTT 收包解析、应用命令分发和安全事件；Arduino loop 每轮调用。 */
void mqtt_loop();

/** WiFi 已断开时请求主循环执行统一安全停泵，不在网络回调中直接操作复杂状态。 */
void mqtt_notify_wifi_disconnected();

void set_iot_command_handler(IotCommandHandler handler);
void set_actuator_state_provider(ActuatorStateProvider provider);
void set_safety_stop_handler(SafetyStopHandler handler);

/**
 * 完成此前返回 Pending 的异步命令并发布 QoS 1 ACK。
 * @param command 必须是进入状态机时保存的原命令，commandId 用于幂等缓存。
 * @param executed true 表示控制输出已经写入且状态机无错误。
 * @param actualValue 真实应用的执行器值；水枪命令为实际水泵百分比。
 * @param errorCode executed=false 时的稳定错误码，不能为 nullptr。
 */
void mqtt_complete_command(const IotCommand &command, bool executed, int actualValue, const char *errorCode);

/** 发布一次 QoS 1 遥测快照；传入的四个指针必须指向已初始化传感器实例。 */
void send_sensor_data(SoilSensor *soilSensor, BH1750 *bh1750, TempSensor *tempSensor, JW01_CO2 *co2Sensor);

#endif
