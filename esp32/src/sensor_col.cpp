#include "sensor_col.h"
#include <math.h>
#include <Arduino.h>

// 滤波参数定义
#define FILTER_WINDOW_SIZE 5    // 滑动平均窗口大小
#define MAX_SENSABLE_JUMP 50.0f // 两次采样间允许的最大跳变（超过则视为干扰）

static float _filter_buffer[FILTER_WINDOW_SIZE] = {0};
static int _buffer_idx = 0;
static float _last_valid_val = 0.0f;

/**
 * @brief 生成模拟环境光干扰数据
 * @return 返回带噪声的正弦波环境光
 */
float sensor_ambient_light(unsigned long current_millis)
{
    // 将毫秒转为秒
    float t = current_millis / 1000.0f;

    // 假设基础环境光是 200，它会以 100 的幅度上下波动 (周期约 12.5 秒)
    // 真实世界里可能是缓慢飘过的云朵带来的变暗
    float ambient = 200.0f + 1000.0f * sin(t * 0.5f);
    // 2. 模拟随机极端干扰 (1% 的概率产生一个 5000 亮度的跳变噪声)
    if (random(0, 100) < 1)
    {
        ambient += 5000.0f;
    }

    return ambient;
}

/**
 * @brief 模拟物理传感器读取，集成异常值剔除与平滑滤波
 * @param ambient_light 当前环境真实亮度
 * @param current_pwm_duty 当前 LED 的 PWM 输出
 * @return 经过算法处理后的“干净”传感器数据
 */
float sensor_get_sensor_reading(float ambient_light, float current_pwm_duty)
{
    // 1. 模拟原始数据获取 (环境 + LED 贡献)
    float raw_val = ambient_light + (current_pwm_duty * 3.5f);

    // 3. 【算法：限幅滤波】
    // 如果本次读数与上次有效读数差值过大，判定为干扰，使用旧值
    if (abs(raw_val - _last_valid_val) > MAX_SENSABLE_JUMP && _last_valid_val != 0)
    {
        raw_val = _last_valid_val;
    }
    _last_valid_val = raw_val;

    // 4. 【算法：滑动平均滤波】
    // 将数据存入循环缓冲区
    _filter_buffer[_buffer_idx] = raw_val;
    _buffer_idx = (_buffer_idx + 1) % FILTER_WINDOW_SIZE;

    // 计算窗口内平均值
    float sum = 0;
    for (int i = 0; i < FILTER_WINDOW_SIZE; i++)
    {
        sum += _filter_buffer[i];
    }
    float smooth_val = sum / FILTER_WINDOW_SIZE;

    return smooth_val;
}

