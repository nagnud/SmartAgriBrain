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
  // 虚拟保守标定：-45..45 deg 只使用 SG90 中间的 60..120 deg，避开机械端点。
  return static_cast<int>(lroundf(mapLinear(
      bearingDeg,
      SAB_PLACEHOLDER_BEARING_MIN_DEG,
      SAB_PLACEHOLDER_BEARING_MAX_DEG,
      static_cast<float>(SAB_PLACEHOLDER_PAN_MIN_DEG),
      static_cast<float>(SAB_PLACEHOLDER_PAN_MAX_DEG))));
}

int WaterGunController::mapRangeToTilt(float rangeMm)
{
  // 虚拟分段标定点：300->110、750->90、1200->70。它只能验证流程，不能证明命中目标。
  if (rangeMm <= SAB_PLACEHOLDER_RANGE_MID_MM)
  {
    return static_cast<int>(lroundf(mapLinear(
        rangeMm,
        static_cast<float>(SAB_PLACEHOLDER_RANGE_MIN_MM),
        static_cast<float>(SAB_PLACEHOLDER_RANGE_MID_MM),
        static_cast<float>(SAB_PLACEHOLDER_TILT_NEAR_DEG),
        static_cast<float>(SAB_PLACEHOLDER_TILT_MID_DEG))));
  }
  return static_cast<int>(lroundf(mapLinear(
      rangeMm,
      static_cast<float>(SAB_PLACEHOLDER_RANGE_MID_MM),
      static_cast<float>(SAB_PLACEHOLDER_RANGE_MAX_MM),
      static_cast<float>(SAB_PLACEHOLDER_TILT_MID_DEG),
      static_cast<float>(SAB_PLACEHOLDER_TILT_FAR_DEG))));
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
    clearSprayProtection();
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

  // 后端百分比是临时算法。lroundf 按用户确认四舍五入；硬件写入函数再应用 40% 最小值。
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
    if (command.target == IotCommandTarget::Pump)
    {
      cancelPendingCommand("ACTUATOR_INTERLOCK");
      clearSprayProtection();
      actualValue = writePump(command.value, "direct_pump_command");
      return IotCommandResult::Executed;
    }
    if (command.target == IotCommandTarget::Pan || command.target == IotCommandTarget::Tilt)
    {
      cancelPendingCommand("ACTUATOR_INTERLOCK");
      clearSprayProtection();
      writePump(0, "manual_servo_command");
      if (panTilt == nullptr)
      {
        errorCode = "INTERNAL_ERROR";
        return IotCommandResult::Rejected;
      }
      if (command.target == IotCommandTarget::Pan)
      {
        panTilt->setPanAngle(command.value);
        actualValue = panTilt->getPanAngle();
      }
      else
      {
        panTilt->setTiltAngle(command.value);
        actualValue = panTilt->getTiltAngle();
      }
      targetKnown = false; // 手动角度破坏了距离/方向映射状态，下一条水枪目标必须重新定位。
      Serial.printf("[WATER_GUN][MANUAL_SERVO] target=%s requested=%d actual=%d pump=0\n",
                    command.target == IotCommandTarget::Pan ? "pan" : "tilt", command.value, actualValue);
      return IotCommandResult::Executed;
    }
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

  // simulation_only 只验证协议，不写舵机或水泵；ACK actual_value 固定为当前真实泵输出。
  if (command.simulationOnly)
  {
    Serial.printf("[WATER_GUN][SIMULATION] command_id=%s action=no_physical_output\n", command.commandId.c_str());
    actualValue = currentPumpPercent;
    return IotCommandResult::Executed;
  }

  const bool changed = targetChanged(command);
  // 即使新命令目标相同，只要上一条命令仍处于舵机稳定等待，就不能走“目标未变化”快路径。
  // 重新开始完整等待可以防止 QoS 1 重排或前端快速更新绕过“稳定后开泵”的硬安全顺序。
  const bool servoWasStillSettling = pendingCommandUsed && stage == Stage::WaitingForServo;
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

  if (!changed && !servoWasStillSettling)
  {
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
  state.tiltAngleDeg = panTilt == nullptr ? 90 : panTilt->getTiltAngle();
  state.waterGunActive = currentPumpPercent > 0;
  state.waterGunTimed = timedDeadlineActive;
  state.waterGunDynamic = dynamicSessionActive;
  state.sprayEndsAt = timedEndsAtEpochMs;
  state.waterGunSequence = lastDynamicSequence;
  return state;
}
