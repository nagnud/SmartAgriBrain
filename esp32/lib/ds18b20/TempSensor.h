#ifndef TEMPSENSOR_H
#define TEMPSENSOR_H

#include <Arduino.h>
#include <OneWire.h>
#include <DallasTemperature.h>

#define DEFAULT_ONE_WIRE_BUS 4

class TempSensor
{
public:
    TempSensor(int oneWireBusPin = DEFAULT_ONE_WIRE_BUS);

    void begin();
    void update();

    float getTemperature();
    bool isSensorConnected();

private:
    int _pin;
    OneWire *_oneWire;
    DallasTemperature *_sensors;

    unsigned long _lastRequestTime;
    bool _isWaitingForConversion;
    float _currentTemp;
    bool _hasNewData;
    bool _sensorConnected;

    DeviceAddress _deviceAddress;
};

#endif
