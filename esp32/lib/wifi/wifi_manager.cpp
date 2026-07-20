#include "wifi_manager.h"
#include <WiFi.h>
#include "config.h" // 引入配置

void init_wifi() {
  Serial.print("\n[WiFi] 正在连接至: ");
  Serial.println(WIFI_SSID);
  
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  
  // 连接过程中指示灯快闪
  for(int i=0; i<10; i++){
      digitalWrite(LED_PIN, HIGH);
      delay(100);
      digitalWrite(LED_PIN, LOW);
      delay(100);
  }

  int timeout = 0;
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
    timeout++;
    if(timeout > 40) { // 20秒超时
      Serial.println("\n[WiFi] ❌ 连接超时!");
      return;
    }
  }

  Serial.println("\n[WiFi] ✅ 连接成功!");
  Serial.print("[WiFi] IP 地址: ");
  Serial.println(WiFi.localIP());
}

bool is_wifi_connected() {
  return (WiFi.status() == WL_CONNECTED);
}