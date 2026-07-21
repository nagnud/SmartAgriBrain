#include <Arduino.h>

#include "JW01_CO2.h"
#include "LedController.h"
#include "LightSensor.h"
#include "PanTilt.h"
#include "SoilSensor.h"
#include "TempSensor.h"
#include "WaterGunController.h"
#include "config.h"
#include "iot_mqtt_client.h"
#include "wifi_manager.h"

// GPIO 分配来自已确认硬件接线。两个舵机使用独立 5 V 电源并与 ESP32 共地。
constexpr uint8_t LAMP_PIN = 14;
constexpr uint8_t PUMP_PIN = 26;
constexpr uint8_t PAN_SERVO_PIN = 27;
constexpr uint8_t TILT_SERVO_PIN = 13;

// ESP32 LEDC 通道不能重复。灯和泵使用 8 位 PWM，SG90 在 PanTilt 内使用 16 位 50 Hz PWM。
constexpr uint8_t LAMP_PWM_CHANNEL = 0;
constexpr uint8_t PUMP_PWM_CHANNEL = 1;
constexpr uint8_t PAN_SERVO_PWM_CHANNEL = 2;
constexpr uint8_t TILT_SERVO_PWM_CHANNEL = 3;
constexpr uint16_t LAMP_PWM_FREQUENCY_HZ = 1000;
constexpr uint8_t ACTUATOR_PWM_RESOLUTION_BITS = 8;

// 传感器对象的构造参数分别是硬件引脚、干燥 ADC 标定值和湿润 ADC 标定值。
BH1750 bh1750(0x23);                         // I2C 地址 0x23：BH1750 ADDR 引脚接 GND。
JW01_CO2 co2Sensor;                         // 驱动内部使用项目已配置的 CO2 串口。
SoilSensor soilSensor(34, 3200, 1400);      // GPIO34；3200=临时干燥值，1400=临时湿润值。
TempSensor tempSensor;                      // 驱动内部使用 GPIO4 的 DS18B20 总线。
LedController ledController;                // GPIO12 WS2812 暂时保留，不响应补光灯 MQTT。

PanTilt panTilt(PAN_SERVO_PIN, TILT_SERVO_PIN, PAN_SERVO_PWM_CHANNEL, TILT_SERVO_PWM_CHANNEL);
WaterGunController waterGunController;

uint32_t previousTelemetryMs = 0;
uint32_t lastLedBlinkMs = 0;
bool statusLedState = false;
int pumpPercent = 0;
int growLightPercent = 0;

/**
 * 把水泵百分比转换为 ESP32 LEDC 占空比。
 * @param percent 已限制在 0..100 的实际百分比；0 必须产生关闭电平。
 * @return 8 位 LEDC duty，范围 0..255。当前驱动高电平有效；常量可支持反相驱动。
 */
uint32_t pumpPercentToDuty(int percent)
{
  const uint32_t maxDuty = (1UL << ACTUATOR_PWM_RESOLUTION_BITS) - 1UL;
  const uint32_t activeDuty = (static_cast<uint32_t>(constrain(percent, 0, 100)) * maxDuty) / 100UL;
  return SAB_PUMP_ACTIVE_HIGH ? activeDuty : maxDuty - activeDuty;
}

/**
 * 普通水泵命令和水枪状态机唯一允许调用的 GPIO26 写入出口。
 * @param requestedPercent 协议请求值，0 关闭，非零范围 1..100。
 * @return 实际应用百分比。临时规则将 1..39 提升到 40，确保达到假定启动功率。
 *
 * SAB_PUMP_MIN_RUNNING_PERCENT=40 尚未经过真实水泵测量，日志始终标注 PLACEHOLDER。
 */
int applyPumpOutput(int requestedPercent)
{
  const int boundedPercent = constrain(requestedPercent, 0, SAB_PUMP_MAX_PERCENT);
  const int actualPercent = boundedPercent == 0 ? 0 : max(boundedPercent, static_cast<int>(SAB_PUMP_MIN_RUNNING_PERCENT));
  const uint32_t duty = pumpPercentToDuty(actualPercent);
  ledcWrite(PUMP_PWM_CHANNEL, duty);
  pumpPercent = actualPercent;
  Serial.printf("[PUMP][GPIO_WRITE] pin=%u requested=%d actual=%d duty=%u min_running=%u calibration=PLACEHOLDER\n",
                PUMP_PIN, requestedPercent, actualPercent, duty, SAB_PUMP_MIN_RUNNING_PERCENT);
  return actualPercent;
}

/** MQTT/WiFi 和非法水枪命令共同使用的安全回调；不能留下任何喷水定时器。 */
void emergencyStopAllActuators()
{
  waterGunController.emergencyStop("network_or_command_fail_safe");
}

/**
 * 返回 MQTT telemetry 所需的统一硬件快照。
 * 补光灯百分比来自 GPIO14 唯一状态；其余状态由 WaterGunController 统一维护。
 */
ActuatorState readActuatorState()
{
  return waterGunController.snapshot(growLightPercent);
}

/**
 * MQTT 命令进入应用层后的唯一分发入口。
 * @param command 已完成设备 ID、时间、来源、结构和值域校验的命令。
 * @param actualValue 同步命令写入真实值；异步水枪命令完成时由状态机提供。
 * @param errorCode 拒绝时返回稳定错误码；成功或 Pending 时设为 nullptr。
 */
