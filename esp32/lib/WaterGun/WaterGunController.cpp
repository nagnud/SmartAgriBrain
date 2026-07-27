#include "WaterGunController.h"

#include <math.h>
#include <time.h>

namespace
{
/** 把输入区间线性映射到输出区间；调用方必须先完成输入范围校验。 */
float mapLinear(float value, float inputMin, float inputMax, float outputMin, float outputMax)
{
  const float ratio = (value - inputMin) / (inputMax - inputMin);
  return outputMin + ratio * (outputMax - outputMin);
}

/** 返回可信 Unix Epoch 毫秒；SNTP 未完成时返回 0。 */
uint64_t currentEpochMs()
{
  const time_t now = time(nullptr);
  return now < 1704067200 ? 0 : static_cast<uint64_t>(now) * 1000ULL;
}
} // namespace

void WaterGunController::begin(PanTilt &panTiltDriver, PumpOutputWriter outputWriter)
{
  panTilt = &panTiltDriver;
  pumpWriter = outputWriter;
  stage = Stage::Idle;
  pendingCommandUsed = false;
  targetKnown = false;
  clearSprayProtection();
  writePump(0, "controller_begin");
  Serial.println("[WATER_GUN][INIT] calibration=UN_CALIBRATED_PLACEHOLDER state=idle pump=0");
}

bool WaterGunController::deadlineReached(uint32_t nowMs, uint32_t deadlineMs)
{
  // 转成有符号差值可正确处理 millis() 约 49.7 天回绕。
  return static_cast<int32_t>(nowMs - deadlineMs) >= 0;
}

int WaterGunController::mapBearingToPan(float bearingDeg)
{
  // Web 方向角完整覆盖左 90 度到右 90 度，并线性使用 SG90 的 0..180 度命令范围。
  // 脉宽仍由 PanTilt 的 500..2500 us 临时标定产生，实体安装方向和机械端点必须断泵验收。
  return static_cast<int>(lroundf(mapLinear(
      bearingDeg,
      SAB_PLACEHOLDER_BEARING_MIN_DEG,
      SAB_PLACEHOLDER_BEARING_MAX_DEG,
      static_cast<float>(SAB_PLACEHOLDER_PAN_MIN_DEG),
      static_cast<float>(SAB_PLACEHOLDER_PAN_MAX_DEG))));
}

int WaterGunController::mapRangeToTilt(float rangeMm)
{
  // 实体垂直机构只允许 5..60 度：60 度竖直向上，用于最近目标；5 度平行向前，
  // 用于最远目标。300..1200 mm 之间采用单段线性插值，每增加 100 mm，
  // 垂直舵机命令约降低 6.11 度。该线性关系尚未包含水压、重力和喷嘴轨迹误差。
  return static_cast<int>(lroundf(mapLinear(
      rangeMm,
      static_cast<float>(SAB_PLACEHOLDER_RANGE_MIN_MM),
      static_cast<float>(SAB_PLACEHOLDER_RANGE_MAX_MM),
      static_cast<float>(SAB_TILT_NEAR_DEG),
      static_cast<float>(SAB_TILT_FAR_DEG))));
}

bool WaterGunController::targetChanged(const IotCommand &command) const
{
  if (!targetKnown)
  {
    return true;
  }
  // 0.1 的容差只用于吸收 JSON 浮点表示误差，不会吞掉有意义的前端目标变化。
  return fabsf(command.bearingDeg - currentBearingDeg) > 0.1F ||
         fabsf(command.groundRangeMm - currentRangeMm) > 0.1F;
}

int WaterGunController::writePump(int requestedPercent, const char *reason)
{
  if (pumpWriter == nullptr)
  {
    Serial.printf("[WATER_GUN][PUMP_FAIL] reason=%s detail=no_writer\n", reason);
    currentPumpPercent = 0;
    return 0;
  }

  currentPumpPercent = pumpWriter(requestedPercent);
  Serial.printf("[WATER_GUN][PUMP_APPLY] requested=%d actual=%d reason=%s\n",
                requestedPercent, currentPumpPercent, reason);
  return currentPumpPercent;
}

