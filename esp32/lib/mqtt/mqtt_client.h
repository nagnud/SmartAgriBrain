#ifndef MQTT_CLIENT_H
#define MQTT_CLIENT_H

#include <Arduino.h>
#include <WiFi.h>          // ESP8266/ESP32 WiFi 库
#include <PubSubClient.h>  // MQTT 客户端库
#include "config.h"       // 包含配置文件 (WiFi 和 MQTT 设置)
#include "LightSensor.h"
#include "SoilSensor.h"
#include "TempSensor.h"
#include "JW01_CO2.h"
#include <WiFiClientSecure.h> //确保引入安全客户端库
// ==========================================
// ⚙️ 配置宏定义 (如果 config.h 里没写，可以在这里备用)
// ==========================================
// 注意：通常建议将这些具体的字符串放在 config.h 中，
// 这里只保留函数声明和全局对象引用，以保持解耦。
// 如果编译报错说找不到 MQTT_SERVER 等，请检查是否包含了 config.h

// ==========================================
// 🌍 全局对象声明 (extern)
// ==========================================
// 告诉编译器这些变量在别的文件(.cpp)里定义了，这里只是引用
extern WiFiClientSecure espClient;
extern PubSubClient mqttClient;

struct SmartControlCommand
{
  bool hasWaterDemand;
  bool hasLightDemand;
  bool hasPanAngle;
  bool hasTiltAngle;
  bool hasLegacyTempDemand;
  int waterDemand;
  int lightDemand;
  int panAngle;
  int tiltAngle;
  int legacyTempDemand;
  int waterPwm;
};

typedef void (*SmartControlHandler)(const SmartControlCommand &command);

// ==========================================
// 🚀 公共函数声明
// ==========================================

/**
 * @brief 初始化 MQTT 模块
 * 设置服务器地址、端口、回调函数和缓冲区大小
 * 应在 setup() 中调用一次
 */
void init_mqtt();

void set_smart_control_handler(SmartControlHandler handler);

/**
 * @brief MQTT 主循环处理函数
 * 负责维持连接、非阻塞重连、处理消息队列
 * 必须在 loop() 中频繁调用
 */
void mqtt_loop();

/**
 * @brief 发送传感器数据
 * 生成随机温湿度数据并发布到 TOPIC_SENSOR
 * 发送成功后会自动触发自我测试
 */
void send_sensor_data(SoilSensor *soilSensor, BH1750 *bh1750, TempSensor *tempSensor, JW01_CO2 *co2Sensor);

/**
 * @brief 触发自我测试
 * 向控制主题发布 "LED_BLINK" 指令
 */
void trigger_self_test();

/**
 * @brief LED 闪烁辅助函数
 * @param times 闪烁次数
 * @param speed 每次闪烁的间隔时间 (毫秒)
 * 
 * 注意：这是一个阻塞函数，仅在本地逻辑或安全上下文中调用
 */
void blink_led_local(int times, int speed);

// ==========================================
// 📝 消息回调函数声明
// ==========================================
// 虽然 callback 通常作为函数指针传给 setCallback，
// 但在这里声明一下有助于代码阅读和调试
void callback(char* topic, byte* payload, unsigned int length);

#endif // MQTT_CLIENT_H
