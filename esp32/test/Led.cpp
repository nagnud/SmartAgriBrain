#include "LedController.h"

// 实例化对象
LedController myLeds;

void setup_Led(){
    Serial.begin(115200);
    Serial.println("Starting LED System...");

    // 初始化 LED 控制器
    myLeds.begin();
}


void loop_Led(){
    // 1. 先测试纯色
    Serial.println("Setting Red...");
    myLeds.setAllColor(255, 0, 0);
    delay(1000);

    Serial.println("Setting Green...");
    myLeds.setAllColor(0, 255, 0);
    delay(1000);

    // 2. 运行彩虹效果 (注意：这个函数内部自带延时)
    Serial.println("Running Rainbow...");
    for (int i = 0; i < 50; i++)
    {
        myLeds.runRainbow();
    }
}