void WaterGunController::clearSprayProtection()
{
  timedDeadlineActive = false;
  timedDeadlineMs = 0;
  timedEndsAtEpochMs = 0;
  dynamicSessionActive = false;
  dynamicSessionId = "";
  lastDynamicSequence = 0;
  lastDynamicCommandMs = 0;
}

void WaterGunController::cancelPendingCommand(const char *errorCode)
{
  if (!pendingCommandUsed)
  {
    return;
  }

  Serial.printf("[WATER_GUN][PENDING_CANCEL] command_id=%s code=%s\n",
                pendingCommand.commandId.c_str(), errorCode);
  mqtt_complete_command(pendingCommand, false, 0, errorCode);
  pendingCommandUsed = false;
  stage = Stage::Idle;
}

bool WaterGunController::validateDynamicSequence(const IotCommand &command, const char *&errorCode)
{
  if (command.waterGunMode != WaterGunMode::Dynamic)
  {
    return true;
  }

  if (dynamicSessionActive && command.sessionId == dynamicSessionId && command.sequence <= lastDynamicSequence)
  {
    errorCode = "STALE_TARGET";
    Serial.printf("[WATER_GUN][SEQUENCE_FAIL] session=%s received=%u last=%u code=%s\n",
                  command.sessionId.c_str(), command.sequence, lastDynamicSequence, errorCode);
    return false;
  }
  return true;
}

bool WaterGunController::armTimedDeadline(const IotCommand &command, const char *&errorCode)
{
  const uint64_t nowEpoch = currentEpochMs();
  if (nowEpoch == 0)
  {
    errorCode = "DEVICE_TIME_UNSYNCED";
    return false;
  }
  if (!command.sprayDurationPresent || !command.sprayEndsAtPresent || command.sprayEndsAt <= nowEpoch)
  {
    errorCode = "TIMED_SPRAY_EXPIRED";
    return false;
  }

  const uint64_t remainingMs64 = command.sprayEndsAt - nowEpoch;
  const uint64_t configuredMs = static_cast<uint64_t>(command.sprayDurationSeconds) * 1000ULL;
  if (remainingMs64 > configuredMs + 2000ULL || remainingMs64 > UINT32_MAX)
  {
    errorCode = "INVALID_COMMAND";
    return false;
  }

  const uint32_t remainingMs = static_cast<uint32_t>(min(remainingMs64, configuredMs));
  timedDeadlineActive = true;
  timedDeadlineMs = millis() + remainingMs;
  timedEndsAtEpochMs = command.sprayEndsAt;
  Serial.printf("[WATER_GUN][TIMER_ARM] command_id=%s duration_s=%u remaining_ms=%u ends_at=%llu\n",
                command.commandId.c_str(), command.sprayDurationSeconds, remainingMs, command.sprayEndsAt);
  return true;
}

IotCommandResult WaterGunController::applyAfterServoReady(
    const IotCommand &command, int &actualValue, const char *&errorCode)
{
  errorCode = nullptr;

  if (!command.sprayEnabled)
  {
    // 动态跟踪允许“只移动、不喷水”。此时必须保留 session_id 和最后序号，
    // 否则延迟到达的旧 MQTT 目标会因序号状态被清零而重新通过校验，驱动舵机回跳。
    timedDeadlineActive = false;
    timedDeadlineMs = 0;
    timedEndsAtEpochMs = 0;
    if (command.waterGunMode == WaterGunMode::Dynamic)
    {
      dynamicSessionActive = true;
      dynamicSessionId = command.sessionId;
      lastDynamicSequence = command.sequence;
      lastDynamicCommandMs = millis();
    }
    else
    {
      dynamicSessionActive = false;
      dynamicSessionId = "";
      lastDynamicSequence = 0;
      lastDynamicCommandMs = 0;
    }
    actualValue = writePump(0, "validated_stop_command");
    return IotCommandResult::Executed;
  }

  if (command.spraySchedule == SpraySchedule::Timed)
  {
    if (!armTimedDeadline(command, errorCode))
    {
      writePump(0, "timed_deadline_invalid");
      return IotCommandResult::Rejected;
    }
  }
  else
  {
    timedDeadlineActive = false;
    timedDeadlineMs = 0;
    timedEndsAtEpochMs = 0;
  }

  if (command.waterGunMode == WaterGunMode::Dynamic)
  {
    dynamicSessionActive = true;
    dynamicSessionId = command.sessionId;
    lastDynamicSequence = command.sequence;
    lastDynamicCommandMs = millis();
  }
  else
  {
    dynamicSessionActive = false;
    dynamicSessionId = "";
    lastDynamicSequence = 0;
    lastDynamicCommandMs = 0;
  }

  // 后端百分比来自实测分段拟合。lroundf 转为设备 PWM 整数百分比；
  // 硬件写入函数只补充 24% 非零下限保护，不改变标定有效范围内的值。
  const int roundedPercent = static_cast<int>(lroundf(command.pumpControlPercent));
  actualValue = writePump(roundedPercent, "water_gun_start_after_servo_settle");
  return IotCommandResult::Executed;
}

