#ifndef LED_CONTROLLER_H
#define LED_CONTROLLER_H

#include <Arduino.h>
#include <FastLED.h>
#include "SoilSensor.h"
#include "LightSensor.h"
#include "TempSensor.h"
#include "JW01_CO2.h"

// 定义硬件引脚和灯珠数量
#define LED_PIN12 12      // 连接 ESP32 的 GPIO 12
#define NUM_LEDS 60    // 灯珠数量
#define BRIGHTNESS 128 // 亮度 (0-255)
#define LED_TYPE WS2812B
#define COLOR_ORDER GRB

class LedController
{
private:
    CRGB leds[NUM_LEDS]; // FastLED 专用的颜色数组

public:
    LedController(); // 构造函数
    void begin();    // 初始化
    void update();   // 刷新显示（必须在loop中调用）

    // 示例功能函数
    void setAllColor(uint8_t r, uint8_t g, uint8_t b);
    void runRainbow(); // 彩虹效果演示
    void setBrightness(float brightness_factor);
};

void callback_led(BH1750 *bh1750, LedController *ledController, char *topic, byte *payload, unsigned int length);

#endif