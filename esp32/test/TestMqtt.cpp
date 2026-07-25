/*
 * 项目名称：ESP32 模块化 MQTT 工程
 * 架构说明：配置分离 + 功能模块化 + 非阻塞主循环
 * 文件：main.cpp
 */

#include <Arduino.h>
#include "config.h"       // 1. 引入配置 (包含引脚、WiFi 账号、MQTT 信息等)
#include "wifi_manager.h" // 2. 引入 WiFi 模块 (需包含 init_wifi, is_wifi_connected)
#include "iot_mqtt_client.h"  // MQTT 模块：初始化、循环维护和传感器上报接口。
#include "sensor_col.h"
#include "serial_vofa.h"
#include "LightSensor.h"
#include "Dht11Sensor.h"
#include "JW01_CO2.h"

// --- 虚拟传感器相关 ---
unsigned long lastMsgTime = 0;
unsigned long lastLedBlinkTime = 0;
bool ledState = false;

// 本测试使用与正式程序相同的传感器构造参数，确保 send_sensor_data 的接口真实可编译。
BH1750 testBh1750(0x23);
Dht11Sensor mqttTestDht11Sensor(4);
JW01_CO2 testCo2Sensor;

void setup_TestMqtt(){

    Serial.begin(115200);
    delay(1000);
    Serial.println("\n==========================================");
    Serial.println("🚀 ESP32 模块化工程启动");
    Serial.println("==========================================");

    pinMode(LED_PIN, OUTPUT); // 2. 硬件初始化
    digitalWrite(LED_PIN, LOW);
    Serial.println("[硬件] LED 引脚初始化完成");

    wave_init(); // 初始化波形(模拟数据)

    testBh1750.begin(CONTINUOUS_HIGH_RES);
    mqttTestDht11Sensor.begin();
    testCo2Sensor.begin();

    Serial.println("[系统] 正在连接 WiFi...");
    init_wifi();

    if (is_wifi_connected())
    {
        Serial.println("[系统] 正在初始化 MQTT...");
        init_mqtt();
        Serial.println("[系统]所有模块初始化完成，进入主循环...");
        digitalWrite(LED_PIN, HIGH); // 初始化成功，LED 常亮表示就绪
    }
    else
    {
        Serial.println("[系统]WiFi 连接失败，将在主循环中重试...");
    }
}


void loop_TestMqtt(){

    wave_loop();
    if (!is_wifi_connected())
    {
        mqtt_notify_wifi_disconnected();
        mqtt_loop(); // 在重连前执行网络安全事件，保持与正式主循环顺序一致。
        // 注意：如果 init_wifi 是阻塞的，这里会暂停其他逻辑。
        // 最佳实践是在 wifi_manager 中提供一个非阻塞的 wifi_loop() 或 reconnect_wifi()
        Serial.print(".");
        init_wifi();

        if (millis() - lastLedBlinkTime > 200)
        { // 重连期间，快速闪烁 LED 表示正在重试
            lastLedBlinkTime = millis();
            ledState = !ledState;
            digitalWrite(LED_PIN, ledState);
        }
        // 如果 WiFi 没连上，就不执行后面的 MQTT 逻辑，直接返回下一轮循环
        return;
    }
    else
    {
        // WiFi 已连接，确保 LED 常亮 (如果没有其他任务在占用 LED)
        if (digitalRead(LED_PIN) != HIGH && millis() - lastLedBlinkTime > 1000)
        {
            digitalWrite(LED_PIN, HIGH);
        }
    }

    mqtt_loop(); // --- 2. 维护 MQTT 连接与消息处理 ---内部已包含非阻塞重连逻辑和 callback 处理
    // update() 自行限制为至少 2 秒采样一次；每轮调用不会阻塞等待采样周期。
    mqttTestDht11Sensor.update();

    if (millis() - lastMsgTime >= SEND_INTERVAL_MS)
    {                           // 发送传感器数据
        lastMsgTime = millis(); // 更新计时器

        // 双重检查：确保 MQTT 也连接正常再发送
        // 虽然 mqtt_loop 会处理重连，但显式检查可以避免不必要的发布尝试
        // 注意：这里不直接调用 mqttClient.connected() 以避免依赖全局变量细节，
        // 依靠 send_sensor_data 内部的连接检查即可。
        Serial.println("\n[定时任务] 这是传感器的模拟数据");
        send_sensor_data(&mqttTestDht11Sensor, &testBh1750, &testCo2Sensor);
    }
}