IotCommandResult WaterGunController::handleCommand(
    const IotCommand &command, int &actualValue, const char *&errorCode)
{
  errorCode = nullptr;

  if (command.kind == IotCommandKind::SetActuator)
  {
    errorCode = "CAPABILITY_UNSUPPORTED";
    return IotCommandResult::Rejected;
  }

  if (panTilt == nullptr || pumpWriter == nullptr)
  {
    errorCode = "INTERNAL_ERROR";
    return IotCommandResult::Rejected;
  }
  if (!validateDynamicSequence(command, errorCode))
  {
    return IotCommandResult::Rejected;
  }

  const bool changed = targetChanged(command);
  // 记录原稳定截止时间。动态保活可能在前一命令的 800 ms 稳定等待期间到达；
  // 相同目标只替换待完成命令，既不能提前开泵，也不能重复写两个舵机。
  const bool servoWasStillSettling = pendingCommandUsed && stage == Stage::WaitingForServo;
  const uint32_t existingServoReadyAtMs = servoReadyAtMs;
  if (pendingCommandUsed)
  {
    cancelPendingCommand("ACTUATOR_INTERLOCK");
  }

  if (command.waterGunMode == WaterGunMode::Dynamic)
  {
    dynamicSessionActive = true;
    dynamicSessionId = command.sessionId;
    lastDynamicSequence = command.sequence;
    lastDynamicCommandMs = millis();
  }

  if (!changed)
  {
    if (servoWasStillSettling && command.sprayEnabled)
    {
      // 保留第一次目标变化建立的稳定截止时间。最新动态命令接管最终 ACK 和开泵决策，
      // 但相同 pan/tilt 不再次调用 ledcWrite，避免舵机因保活或命令突发重复动作。
      pendingCommand = command;
      pendingCommandUsed = true;
      servoReadyAtMs = existingServoReadyAtMs;
      stage = Stage::WaitingForServo;
      Serial.printf("[WATER_GUN][TARGET_UNCHANGED_PENDING] command_id=%s sequence=%u action=keep_servo_deadline no_pwm_rewrite=1\n",
                    command.commandId.c_str(), command.sequence);
      return IotCommandResult::Pending;
    }

    // 关闭喷水命令不需要等待；取消旧待执行命令后立即维持泵关闭。
    Serial.printf("[WATER_GUN][TARGET_UNCHANGED] command_id=%s sequence=%u action=skip_servo_wait\n",
                  command.commandId.c_str(), command.sequence);
    return applyAfterServoReady(command, actualValue, errorCode);
  }

  // 目标变化时的硬安全顺序：先停泵，再写两个舵机，最后进入非阻塞稳定等待。
  writePump(0, "target_changed_before_servo_move");
  timedDeadlineActive = false;
  const int panAngle = mapBearingToPan(command.bearingDeg);
  const int tiltAngle = mapRangeToTilt(command.groundRangeMm);
  Serial.printf("[WATER_GUN][MAP_PLACEHOLDER] command_id=%s bearing=%.2f range=%.1f pan=%d tilt=%d calibration=UN_CALIBRATED_PLACEHOLDER\n",
                command.commandId.c_str(), command.bearingDeg, command.groundRangeMm, panAngle, tiltAngle);
  panTilt->setPanAngle(panAngle);
  panTilt->setTiltAngle(tiltAngle);

  currentBearingDeg = command.bearingDeg;
  currentRangeMm = command.groundRangeMm;
  targetKnown = true;
  pendingCommand = command;
  pendingCommandUsed = true;
  servoReadyAtMs = millis() + SAB_PLACEHOLDER_SERVO_SETTLE_MS;
  stage = Stage::WaitingForServo;
  Serial.printf("[WATER_GUN][SERVO_WAIT] command_id=%s wait_ms=%u pump=0\n",
                command.commandId.c_str(), SAB_PLACEHOLDER_SERVO_SETTLE_MS);
  return IotCommandResult::Pending;
}

