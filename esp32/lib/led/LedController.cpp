#include "LedController.h"
#include <ArduinoJson.h>
#include "LightSensor.h"

//BH1750 bh1750;
//unsigned long currentMillis = millis();
//unsigned long previousMillis = 0;
// 构造函数
LedController::LedController()
{
    // 可以在这里做变量初始化
}

// 初始化
void LedController::begin()
{
    // 告诉 FastLED 硬件配置
    FastLED.addLeds<LED_TYPE, LED_PIN12, COLOR_ORDER>(leds, NUM_LEDS).setCorrection(TypicalLEDStrip);
    FastLED.setBrightness(BRIGHTNESS);

    // 初始全灭
    FastLED.clear();
    FastLED.show();
}

// 刷新显示
// 注意：FastLED 需要不断调用 show() 或 delay() 来维持信号
void LedController::update()
{
    FastLED.show();
}

//设置所有灯为同一个颜色
void LedController::setAllColor(uint8_t r, uint8_t g, uint8_t b)
{
    for (int i = 0; i < NUM_LEDS; i++)
    {
        leds[i] = CRGB(r, g, b);
    }
    FastLED.show();
}

//简单的彩虹循环
void LedController::runRainbow()
{
    // 这是一个阻塞式的演示，实际项目中建议用非阻塞计时器
    uint8_t hue = 0;
    for (int i = 0; i < NUM_LEDS; i++)
    {
        // 根据位置设置不同色相
        leds[i] = CHSV(hue + (i * 10), 255, 255);
    }
    FastLED.show();
    FastLED.delay(10); // 短暂延时产生动画效果
    hue++;
}

//全局亮度控制
void LedController::setBrightness(float brightness_factor)
{
    // 限制范围：0.0 (灭) 到 1.0 (最亮)
    if (brightness_factor < 0.0)
        brightness_factor = 0.0;
    if (brightness_factor > 1.0)
        brightness_factor = 1.0;

    // 告诉 FastLED 库当前的整体亮度百分比
    // FastLED 内部会处理这个缩放，非常方便
    FastLED.setBrightness(brightness_factor * 255);
}


    /**
     * @brief LED 控制回调函数
     * @param topic 订阅主题
     * @param payload 原始数据
     * @param length 数据长度
     *
     * 注意：extern float target_value;PID 目标值；extern uint32_t current_color;
     * 示例：
     * {
      "cmd": "set",
      "target": 128,
      "color": [255, 0, 0],
      "mode": "breath"
    }
     */

void callback_led(BH1750 *bh1750, LedController *ledController, char *topic, byte *payload, unsigned int length)
{
    int target_value = 0;
    ledController->update();   // 刷新显示，保持 LED 状态
    // 1. 创建 JSON 文档对象,这里的 128字节 是内存容量，根据JSON 大小调整
    JsonDocument doc;
    // 2. 反序列化（解析 JSON）
    DeserializationError error = deserializeJson(doc, payload, length);
    if (error)
    {
        Serial.print("❌ JSON 解析失败: ");
        Serial.println(error.f_str());
        return;
    }


    if (doc["target"].is<int>())
    {
        int new_target = doc["target"];
        if (new_target >= 0 && new_target <= 255)
        {
            target_value = new_target; // 更新全局 PID 目标值
            //Serial.printf("PID目标更新: %d\n", target_value);
        }
    }

    // Directly apply the target brightness value from the control command.
    ledController->setBrightness(target_value / 255.0f);


    if (doc["color"][0].is<int>() && doc["color"][1].is<int>() && doc["color"][2].is<int>())
    {
        // 获取数组中的 R, G, B
        int r = doc["color"][0];
        int g = doc["color"][1];
        int b = doc["color"][2];
// 更新 LED 颜色
        ledController->setAllColor(r, g, b);
    }

    

    // --- 解析模式 ---
    const char *mode_str = doc["mode"];
    if (mode_str)
    {
        if (strcmp(mode_str, "breath") == 0)
        {
            //Serial.println("✅ 切换到呼吸模式");
            // 设置全局标志位: led_mode = MODE_BREATH;
        }
        else if (strcmp(mode_str, "solid") == 0)
        {
            //Serial.println("✅ 切换到常亮模式");
            // 设置全局标志位: led_mode = MODE_SOLID;
        }
    }
}
