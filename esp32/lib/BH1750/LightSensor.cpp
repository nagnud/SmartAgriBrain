#include "LightSensor.h"

/**
 * @brief 构造函数实现
 */
BH1750::BH1750(uint8_t addr, TwoWire *wire)
{
    _i2cAddr = addr;
    _i2cPort = wire;
    _lux = 0.0;
}

/**
 * @brief 内部函数：发送单字节命令
 */
bool BH1750::writeCommand(uint8_t command)
{
    _i2cPort->beginTransmission(_i2cAddr);
    if (_i2cPort->write(command) == 1)
    {
        // 发送成功，检查结束传输的应答
        return (_i2cPort->endTransmission() == 0);
    }
    _i2cPort->endTransmission();
    return false;
}

/**
 * @brief 初始化传感器
 * 启动 I2C 总线并配置传感器模式
 */
bool BH1750::begin(BH1750_MODE mode)
{
    Wire.begin(SDA_PIN, SCL_PIN);
    //_i2cPort->begin();

    // 先发送关机指令复位传感器，确保状态已知
    writeCommand(POWER_DOWN);
    delay(10); // 等待传感器复位

    // 设置工作模式
    if (writeCommand(mode))
    {
        // 如果是单次模式，需要等待测量完成
        // 高分辨率模式通常需要 120ms
        if (mode == ONE_TIME_HIGH_RES || mode == ONE_TIME_HIGH_RES_2)
        {
            delay(120);
        }
        return true;
    }
    return false;
}

/**
 * @brief 读取光照数据
 * @return float 类型的 Lux 值
 */
float BH1750::readLight()
{
    uint8_t byteHigh = 0;
    uint8_t byteLow = 0;
    uint16_t value = 0;

    //请求 2 个字节的数据
    _i2cPort->requestFrom(_i2cAddr, (uint8_t)2);

    if (_i2cPort->available() == 2)
    {
        //读取高字节
        byteHigh = _i2cPort->read();//一次只能读取uint_8,所以需要两次读取来获取完整的16位数据
        // 读取低字节
        byteLow = _i2cPort->read();
        //合并数据
        value = (byteHigh << 8) | byteLow;
        //数据换算公式：Lux = Value / 1.2
        _lux = value / 1.2;
    }

    return _lux;
}

/**
 * @brief 更改模式
 * 用于在运行时切换模式 (例如从连续模式切换到休眠)
 */
void BH1750::setMode(BH1750_MODE mode)
{
    writeCommand(mode);
}

/**
 * @brief 休眠
 * 停止测量以节省电量
 */
void BH1750::sleep()
{
    writeCommand(POWER_DOWN);
}



void printBH1750Data(BH1750 *bh1750)
{

    float lux = bh1750->readLight(); // 1. 读取 Lux 值

    // 2. 简单校验：BH1750 有效范围通常在 0 - 65535 Lux
    if (isnan(lux))
    {
        Serial.println("读取数据无效！");
        return;
    }

    Serial.print("光照强度: ");
    Serial.print(lux);
    Serial.print(" Lux");

    if (lux < 10)
    {
        Serial.println(" (环境很暗)");
    }
    else if (lux < 1000)
    {
        Serial.println(" (室内光线)");
    }
    else
    {
        Serial.println(" (阳光强烈)");
    }
}
