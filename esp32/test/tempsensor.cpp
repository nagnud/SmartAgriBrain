#include <Arduino.h>
#include "TempSensor.h"

// 实例化对象，默认使用 GPIO 4
// 如果你想用其他引脚，例如 GPIO 5，写成 TempSensor myTemp(5);
TempSensor myTemp;

void setup_TestTempSensor()
{
    Serial.begin(115200);
    Serial.println("ESP32-S3 非阻塞 DS18B20 测试");

    myTemp.begin();

    if (!myTemp.isSensorConnected())
    {
        Serial.println("未检测到 DS18B20 传感器，请检查接线！");
    }
}

void loop_TestTempSensor()
{
    // 1. 必须不断调用 update，它会自动处理时序
    myTemp.update();

    // 2. 在这里可以执行其他任务，不会被 delay(750) 卡住
    // 例如：控制LED闪烁、读取按键、处理WiFi等
    // delay(1); // 即使有微小的delay也不会影响传感器逻辑太多，但最好不用

    // 3. 打印数据 (这里为了演示方便加了一个简单的打印间隔逻辑，实际项目中可用 millis 控制)
    static unsigned long lastPrint = 0;
    if (millis() - lastPrint > 2000)
    { // 每2秒打印一次
        float temp = myTemp.getTemperature();

        Serial.print("当前温度: ");
        if (temp == DEVICE_DISCONNECTED_C)
        {
            Serial.println("读取错误");
        }
        else
        {
            Serial.print(temp);
            Serial.println(" °C");
        }

        lastPrint = millis();
    }
}