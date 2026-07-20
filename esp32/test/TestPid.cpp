 #include <Arduino.h>
 #include "serial_vofa.h"
 #include "pid_ctrl.h"
 #include "sensor_col.h"

// 定时控制变量
static unsigned long last_update_time = 0;
const unsigned long SAMPLE_TIME_MS = 20; // 控制周期 20ms (50Hz)

// 系统变量
const float TARGET_LIGHT_LEVEL = 450.0f; // 设定的目标亮度
float current_pwm_duty = 0.0f;           // 当前的 PWM 输出 (0.0 - 100.0)

void setup() {
    // 1. 初始化串口 (连接 VOFA+)
    vofa_init(115200);

    // 2. 初始化 PID 参数
    pid_init(0.8f, 0.5f, 0.05f, 0.0f, 100.0f);

    last_update_time = millis();
}

void loop() {
    unsigned long current_time = millis();
    unsigned long dt_ms = current_time - last_update_time;

    // 非阻塞定时控制 (20ms 运行一次控制算法)
    if (dt_ms >= SAMPLE_TIME_MS) {
        float dt = dt_ms / 1000.0f; // 换算成秒给 PID 使用
        last_update_time = current_time;

        // ---------- 核心控制闭环 ----------

        // 1. 模拟环境光线数据
        float ambient = sensor_ambient_light(current_time);

        // 2. 读取虚拟传感器 (外界环境光 + 当前LED发出的光)
        float sensor_val = sensor_get_sensor_reading(ambient, current_pwm_duty);

        // 3. PID 计算！根据误差算出新的 PWM
        current_pwm_duty = pid_compute(TARGET_LIGHT_LEVEL, sensor_val, dt);

        // 4. 发送数据到 VOFA+ 进行绘图观察
        vofa_send_data(TARGET_LIGHT_LEVEL, sensor_val, current_pwm_duty, ambient);
    }
}