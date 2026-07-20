#include "JW01_CO2.h"

// 构造函数
JW01_CO2::JW01_CO2()
{
    _co2Value = 0;
    _isDataReady = false;
    _lastReadTime = 0;
}

void JW01_CO2::begin()
{
    // 建议使用具体的引脚号 16 和 17，兼容性更好
    Serial2.begin(JW01_BAUD_RATE, SERIAL_8N1, 16, 17);

    // 保存引脚（可选）
    _rxPin = 16;
    _txPin = 17;
}

void JW01_CO2::update()
{
    // 简单的限流，防止处理过快
    if (millis() - _lastReadTime < 1000)
    {
        return;
    }

    // 检查是否有足够的数据（包头+5个数据 = 6字节）
    if (Serial2.available() >= 6)
    {
        // 1. 寻找帧头 0x2C
        // 注意：这里不能直接 read，要先 peek 或者 read 后判断
        if (Serial2.read() == 0x2C)
        {
            byte buffer[6];
            buffer[0] = 0x2C; // 手动补上帧头

            // 2. 读取剩余的 5 个字节 (B2 ~ B6)
            int bytesRead = Serial2.readBytes(&buffer[1], 5);

            if (bytesRead == 5)
            {
                // 3. 解析数据
                if (parseData(buffer))
                {
                    _lastReadTime = millis();
                    _isDataReady = true;
                }
            }
        }
        else
        {
            // 如果不是帧头，丢弃这个字节，继续下一次循环寻找
            // 这里可以加一点延时防止死循环占用过高CPU，通常不需要
        }
    }
}

// 数据解析逻辑
bool JW01_CO2::parseData(byte *buffer)
{
    // buffer 结构：
    // [0]: 0x2C (帧头)
    // [1]: CO2 High
    // [2]: CO2 Low
    // [3]: Full Scale High
    // [4]: Full Scale Low
    // [5]: Checksum

    byte checksum = buffer[0] + buffer[1] + buffer[2] + buffer[3] + buffer[4];

    if (checksum != buffer[5])
    {
        // 校验失败，数据无效
        return false;
    }

    // 2. 提取 CO2 数据,PPM = (B2 * 256) + B3,(buffer[1] << 8) | buffer[2]
    int high = buffer[1];
    int low = buffer[2];

    int concentration = (high << 8) | low;

    // 3. 合理性检查 (CO2 通常在 400-5000 之间，这里放宽一点限制)
    if (concentration > 0 && concentration < 10000)
    {
        _co2Value = concentration;
        return true;
    }

    return false;
}

int JW01_CO2::getCO2()
{
    return _co2Value;
}

bool JW01_CO2::isDataReady()
{
    if (_isDataReady)
    {
        _isDataReady = false; // 读取后重置标志
        return true;
    }
    return false;
}

// 全局打印函数
void printCO2Status(JW01_CO2 &sensor)
{
    if (sensor.isDataReady())
    {
        int co2 = sensor.getCO2();
        Serial.printf("CO2 浓度: %d ppm", co2);

        if (co2 < 800)
        {
            Serial.println(" (空气优良)");
        }
        else if (co2 < 1500)
        {
            Serial.println(" (空气一般，建议通风)");
        }
        else
        {
            Serial.println(" (空气差，请开窗！)");
        }
    }
}