void WaterGunController::update()
{
  const uint32_t now = millis();

  // 阶段 1：完成舵机非阻塞稳定等待，然后建立保护并决定是否开泵。
  if (stage == Stage::WaitingForServo && pendingCommandUsed && deadlineReached(now, servoReadyAtMs))
  {
    int actualValue = 0;
    const char *errorCode = nullptr;
    const IotCommand command = pendingCommand;
    pendingCommandUsed = false;
    stage = Stage::Idle;
    Serial.printf("[WATER_GUN][SERVO_READY] command_id=%s waited_ms=%u\n",
                  command.commandId.c_str(), SAB_PLACEHOLDER_SERVO_SETTLE_MS);
    const IotCommandResult result = applyAfterServoReady(command, actualValue, errorCode);
    mqtt_complete_command(command, result == IotCommandResult::Executed, actualValue, errorCode);
  }

  // 阶段 2：定时喷水必须由本地单调时钟兜底，后端停止包只作为第二重保险。
  if (timedDeadlineActive && deadlineReached(now, timedDeadlineMs))
  {
    writePump(0, "timed_complete_local_deadline");
    timedDeadlineActive = false;
    timedDeadlineMs = 0;
    timedEndsAtEpochMs = 0;
    Serial.println("[WATER_GUN][TIMED_COMPLETE] source=local_monotonic_timer pump=0");
  }

  // 阶段 3：动态模式超过 3 秒没有设备可见的新序号时安全停泵，但保留会话用于拒绝旧序号。
  if (dynamicSessionActive && currentPumpPercent > 0 && now - lastDynamicCommandMs > SAB_DYNAMIC_COMMAND_TIMEOUT_MS)
  {
    writePump(0, "dynamic_command_timeout");
    Serial.printf("[WATER_GUN][DYNAMIC_TIMEOUT] session=%s last_sequence=%u timeout_ms=%u pump=0\n",
                  dynamicSessionId.c_str(), lastDynamicSequence, SAB_DYNAMIC_COMMAND_TIMEOUT_MS);
  }
}

void WaterGunController::emergencyStop(const char *reason)
{
  cancelPendingCommand("ACTUATOR_INTERLOCK");
  writePump(0, reason == nullptr ? "emergency_stop" : reason);
  clearSprayProtection();
  stage = Stage::Idle;
  Serial.printf("[WATER_GUN][EMERGENCY_STOP] reason=%s pump=0 timers=cleared\n",
                reason == nullptr ? "unspecified" : reason);
}

ActuatorState WaterGunController::snapshot(int growLightPercent) const
{
  ActuatorState state;
  state.pumpPercent = currentPumpPercent;
  state.growLightPercent = growLightPercent;
  state.panAngleDeg = panTilt == nullptr ? 90 : panTilt->getPanAngle();
  state.tiltAngleDeg = panTilt == nullptr ? SAB_TILT_MECHANICAL_MIN_DEG : panTilt->getTiltAngle();
  state.waterGunActive = currentPumpPercent > 0;
  state.waterGunTimed = timedDeadlineActive;
  state.waterGunDynamic = dynamicSessionActive;
  state.sprayEndsAt = timedEndsAtEpochMs;
  state.waterGunSequence = lastDynamicSequence;
  return state;
}
