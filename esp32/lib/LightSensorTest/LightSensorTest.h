#ifndef _LIGHT_SENSOR_TEST_H
#define _LIGHT_SENSOR_TEST_H

#include <Arduino.h>

class LightSensor
{
private:
    int _pin;       // 连接的GPIO引脚
    int _rawValue;  // 原始ADC读数 (0-4095)
    float _voltage; // 计算出的电压值
    float _lux;     // 估算的光照强度 (Lux) - 仅供参考

    // 滑动平均滤波
    static const int FILTER_SIZE = 100;//滤波窗口的大小
    int _readings[FILTER_SIZE];//数据暂存区
    int _readIndex;
    long _total;       //当前滤波窗口数据的总和

public:
    // 构造函数
    LightSensor(int pin);

    // 初始化
    void begin();

    // 读取并更新数据
    void update();

    // 获取原始ADC值 (0-4095)
    int getRawValue();

    // 获取电压值 (0.0 - 3.3V)
    float getVoltage();

    // 获取光照强度 (Lux) - 这是一个估算值
    float getLux();

    // 获取光照等级 (0-100%)，0为全黑，100为最亮
    float getLightPercent();
};

void LightSensorTest_Print(LightSensor *lightSensor);

#endif