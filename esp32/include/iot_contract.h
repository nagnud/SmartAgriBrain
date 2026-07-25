#ifndef IOT_CONTRACT_H
#define IOT_CONTRACT_H

// 实际芯片是普通 ESP32；字符串中的 "_s3" 仅用于兼容前端已经确定的协议命名，
// 不能据此把 PlatformIO 开发板改成 ESP32-S3。device_id 同时用于 MQTT Topic、
// MQTT Client ID 和后端设备注册；精简 JSON 不再重复该值。
#ifndef SAB_DEVICE_ID
#define SAB_DEVICE_ID "greenhouse_001_s3"
#endif

// site_id 只用于启动诊断和部署核对。MQTT 消息不重复该值，后端根据 Topic
// 中的 device_id 和设备注册关系确定站点归属。
#ifndef SAB_SITE_ID
#define SAB_SITE_ID "greenhouse_001"
#endif

#ifndef SAB_TOPIC_PREFIX
#define SAB_TOPIC_PREFIX "smartagribrain/v1"
#endif

#ifndef SAB_FIRMWARE_VERSION
#define SAB_FIRMWARE_VERSION "0.3.0"
#endif

constexpr uint8_t SAB_MQTT_QOS = 1;
constexpr uint8_t SAB_PUMP_MAX_PERCENT = 100;
constexpr uint8_t SAB_PUMP_MIN_RUNNING_PERCENT = 40;
constexpr uint16_t SAB_PUMP_PWM_FREQUENCY_HZ = 1000;
constexpr bool SAB_PUMP_ACTIVE_HIGH = true;
constexpr uint8_t SAB_GROW_LIGHT_MAX_PERCENT = 90;
// 两个 SG90 的机械可用范围不同，必须分别限制，不能使用同一组 0..180 度边界。
// 水平轴仍使用完整命令范围；垂直轴范围来自实体机构确认：5 度为平射，60 度为竖直向上。
constexpr uint8_t SAB_PAN_MECHANICAL_MIN_DEG = 0;
constexpr uint8_t SAB_PAN_MECHANICAL_MAX_DEG = 180;
constexpr uint8_t SAB_TILT_MECHANICAL_MIN_DEG = 5;
constexpr uint8_t SAB_TILT_MECHANICAL_MAX_DEG = 60;

// 水平映射和“距离到俯仰角”的线性轨迹模型尚未经过喷水落点标定。
// 垂直轴 5..60 度机械端点已经由实体机构确认，但仍不能据此宣称能够准确命中目标。
constexpr float SAB_PLACEHOLDER_BEARING_MIN_DEG = -90.0F;
constexpr float SAB_PLACEHOLDER_BEARING_MAX_DEG = 90.0F;
constexpr int SAB_PLACEHOLDER_PAN_MIN_DEG = SAB_PAN_MECHANICAL_MIN_DEG;
constexpr int SAB_PLACEHOLDER_PAN_CENTER_DEG = 90;
constexpr int SAB_PLACEHOLDER_PAN_MAX_DEG = SAB_PAN_MECHANICAL_MAX_DEG;
constexpr uint32_t SAB_PLACEHOLDER_RANGE_MIN_MM = 300;
constexpr uint32_t SAB_PLACEHOLDER_RANGE_MAX_MM = 1200;
// 目标越近，水枪仰角越大；目标越远，水枪越接近平射。
// 端点角度已由实体机构确认，端点之间的距离关系仍采用线性控制模型。
constexpr int SAB_TILT_NEAR_DEG = SAB_TILT_MECHANICAL_MAX_DEG;
constexpr int SAB_TILT_FAR_DEG = SAB_TILT_MECHANICAL_MIN_DEG;
constexpr uint32_t SAB_PLACEHOLDER_SERVO_SETTLE_MS = 800;
constexpr uint32_t SAB_DYNAMIC_COMMAND_TIMEOUT_MS = 3000;
constexpr uint32_t SAB_TIMED_SPRAY_MAX_SECONDS = 86399;

#endif
