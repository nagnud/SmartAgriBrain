#ifndef PAN_TILT_H
#define PAN_TILT_H

#include <Arduino.h>

class PanTilt
{
public:
    PanTilt(uint8_t panPin, uint8_t tiltPin, uint8_t panChannel, uint8_t tiltChannel);

    void begin(int panInitialAngle = 90, int tiltInitialAngle = 90);
    void setPanAngle(int angle);
    void setTiltAngle(int angle);

    int getPanAngle() const;
    int getTiltAngle() const;

private:
    static constexpr uint32_t SERVO_FREQUENCY_HZ = 50;
    static constexpr uint8_t SERVO_PWM_RESOLUTION_BITS = 16;
    static constexpr int SERVO_PERIOD_US = 20000;
    static constexpr int SERVO_MIN_PULSE_US = 500;
    static constexpr int SERVO_MAX_PULSE_US = 2500;
    static constexpr int MIN_ANGLE_DEG = 0;
    static constexpr int MAX_ANGLE_DEG = 180;

    uint8_t panPin;
    uint8_t tiltPin;
    uint8_t panChannel;
    uint8_t tiltChannel;
    int panAngle;
    int tiltAngle;

    static int clampAngle(int angle);
    static uint32_t angleToDuty(int angle);
    void writeAngle(uint8_t channel, int angle);
};

#endif
