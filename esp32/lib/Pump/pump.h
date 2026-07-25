#ifndef WATER_PUMP_H
#define WATER_PUMP_H

#include "Arduino.h"
#include "driver/ledc.h"


class WaterPump
{
private:
    uint8_t _pin;         // 引脚号
    uint8_t _channel;     // LEDC 通道
    uint32_t _freq;       // PWM 频率
    uint8_t _resolution;  // 分辨率
    int32_t _targetSpeed; // 当前设定的占空比 (0-255)

public:
    WaterPump(uint8_t pin, uint8_t channel, uint32_t freq = 5000, uint8_t resolution = 8);
    void begin();

    //直接设置 PWM 占空比 (0-255)
    void setSpeed(int speed);

    void stop();

    void rampTo(int speed, int step);

    // 获取当前设定的占空比
    int getCurrentSpeed();

};

void callback_pump(WaterPump *waterPump, char *topic, byte *payload, unsigned int length);

#endif
