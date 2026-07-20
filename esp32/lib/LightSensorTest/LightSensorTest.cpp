#include "LightSensorTest.h"

LightSensor::LightSensor(int pin)
{
    _pin = pin;
    _rawValue = 0;
    _voltage = 0.0;
    _lux = 0.0;
    _readIndex = 0;
    _total = 0;

    // 初始化滤波数组
    for (int i = 0; i < FILTER_SIZE; i++)
    {
        _readings[i] = 0;
    }
}

void LightSensor::begin()
{
    pinMode(_pin, INPUT);
    // ESP32 ADC 设置
    analogSetWidth(12);             // 12位精度 (0-4095)
    analogSetAttenuation(ADC_11db); // 设置衰减，使量程达到 0-3.3V
}

void LightSensor::update()
{
    // 1. 读取原始值
    int reading = analogRead(_pin);

    // 2. 滑动平均滤波
    _total = _total - _readings[_readIndex];
    _readings[_readIndex] = reading;
    _total = _total + _readings[_readIndex];
    _readIndex = (_readIndex + 1) % FILTER_SIZE;

    // 计算平均值
    _rawValue = _total / FILTER_SIZE;

    // 3. 转换为电压 (ESP32 参考电压通常为 3.3V)
    _voltage = (_rawValue / 4095.0) * 3.3;

    // 4. 估算 Lux
    // 注意：光敏电阻是非线性元件，且受串联电阻影响。
    // 这里使用一个简单的近似公式：Lux = (Voltage / 3.3) * 10000
    // 这里的 10000 是假设最大亮度为 10000 Lux，你可以根据环境调整系数
    _lux = (_voltage / 3.3) * 10000.0;
}

int LightSensor::getRawValue()
{
    return _rawValue;
}

float LightSensor::getVoltage()
{
    return _voltage;
}

float LightSensor::getLux()
{
    return _lux;
}

float LightSensor::getLightPercent()
{
    // 映射为百分比 (0-100%)
    // 假设 3.3V 对应 100% 亮度
    return (_voltage / 3.3) * 100.0;
}

void LightSensorTest_Print(LightSensor *lightSensor)
{

    // 打印数据
    Serial.print("原始值: ");
    Serial.print(lightSensor->getRawValue());

    Serial.print(" | 电压: ");
    Serial.print(lightSensor->getVoltage());
    Serial.print(" V");

    Serial.print(" | 估算Lux: ");
    Serial.print(lightSensor->getLux());

    Serial.print(" | 亮度: ");
    Serial.print(lightSensor->getLightPercent());
    Serial.println(" %");

}
