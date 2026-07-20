#ifndef JW01_CO2_H
#define JW01_CO2_H

#include <Arduino.h>
#include <HardwareSerial.h>

#define RXD2 16
#define TXD2 17

// 定义串口波特率 (JW01 默认通常是 9600)
#define JW01_BAUD_RATE 9600

// 数据包长度 (JW01 通常是 6 字节或 9 字节，这里按标准的 6 字节处理)
// 格式：0x2C, 0x00, High, Low, CheckSum, 0x2C (不同批次可能略有不同，需根据实际调整)
// 常见格式：帧头(0x2C), 状态(0x00), 高8位, 低8位, 校验和, 帧尾(0x2C)
#define PACKET_SIZE 6

class JW01_CO2
{
private:
    HardwareSerial *_serialPort; // 指向串口对象的指针
    int _rxPin;
    int _txPin;

    unsigned long _lastReadTime;
    int _co2Value;
    bool _isDataReady;

    // 内部解析函数
    bool parseData(byte *buffer);

public:
    // 构造函数
    JW01_CO2();

    // 初始化串口
    void begin();

    // 循环处理函数 (需要在 loop 中不断调用)
    void update();

    // 获取 CO2 浓度
    int getCO2();

    // 检查是否有新数据
    bool isDataReady();
};

// 全局打印辅助函数
void printCO2Status(JW01_CO2 &sensor);

#endif