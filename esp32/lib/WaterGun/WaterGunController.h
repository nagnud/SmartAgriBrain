#ifndef WATER_GUN_CONTROLLER_H
#define WATER_GUN_CONTROLLER_H

#include <Arduino.h>

#include "PanTilt.h"
#include "iot_mqtt_client.h"

/**
 * 水泵硬件写入函数。
 * @param requestedPercent 协议请求百分比，0 表示关闭，非零范围为 1..100。
 * @return 实际写入 GPIO26 的百分比；标定边界保护会把 1..23 提升到 24。
 */
using PumpOutputWriter = int (*)(int requestedPercent);

/**
 * 普通水泵与水枪共用的非阻塞控制器。
 *
 * MQTT 层负责协议校验，本类负责硬件执行顺序：停泵、转舵机、等待稳定、
 * 建立定时/动态保护、开泵和异步 ACK。update() 必须在 Arduino loop 每轮调用。
 */
class WaterGunController
{
public:
  /**
   * 绑定硬件依赖并建立安全初始状态。
   * @param panTiltDriver 已完成 begin() 的二维 SG90 驱动对象。
   * @param pumpWriter 唯一允许写 GPIO26 PWM 的应用层函数。
   */
  void begin(PanTilt &panTiltDriver, PumpOutputWriter pumpWriter);

  /**
   * 处理已经通过 MQTT 校验的 pump/pan/tilt/target_position 命令。
   * @param command 命令副本；异步执行时会保存到状态机直到发布最终 ACK。
   * @param actualValue 同步完成时返回真实写入值。
   * @param errorCode 拒绝时返回稳定错误码；成功时设置为 nullptr。
   */
  IotCommandResult handleCommand(const IotCommand &command, int &actualValue, const char *&errorCode);

  /** 推进舵机稳定等待、本地定时截止和动态失联保护；loop 每轮必须调用。 */
  void update();

  /**
   * 网络断开或认证后非法水枪命令触发的最高优先级停止。
   * 会关闭 GPIO26、取消定时/动态状态，并拒绝尚未完成的异步命令。
   */
  void emergencyStop(const char *reason);

  /** 返回当前真实应用状态，供 MQTT telemetry 使用。 */
  ActuatorState snapshot(int growLightPercent) const;

private:
  enum class Stage : uint8_t
  {
    Idle,
    WaitingForServo,
  };

  PanTilt *panTilt = nullptr;
  PumpOutputWriter pumpWriter = nullptr;
  Stage stage = Stage::Idle;

  bool pendingCommandUsed = false;
  IotCommand pendingCommand;
  uint32_t servoReadyAtMs = 0;

  bool targetKnown = false;
  float currentBearingDeg = 0.0F;
  float currentRangeMm = 0.0F;

  int currentPumpPercent = 0;
  bool timedDeadlineActive = false;
  uint32_t timedDeadlineMs = 0;
  uint64_t timedEndsAtEpochMs = 0;

  bool dynamicSessionActive = false;
  String dynamicSessionId;
  uint32_t lastDynamicSequence = 0;
  uint32_t lastDynamicCommandMs = 0;

  static bool deadlineReached(uint32_t nowMs, uint32_t deadlineMs);
  static int mapBearingToPan(float bearingDeg);
  static int mapRangeToTilt(float rangeMm);
  bool targetChanged(const IotCommand &command) const;
  int writePump(int requestedPercent, const char *reason);
  void clearSprayProtection();
  void cancelPendingCommand(const char *errorCode);
  bool validateDynamicSequence(const IotCommand &command, const char *&errorCode);
  bool armTimedDeadline(const IotCommand &command, const char *&errorCode);
  IotCommandResult applyAfterServoReady(const IotCommand &command, int &actualValue, const char *&errorCode);
};

#endif
