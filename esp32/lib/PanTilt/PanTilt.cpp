#include "PanTilt.h"

PanTilt::PanTilt(uint8_t panPin, uint8_t tiltPin, uint8_t panChannel, uint8_t tiltChannel)
    : panPin(panPin), tiltPin(tiltPin), panChannel(panChannel), tiltChannel(tiltChannel), panAngle(90), tiltAngle(90)
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
    panAngle = clampAngle(angle);
    writeAngle(panChannel, panAngle);
}

void PanTilt::setTiltAngle(int angle)
{
    tiltAngle = clampAngle(angle);
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

int PanTilt::clampAngle(int angle)
{
    return constrain(angle, MIN_ANGLE_DEG, MAX_ANGLE_DEG);
}

uint32_t PanTilt::angleToDuty(int angle)
{
    const int clampedAngle = clampAngle(angle);
    const int pulseUs = map(clampedAngle, MIN_ANGLE_DEG, MAX_ANGLE_DEG, SERVO_MIN_PULSE_US, SERVO_MAX_PULSE_US);
    const uint32_t maxDuty = (1UL << SERVO_PWM_RESOLUTION_BITS) - 1;
    return (static_cast<uint32_t>(pulseUs) * maxDuty) / SERVO_PERIOD_US;
}

void PanTilt::writeAngle(uint8_t channel, int angle)
{
    ledcWrite(channel, angleToDuty(angle));
}
