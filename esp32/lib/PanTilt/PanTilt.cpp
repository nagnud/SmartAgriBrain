#include "PanTilt.h"

PanTilt::PanTilt(uint8_t panPin, uint8_t tiltPin, uint8_t panChannel, uint8_t tiltChannel)
    : panPin(panPin),
      tiltPin(tiltPin),
      panChannel(panChannel),
      tiltChannel(tiltChannel),
      panAngle(90),
      tiltAngle(SAB_TILT_MECHANICAL_MIN_DEG)
{
}

void PanTilt::begin(int panInitialAngle, int tiltInitialAngle)
{
    ledcSetup(panChannel, SERVO_FREQUENCY_HZ, SERVO_PWM_RESOLUTION_BITS);
    ledcSetup(tiltChannel, SERVO_FREQUENCY_HZ, SERVO_PWM_RESOLUTION_BITS);
    ledcAttachPin(panPin, panChannel);
    ledcAttachPin(tiltPin, tiltChannel);

    setPanAngle(panInitialAngle);
    setTiltAngle(tiltInitialAngle);
}

void PanTilt::setPanAngle(int angle)
{
    const int safeAngle = clampPanAngle(angle);
    if (safeAngle != angle)
    {
        Serial.printf("[SERVO][CLAMP] axis=pan requested=%d applied=%d allowed=%d..%d\n",
                      angle, safeAngle, SAB_PAN_MECHANICAL_MIN_DEG, SAB_PAN_MECHANICAL_MAX_DEG);
    }
    panAngle = safeAngle;
    writeAngle(panChannel, panAngle);
}

void PanTilt::setTiltAngle(int angle)
{
    const int safeAngle = clampTiltAngle(angle);
    if (safeAngle != angle)
    {
        Serial.printf("[SERVO][CLAMP] axis=tilt requested=%d applied=%d allowed=%d..%d\n",
                      angle, safeAngle, SAB_TILT_MECHANICAL_MIN_DEG, SAB_TILT_MECHANICAL_MAX_DEG);
    }
    tiltAngle = safeAngle;
    writeAngle(tiltChannel, tiltAngle);
}

int PanTilt::getPanAngle() const
{
    return panAngle;
}

int PanTilt::getTiltAngle() const
{
    return tiltAngle;
}

int PanTilt::clampPanAngle(int angle)
{
    return constrain(angle, SAB_PAN_MECHANICAL_MIN_DEG, SAB_PAN_MECHANICAL_MAX_DEG);
}

int PanTilt::clampTiltAngle(int angle)
{
    return constrain(angle, SAB_TILT_MECHANICAL_MIN_DEG, SAB_TILT_MECHANICAL_MAX_DEG);
}

int PanTilt::clampPwmAngle(int angle)
{
    return constrain(angle, PWM_ANGLE_MIN_DEG, PWM_ANGLE_MAX_DEG);
}

uint32_t PanTilt::angleToDuty(int angle)
{
    const int clampedAngle = clampPwmAngle(angle);
    // 机械限位由 setPanAngle/setTiltAngle 分轴完成；这里再限制 SG90 的 PWM 换算区间，
    // 保证任何内部调用都不能生成 0..180 度命令范围之外的脉宽。
    const int pulseUs = constrain(
        map(clampedAngle, PWM_ANGLE_MIN_DEG, PWM_ANGLE_MAX_DEG, SERVO_MIN_PULSE_US, SERVO_MAX_PULSE_US),
        SERVO_MIN_PULSE_US,
        SERVO_MAX_PULSE_US);
    const uint32_t maxDuty = (1UL << SERVO_PWM_RESOLUTION_BITS) - 1;
    return (static_cast<uint32_t>(pulseUs) * maxDuty) / SERVO_PERIOD_US;
}

void PanTilt::writeAngle(uint8_t channel, int angle)
{
    ledcWrite(channel, angleToDuty(angle));
}
