#include <Arduino.h>
#include "config.h"       // 引入配置 (包含引脚、WiFi 账号、MQTT 信息等)
#include "wifi_manager.h" 
#include "mqtt_client.h"  
#include "sensor_col.h"
#include "serial_vofa.h"
#include "LedController.h"
#include "LightSensorTest.h"
#include "LightSensor.h"
#include "TempSensor.h"
#include "SoilSensor.h"
#include "JW01_CO2.h"
//#include "pump.h"

#define HEATER_PIN 14
#define PUMP_PIN 26
#define HEATER_PWM_CHANNEL 0
#define PUMP_PWM_CHANNEL 1

#define PWM_FREQ 1000 // PWM频率 1000Hz
#define PWM_RES 8     // 8位分辨率，占空比范围0~255

LightSensor lightSensor(34); 
// 使用 GPIO 34 (支持ADC) 这是光传感器测试
BH1750 bh1750(0x23);
// 定义光传感器对象 (假设 ADDR 接 GND, 地址为 0x23)，如果 ADDR 接 VCC，请改为 0x5C
JW01_CO2 co2Sensor;
SoilSensor soilSensor(34, 3200, 1400);
TempSensor tempSensor; //gpio4

//WaterPump myPump(26, 1);// 定义水泵对象，使用 GPIO 26，LEDC 通道 0
LedController ledController2;// 定义 LED 控制器对象

unsigned long previousMillis = 0;
const long interval = 10000; // 间隔 1000ms
unsigned long lastLedBlinkTime = 0;

bool ledState = false;

void applySmartControl(const SmartControlCommand &command)
{
   ledcWrite(PUMP_PWM_CHANNEL, command.waterPwm);
   ledcWrite(HEATER_PWM_CHANNEL, command.heaterPwm);

   ledController2.setBrightness(1.0f);
   ledController2.setAllColor(command.lightPwm, command.lightPwm, command.lightPwm);
   ledController2.update();

   Serial.printf("[CONTROL] Applied pump=%d light=%d heater=%d\n",
                 command.waterPwm, command.lightPwm, command.heaterPwm);
}

void setup()
{
   Serial.begin(115200);
   delay(1000);
   Serial.println("\n==========================================");
   Serial.println("ESP32 模块化工程启动");
   Serial.println("==========================================");

   pinMode(LED_PIN, OUTPUT); // 2. 硬件初始化
   digitalWrite(LED_PIN, LOW);
   Serial.println("[硬件] LED 引脚初始化完成");

   //myPump.begin();
   Serial.println("系统启动完成");

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



   lightSensor.begin();//这是光敏传感器测试初始化
   Serial.println("✅ 光敏测试传感器 初始化成功！");

   //Serial.println("正在初始化 BH1750...");
   // 调用 begin，传入模式，这里用连续测量，分辨率 1 Lux，测量时间约 120ms
   if (bh1750.begin(CONTINUOUS_HIGH_RES))
   {
      Serial.println("✅ BH1750 初始化成功！");
   }
   else
   {
      Serial.println("❌ BH1750 初始化失败");
   }

   //Serial.println("✅ 土壤湿度传感器 初始化成功！");
   soilSensor.begin();
   tempSensor.begin();
   Serial.println("[System] DS18B20 init done");
   Serial.println("✅ 土壤湿度传感器 初始化成功！");
   //Serial.println("--------------------------------");

   co2Sensor.begin();
   Serial.println("✅ JW01 CO2 传感器初始化成功！");

   ledController2.begin();
   Serial.println("✅ LED 灯初始化成功！");

   // pinMode(26, OUTPUT);
   // digitalWrite(26, HIGH);
   // pinMode(14, OUTPUT);
   // digitalWrite(14, HIGH);
   ledcSetup(HEATER_PWM_CHANNEL, PWM_FREQ, PWM_RES);
   ledcSetup(PUMP_PWM_CHANNEL, PWM_FREQ, PWM_RES);

   ledcAttachPin(HEATER_PIN, HEATER_PWM_CHANNEL);
   ledcAttachPin(PUMP_PIN, PUMP_PWM_CHANNEL);
   

   ledcWrite(HEATER_PWM_CHANNEL, 0);
   ledcWrite(PUMP_PWM_CHANNEL, 0);
   set_smart_control_handler(applySmartControl);
}

 void loop() {
    unsigned long currentMillis = millis();

    if (!is_wifi_connected())
    {
       // 注意：如果 init_wifi 是阻塞的，这里会暂停其他逻辑。
       Serial.print(".");
       init_wifi();

       if (millis() - previousMillis > 200)
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


    mqtt_loop(); //维护 MQTT 连接与消息处理


    lightSensor.update(); //这是光敏传感器测试更新数据
    soilSensor.update();//更新土壤湿度传感器数据
    co2Sensor.update();//更新 CO2 传感器数据

    //ledController2.update(); // 刷新 LED 显示，保持状态

    tempSensor.update();

    if (millis() - previousMillis >= SEND_INTERVAL_MS)
    {                          // 发送传感器数据
       previousMillis = millis(); // 更新计时器

       // 双重检查：确保 MQTT 也连接正常再发送
       // 虽然 mqtt_loop 会处理重连，但显式检查可以避免不必要的发布尝试
       // 注意：这里不直接调用 mqttClient.connected() 以避免依赖全局变量细节，
       // 依靠 send_sensor_data 内部的连接检查即可。
       Serial.println("\n[定时任务] 这是传感器的数据");
       send_sensor_data(&soilSensor, &bh1750, &tempSensor, &co2Sensor);
    }


    //这里是串口打印传感器数据测试
    if (currentMillis - previousMillis >= interval)
    {
       //previousMillis = currentMillis;
       //LightSensorTest_Print(&lightSensor);//这是光照传感器测试
       //printBH1750Data(&bh1750); // 打印 BH1750 传感器数据
       //readSoilMoisture(&soilSensor);//打印土壤湿度传感器数据
       //printCO2Status(co2Sensor);
    }

    ledController2.update();
    //callback_led(&bh1750, &ledController2, char *topic, byte *payload, unsigned int length);
   //  if (strcmp(topic, TOPIC_CONTROL) == 0)
   //  {
   //     callback_led(&bh1750, &ledController2, topic, payload, length);
   //  }
    
   // myPump.setSpeed(80);
 } 

