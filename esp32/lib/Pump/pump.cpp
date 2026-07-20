#include "SoilSensor.h"
#include "pump.h"
#include <ArduinoJson.h>

WaterPump::WaterPump(uint8_t pin, uint8_t channel, uint32_t freq, uint8_t resolution)
{
    _pin = pin;
    _channel = channel;
    _freq = freq;
    _resolution = resolution;
    _targetSpeed = 0; // 只有目标值，没有实际转速反馈
}

void WaterPump::begin()
{
    ledcSetup(_channel, _freq, _resolution);
    ledcAttachPin(_pin, _channel);
    ledcWrite(_channel, 0); // 初始关闭
    //Serial.printf("水泵初始化完成 -> 引脚:%d\n", _pin);
}

// 核心控制函数：直接输出 PWM
void WaterPump::setSpeed(int speed)
{
    // 限幅保护
    if (speed > 220)
        speed = 220;
    if (speed < 0)
        speed = 0;

    _targetSpeed = speed;

    // 【关键修复】：直接在这里输出 PWM 信号
    // PID 算出多少，这里就输出多少，不要任何延迟或平滑
    ledcWrite(_channel, speed);
}

void WaterPump::stop()
{
    setSpeed(0);
}

void WaterPump::rampTo(int speed, int step)
{
    setSpeed(speed);
}

int WaterPump::getCurrentSpeed()
{
    // 返回的设定的占空比
    return _targetSpeed;
}

/**
     * @brief 水泵 控制回调函数
     * @param topic 订阅主题
     * @param payload 原始数据
     * @param length 数据长度
     *
     * 注意：
     * 示例：
     * {
      "cmd": "set",
      "target": 128,
      "mode": "breath"
    }
     */

void callback_pump(SoilSensor *soilSensor, WaterPump *waterPump, char *topic, byte *payload, unsigned int length)
{
    int target_value = 0;
    // 1. 创建 JSON 文档对象,这里的 128字节 是内存容量，根据JSON 大小调整
    JsonDocument doc;
    // 2. 反序列化（解析 JSON）
    DeserializationError error = deserializeJson(doc, payload, length);
    if (error)
    {
        Serial.print("❌ 水泵JSON 解析失败: ");
        Serial.println(error.f_str());
        return;
    }

    if (doc["target"].is<int>())
    {
        int new_target = doc["target"];
        if (new_target >= 0 && new_target <= 255)
        {
            target_value = new_target; // 更新全局 PID 目标值
            // Serial.printf("PID目标更新: %d\n", target_value);
        }
    }

    // Directly apply the target PWM value from the control command.
    waterPump->setSpeed(target_value);

    // --- 解析模式 ---
    const char *mode_str = doc["mode"];
    if (mode_str)
    {
        if (strcmp(mode_str, "breath") == 0)
        {
            // Serial.println("✅ 切换到呼吸模式");
            //  设置全局标志位: led_mode = MODE_BREATH;
        }
        else if (strcmp(mode_str, "solid") == 0)
        {
            // Serial.println("✅ 切换到常亮模式");
            //  设置全局标志位: led_mode = MODE_SOLID;
        }
    }
}
