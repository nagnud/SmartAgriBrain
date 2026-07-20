#ifndef _SOIL_SENSOR_H
#define _SOIL_SENSOR_H

#include <Arduino.h>

class SoilSensor
{
private:
    int _pin;          // 连接的GPIO引脚
    int _rawValue;     // 原始ADC读数 (0-4095)
    int _smoothValue;  // 平滑后的ADC读数
    float _percentage; // 计算出的湿度百分比 (0.0 - 100.0)

    // 校准参数 (根据实际传感器调整)
    int _calibratedDry; // 空气中读数 (干燥)
    int _calibratedWet; // 水中读数 (湿润)

    // 滑动平均滤波窗口大小
    static const int FILTER_SIZE = 10;
    int _readings[FILTER_SIZE];
    int _readIndex;

public:
    // 构造函数
    SoilSensor(int pin, int dryVal = 3200, int wetVal = 1400);

    // 初始化
    void begin();

    // 读取并更新数据
    void update();

    // 获取原始ADC值 (0-4095)
    int getRawValue();

    // 获取平滑后的ADC值
    int getSmoothedValue();
    // 获取湿度百分比 (0.0 - 100.0%)
    float getHumidityPercent();
};

extern SoilSensor soilSensor;

void readSoilMoisture(SoilSensor *soilSensor);

#endif