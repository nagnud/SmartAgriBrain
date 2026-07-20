#include <Arduino.h>
#include "serial_vofa.h"

// --- 私有变量 ---
static unsigned long _lastUpdateMillis = 0;
static float _currentPhase = 0.0f;
static float _phaseStepPerMs = 0.0f;

// JustFloat 协议固定的帧尾
const uint8_t vofa_tail[4] = {0x00, 0x00, 0x80, 0x7f};

void vofa_init(long baud_rate)
{
  Serial.begin(baud_rate);
}

void vofa_send_data(float target, float current, float pwm, float ambient)
{
  float fdata[CH_COUNT];
  fdata[0] = target;  // 通道 0: 我们设定的目标亮度
  fdata[1] = current; // 通道 1: 传感器实际读到的亮度
  fdata[2] = pwm;     // 通道 2: PID 算出来的 PWM 输出 (0-100%)
  fdata[3] = ambient; // 通道 3: 纯正的环境光 (为了观察干扰情况)

  // 发送浮点数组
  Serial.write((uint8_t *)fdata, sizeof(float) * CH_COUNT);
  // 发送帧尾
  Serial.write(vofa_tail, 4);
}

void wave_init() {
  _phaseStepPerMs = 2.0 * PI * WAVE_FREQ_HZ / 1000.0; //这里定义的是相位变化率
  _currentPhase = 0.0;
  _lastUpdateMillis = millis();
  
  Serial.println("[WaveGen] JustFloat 模式已初始化");
}

void wave_loop() {
  unsigned long currentMillis = millis();
  unsigned long deltaTime = currentMillis - _lastUpdateMillis;

  // 控制刷新率 (例如每 20ms 发送一次)
  if (deltaTime >= 20) { 
    // ✅ 1. 先利用“旧的时间差”更新相位
    // 注意：这里用的是进入函数时计算的 deltaTime，而不是更新后的时间
    _currentPhase += _phaseStepPerMs * deltaTime;
    
    // 相位保持在一个周期内 (0 ~ 2PI)
    if (_currentPhase >= TWO_PI) {
      _currentPhase -= TWO_PI;
    }

    // ✅ 2. 再更新时间戳 (为下一次循环做准备)
    // 技巧：不要直接 = currentMillis，而是 += 20，这样可以防止长期累积误差
    // 但如果网络/系统卡顿严重，直接 = currentMillis 更能保证实时性，这里用简单的 = 即可
    _lastUpdateMillis = currentMillis; 

    // 3. 计算数值
    float value = sin(_currentPhase) * WAVE_AMPLITUDE + WAVE_OFFSET;

    // 4. 构建数据
    float dataBuffer[JEB_CHANNEL_COUNT];
    dataBuffer[0] = value; 

    // 5. 发送数据
    Serial.write((uint8_t*)dataBuffer, sizeof(dataBuffer));
    Serial.write(vofa_tail, 4);
  }
}