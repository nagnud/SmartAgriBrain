#include "SoilSensor.h"



// 构造函数：初始化引脚和默认校准值
SoilSensor::SoilSensor(int pin, int dryVal, int wetVal)
{
    _pin = pin;
    _calibratedDry = dryVal; // 默认干燥值 (需根据实际校准)
    _calibratedWet = wetVal; // 默认湿润值 (需根据实际校准)
    _rawValue = 0;
    _smoothValue = 0;
    _percentage = 0.0;
    _readIndex = 0;

    // 初始化滤波数组
    for (int i = 0; i < FILTER_SIZE; i++)
    {
        _readings[i] = 0;
    }
}

void SoilSensor::begin()
{
    // 配置引脚为输入模式
    pinMode(_pin, INPUT);

    // ESP32 特有的 ADC 配置 (可选，提高精度)
    analogSetWidth(12); // 设置分辨率为12位 (0-4095)，默认即为12位
    analogSetAttenuation(ADC_11db); // 扩大量程至 0-3.3V
}

void SoilSensor::update()
{
    _rawValue = analogRead(_pin); // 原始值

    // 滑动平均滤波,减去旧值
    _smoothValue = _smoothValue - _readings[_readIndex];
    _readings[_readIndex] = _rawValue; // 存入新值
    _smoothValue = _smoothValue + _readings[_readIndex]; // 加上新值
    _readIndex = (_readIndex + 1) % FILTER_SIZE;
    int average = _smoothValue / FILTER_SIZE;

    //映射为百分比
    // 注意：电容式传感器通常是 "数值越小越湿，数值越大越干"
    if (average >= _calibratedDry)
    {
        _percentage = 0.0; // 完全干燥
    }
    else if (average <= _calibratedWet)
    {
        _percentage = 100.0; // 完全湿润
    }
    else
    {
        // 线性插值计算百分比
        _percentage = (float)(_calibratedDry - average) /
                      (float)(_calibratedDry - _calibratedWet) * 100.0;
    }
}

int SoilSensor::getRawValue()
{
    return _rawValue;
}

int SoilSensor::getSmoothedValue()
{
    return _smoothValue / FILTER_SIZE;
}

float SoilSensor::getHumidityPercent()
{
    return _percentage;
}

void readSoilMoisture(SoilSensor *soilSensor)
{

    int raw = soilSensor->getRawValue();
    int smooth = soilSensor->getSmoothedValue();
    float percent = soilSensor->getHumidityPercent();

    Serial.printf("Raw: %d | Smooth: %d | 湿度: %.1f %%\n", raw, smooth, percent);

    // if (percent < 30.0)
    // {
    //     Serial.println(">>> 提示：该浇水了！");
    // }
}