IotCommandResult applyIotCommand(const IotCommand &command, int &actualValue, const char *&errorCode)
{
  errorCode = nullptr;

  if (command.kind == IotCommandKind::SetActuator && command.target == IotCommandTarget::GrowLight)
  {
    growLightPercent = constrain(command.value, 0, SAB_GROW_LIGHT_MAX_PERCENT);
    // grow_light 的单位是真实百分比，因此 90 映射到约 90% duty，而不是满占空比。
    const uint8_t lampDuty = static_cast<uint8_t>((growLightPercent * 255UL) / 100UL);
    ledcWrite(LAMP_PWM_CHANNEL, lampDuty);
    actualValue = growLightPercent;
    Serial.printf("[LAMP][GPIO_WRITE] pin=%u requested=%d actual=%d duty=%u\n",
                  LAMP_PIN, command.value, growLightPercent, lampDuty);
    return IotCommandResult::Executed;
  }

  // pump、pan、tilt 和 target_position 都交给同一控制器，保证停泵优先和状态一致。
  return waterGunController.handleCommand(command, actualValue, errorCode);
}

/** 初始化执行器。顺序固定为配置 PWM、绑定 GPIO、写安全关闭值、再启动舵机。 */
void initializeActuators()
{
  ledcSetup(LAMP_PWM_CHANNEL, LAMP_PWM_FREQUENCY_HZ, ACTUATOR_PWM_RESOLUTION_BITS);
  ledcSetup(PUMP_PWM_CHANNEL, SAB_PUMP_PWM_FREQUENCY_HZ, ACTUATOR_PWM_RESOLUTION_BITS);
  ledcAttachPin(LAMP_PIN, LAMP_PWM_CHANNEL);
  ledcAttachPin(PUMP_PIN, PUMP_PWM_CHANNEL);

  ledcWrite(LAMP_PWM_CHANNEL, 0);
  growLightPercent = 0;
  applyPumpOutput(0);

  panTilt.begin(90, 90);
  waterGunController.begin(panTilt, applyPumpOutput);
  Serial.println("[ACTUATOR][INIT] lamp=0 pump=0 pan=90 tilt=90 calibration=UN_CALIBRATED_PLACEHOLDER");
}

/** 初始化传感器；失败只影响对应遥测，不允许绕过执行器的安全初始状态。 */
void initializeSensors()
{
  if (bh1750.begin(CONTINUOUS_HIGH_RES))
  {
    Serial.println("[SENSOR][INIT_OK] name=BH1750 address=0x23 mode=continuous_high_res");
  }
  else
  {
    Serial.println("[SENSOR][INIT_FAIL] name=BH1750 address=0x23");
  }

  soilSensor.begin();
  tempSensor.begin();
  co2Sensor.begin();
  ledController.begin();
  Serial.println("[SENSOR][INIT_DONE] soil_gpio=34 temperature_gpio=4 co2=enabled ws2812=retained");
}

void setup()
{
  Serial.begin(115200);
  delay(1000);
  Serial.println("\n[BOOT][START] target=esp32 protocol_device_id=" SAB_DEVICE_ID " site_id=" SAB_SITE_ID);
  Serial.println("[BOOT][NOTICE] protocol name contains _s3 but physical chip and PlatformIO target are ordinary ESP32");

  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);

  // 先建立硬件安全状态和回调，再启动网络，确保启动期间收到命令也不会越过控制器。
  initializeActuators();
  initializeSensors();
  set_iot_command_handler(applyIotCommand);
  set_actuator_state_provider(readActuatorState);
  set_safety_stop_handler(emergencyStopAllActuators);

  Serial.println("[BOOT][WIFI] stage=connect_start");
  init_wifi();
  Serial.println("[BOOT][MQTT] stage=init_qos1_persistent_session");
  init_mqtt();
  Serial.println("[BOOT][READY] main_loop=network,mqtt,safety_state_machine,sensors,telemetry");
}

void loop()
{
  const uint32_t now = millis();

  // 阶段 1：网络安全。WiFi 断开先请求 MQTT/水枪安全停止，再进行重连。
  if (!is_wifi_connected())
  {
    mqtt_notify_wifi_disconnected();
    mqtt_loop(); // 立即在主循环执行停泵，不能等 WiFi 重连成功后才处理。

    if (now - lastLedBlinkMs >= 200U)
    {
      lastLedBlinkMs = now;
      statusLedState = !statusLedState;
      digitalWrite(LED_PIN, statusLedState);
    }
    init_wifi();
    return;
  }

  if (digitalRead(LED_PIN) != HIGH && now - lastLedBlinkMs > 1000U)
  {
    digitalWrite(LED_PIN, HIGH);
    statusLedState = true;
  }

  // 阶段 2：MQTT。处理连接事件、QoS 1 收包、JSON 校验和命令分发，不直接 delay。
  mqtt_loop();

  // 阶段 3：执行器安全状态机。推进 800 ms 稳定等待、定时截止和动态 3 秒超时。
  waterGunController.update();

  // 阶段 4：传感器采集。各驱动内部决定非阻塞采样周期，主循环只推进状态。
  soilSensor.update();
  co2Sensor.update();
  tempSensor.update();
  ledController.update();

  // 阶段 5：遥测。使用独立计时基准，发送传感器与统一执行器状态的 QoS 1 快照。
  if (now - previousTelemetryMs >= SEND_INTERVAL_MS)
  {
    previousTelemetryMs = now;
    Serial.printf("[TELEMETRY][SCHEDULE] interval_ms=%u\n", SEND_INTERVAL_MS);
    send_sensor_data(&soilSensor, &bh1750, &tempSensor, &co2Sensor);
  }
}
