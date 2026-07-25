#ifndef PAN_TILT_H
#define PAN_TILT_H

#include <Arduino.h>
#include "iot_contract.h"

class PanTilt
{
public:
    /**
     * 创建二维 SG90 驱动。
     * @param panPin 水平轴信号 GPIO，当前接 GPIO27。
     * @param tiltPin 俯仰轴信号 GPIO，当前接 GPIO13。
     * @param panChannel 水平轴 ESP32 LEDC 通道，当前为 2。
     * @param tiltChannel 俯仰轴 ESP32 LEDC 通道，当前为 3。
     */
    PanTilt(uint8_t panPin, uint8_t tiltPin, uint8_t panChannel, uint8_t tiltChannel);

    /**
     * 初始化 50 Hz PWM 并写入两个初始角度。
     * @param panInitialAngle 水平轴初始命令角度，单位 deg，范围 0..180。
     * @param tiltInitialAngle 俯仰轴初始命令角度，单位 deg，实体安全范围 5..60。
     */
    void begin(int panInitialAngle = 90, int tiltInitialAngle = SAB_TILT_MECHANICAL_MIN_DEG);

    /** 设置水平轴命令角度；底层强制限制在 0..180，不改变现有水平控制关系。 */
    void setPanAngle(int angle);

    /** 设置俯仰轴命令角度；底层强制限制在实体机构确认的 5..60 度安全范围。 */
    void setTiltAngle(int angle);

    /** 返回最近一次写入水平轴的命令角度，不代表闭环测量位置。 */
    int getPanAngle() const;

    /** 返回最近一次写入俯仰轴的命令角度，不代表闭环测量位置。 */
    int getTiltAngle() const;

private:
    static constexpr uint32_t SERVO_FREQUENCY_HZ = 50;       // SG90 标准刷新频率，周期 20 ms。
    static constexpr uint8_t SERVO_PWM_RESOLUTION_BITS = 16; // LEDC 16 位分辨率用于细化脉宽。
    static constexpr int SERVO_PERIOD_US = 20000;             // 50 Hz 对应 20000 us 周期。
    static constexpr int SERVO_MIN_PULSE_US = 500;            // 临时 0 deg 脉宽，尚需实物校准。
    static constexpr int SERVO_MAX_PULSE_US = 2500;           // 临时 180 deg 脉宽，尚需实物校准。
    // PWM 换算仍按 SG90 的完整 0..180 度命令区间计算；机械限位在写入前按轴分别执行。
    static constexpr int PWM_ANGLE_MIN_DEG = 0;
    static constexpr int PWM_ANGLE_MAX_DEG = 180;

    uint8_t panPin;
    uint8_t tiltPin;
    uint8_t panChannel;
    uint8_t tiltChannel;
    int panAngle;
    int tiltAngle;

    static int clampPanAngle(int angle);                // 水平轴机械边界：0..180 deg。
    static int clampTiltAngle(int angle);               // 垂直轴机械边界：5..60 deg。
    static int clampPwmAngle(int angle);                // PWM 换算输入边界：0..180 deg。
    static uint32_t angleToDuty(int angle);             // 把角度线性换算为 16 位 LEDC duty。
    void writeAngle(uint8_t channel, int angle);        // 向指定 LEDC 通道写入换算后的 duty。
};

#endif
