#include "PidLed.h"
#include <Arduino.h>

static float _kp, _ki, _kd;
static float _out_min, _out_max;
static float _integral = 0.0f; // 积分项累积值
static float _prev_error = 0.0f; // 上一次误差
static float _prev_derivative = 0.0f; // 上一次微分项，用来计算D

/**
 * @brief 初始化 PID 控制器
 * @param kp 比例系数，决定响应速度
 * @param ki 积分系数，消除静差
 * @param kd 微分系数，抑制震荡
 * @param out_min 输出最小值 (如 PWM 0)
 * @param out_max 输出最大值 (如 PWM 1023 或 100)
 */
void pid_init(float kp, float ki, float kd, float out_min, float out_max)
{
    _kp = kp;
    _ki = ki;
    _kd = kd;
    _out_min = out_min;
    _out_max = out_max;
    _integral = 0.0f;
    _prev_error = 0.0f;
    _prev_derivative = 0.0f;
}

/**
 * @brief 改进型 PID 计算函数
 * @param setpoint 目标设定值
 * @param measured_value 当前传感器测量值
 * @param dt 时间间隔（秒）
 * @return 限制在 [_out_min, _out_max] 之间的控制输出
 */
float pid_compute(float setpoint, float measured_value, float dt)
{
    if (dt <= 0.0f)
        return 0.0f;

    float error = setpoint - measured_value;

    //积分项计算 (带抗饱和逻辑)
    _integral += error * dt;

    // 微分项计算 (带低通滤波)，对微分结果做平滑处理
    float raw_derivative = (error - _prev_error) / dt;
    float filtered_derivative = _prev_derivative + 0.3f * (raw_derivative - _prev_derivative);
    _prev_derivative = filtered_derivative;

    //计算原始 PID 输出
    float output = (_kp * error) + (_ki * _integral) + (_kd * filtered_derivative);

    //动态抗积分饱和
    if (output > _out_max)
    {
        // 如果输出过大，扣除多余部分的积分贡献
        _integral -= (output - _out_max) / _kp;
        output = _out_max;
    }
    else if (output < _out_min)
    {
        _integral -= (output - _out_min) / _kp;
        output = _out_min;
    }

    _prev_error = error;
    return output;
}