#ifndef WIFI_MANAGER_H
#define WIFI_MANAGER_H

#include <Arduino.h>

// 初始化并连接 WiFi
void init_wifi();

// 检查 WiFi 是否连接
bool is_wifi_connected();

#endif