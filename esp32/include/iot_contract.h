#ifndef IOT_CONTRACT_H
#define IOT_CONTRACT_H

// 实际芯片是普通 ESP32；字符串中的 "_s3" 仅用于兼容前端已经确定的协议命名，
// 不能据此把 PlatformIO 开发板改成 ESP32-S3。device_id 同时用于 MQTT Topic、
// MQTT Client ID 和所有上行 JSON，后端设备注册必须逐字符使用同一值。
#ifndef SAB_DEVICE_ID
#define SAB_DEVICE_ID "greenhouse_001_s3"
#endif

// site_id 表示设备所属站点，不参与硬件寻址，但普通命令、ACK、状态和遥测都
// 携带该字段，便于后端在多站点场景中校验设备归属。
#ifndef SAB_SITE_ID
#define SAB_SITE_ID "greenhouse_001"
#endif

#ifndef SAB_TOPIC_PREFIX
#define SAB_TOPIC_PREFIX "smartagribrain/v1"
#endif

#ifndef SAB_FIRMWARE_VERSION
#define SAB_FIRMWARE_VERSION "0.3.0"
#endif

constexpr char SAB_SCHEMA_VERSION[] = "1.0";
constexpr uint8_t SAB_MQTT_QOS = 1;
constexpr uint8_t SAB_PUMP_MAX_PERCENT = 100;
constexpr uint8_t SAB_PUMP_MIN_RUNNING_PERCENT = 40;
constexpr uint16_t SAB_PUMP_PWM_FREQUENCY_HZ = 1000;
constexpr bool SAB_PUMP_ACTIVE_HIGH = true;
constexpr uint8_t SAB_GROW_LIGHT_MAX_PERCENT = 90;
constexpr uint8_t SAB_SERVO_MIN_ANGLE_DEG = 0;
constexpr uint8_t SAB_SERVO_MAX_ANGLE_DEG = 180;

// 以下水枪标定值没有经过实物测量，只用于让通信和状态机在保守角度内跑通。
// 每个使用位置都必须输出 UN_CALIBRATED_PLACEHOLDER，完成真实标定后整体替换。
constexpr float SAB_PLACEHOLDER_BEARING_MIN_DEG = -45.0F;
constexpr float SAB_PLACEHOLDER_BEARING_MAX_DEG = 45.0F;
constexpr int SAB_PLACEHOLDER_PAN_MIN_DEG = 60;
constexpr int SAB_PLACEHOLDER_PAN_CENTER_DEG = 90;
constexpr int SAB_PLACEHOLDER_PAN_MAX_DEG = 120;
constexpr uint32_t SAB_PLACEHOLDER_RANGE_MIN_MM = 300;
constexpr uint32_t SAB_PLACEHOLDER_RANGE_MID_MM = 750;
constexpr uint32_t SAB_PLACEHOLDER_RANGE_MAX_MM = 1200;
constexpr int SAB_PLACEHOLDER_TILT_NEAR_DEG = 110;
constexpr int SAB_PLACEHOLDER_TILT_MID_DEG = 90;
constexpr int SAB_PLACEHOLDER_TILT_FAR_DEG = 70;
constexpr uint32_t SAB_PLACEHOLDER_SERVO_SETTLE_MS = 800;
constexpr uint32_t SAB_DYNAMIC_COMMAND_TIMEOUT_MS = 3000;
constexpr uint32_t SAB_TIMED_SPRAY_MAX_SECONDS = 86399;

#endif
