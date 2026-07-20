#ifndef SERIAL_VOFA_H
#define SERIAL_VOFA_H

#include <Arduino.h>

// --- 配置参数 ---
#define WAVE_FREQ_HZ      1.0f    // 正弦波频率
#define WAVE_AMPLITUDE    50.0f   // 振幅
#define WAVE_OFFSET       50.0f   // 偏移量
#define JEB_CHANNEL_COUNT 1       // 我们只发 1 个通道 (ch1)

#define CH_COUNT 4

// --- 函数声明 ---
void wave_init();
void wave_loop();

void vofa_init(long baud_rate);
void vofa_send_data(float target, float current, float pwm, float ambient); // 发送一帧数据

#endif
