#ifndef LIGHTSENSOR_H
#define LIGHTSENSOR_H

#include <Arduino.h>
#include <Wire.h>

/**
 * @brief BH1750 传感器 I2C 地址定义
 * 根据传感器模块上 ADDR 引脚的连接情况选择
 */
#define BH1750_ADDR_LOW 0x23  // ADDR 引脚接地 (GND)
#define BH1750_ADDR_HIGH 0x5C // ADDR 引脚接电源 (VCC)

#define SDA_PIN 21
#define SCL_PIN 22
/**
 * @brief 测量模式指令定义
 * 参考 BH1750 数据手册
 */
enum BH1750_MODE
{
    POWER_DOWN = 0x00,            // 关机模式
    CONTINUOUS_LOW_RES = 0x13,    // 连续低分辨率模式 (4 lux, 16ms)
    CONTINUOUS_HIGH_RES = 0x10,   // 连续高分辨率模式 1 (1 lux, 120ms)
    CONTINUOUS_HIGH_RES_2 = 0x11, // 连续高分辨率模式 2 (0.5 lux, 120ms)
    ONE_TIME_LOW_RES = 0x23,      // 单次低分辨率模式
    ONE_TIME_HIGH_RES = 0x20,     // 单次高分辨率模式 1
    ONE_TIME_HIGH_RES_2 = 0x21    // 单次高分辨率模式 2
};

class BH1750
{
private:
    TwoWire *_i2cPort; // I2C 总线指针 (Wire 或 Wire1)
    uint8_t _i2cAddr;  // 设备 I2C 地址
    float _lux;        // 存储最近一次读取的光照值

    /**
     * @brief 向传感器写入命令
     * @param command 要发送的指令字节
     * @return true 如果发送成功，false 如果通信失败
     */
    bool writeCommand(uint8_t command);

public:
    /**
     * @brief 构造函数
     * @param addr I2C 地址 (默认为 BH1750_ADDR_LOW)
     * @param wire 使用的 I2C 总线对象 (默认为 Wire)
     */
    BH1750(uint8_t addr = BH1750_ADDR_LOW, TwoWire *wire = &Wire);

    /**
     * @brief 初始化传感器
     * @param mode 启动时的测量模式 (默认为连续高分辨率模式)
     * @return true 如果初始化成功 (检测到设备)，false 否则
     */
    bool begin(BH1750_MODE mode = CONTINUOUS_HIGH_RES);

    /**
     * @brief 读取光照强度
     * @return 光照强度值 (单位: Lux)
     */
    float readLight();

    /**
     * @brief 更改测量模式
     * @param mode 新的测量模式
     */
    void setMode(BH1750_MODE mode);

    /**
     * @brief 进入低功耗模式 (停止测量)
     */
    void sleep();
};

void printBH1750Data(BH1750 *bh1750);

#endif