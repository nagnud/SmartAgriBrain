#include "TempSensor.h"

TempSensor::TempSensor(int oneWireBusPin)
{
    _pin = oneWireBusPin;
    _oneWire = nullptr;
    _sensors = nullptr;
    _lastRequestTime = 0;
    _isWaitingForConversion = false;
    _currentTemp = DEVICE_DISCONNECTED_C;
    _hasNewData = false;
    _sensorConnected = false;
}

void TempSensor::begin()
{
    if (_oneWire == nullptr)
    {
        _oneWire = new OneWire(_pin);
    }

    if (_sensors == nullptr)
    {
        _sensors = new DallasTemperature(_oneWire);
    }

    _sensors->begin();
    _sensorConnected = _sensors->getAddress(_deviceAddress, 0);

    if (!_sensorConnected)
    {
        _currentTemp = DEVICE_DISCONNECTED_C;
        _isWaitingForConversion = false;
        Serial.printf("[TempSensor] DS18B20 not found on GPIO %d\n", _pin);
        return;
    }

    _sensors->setResolution(_deviceAddress, 12);
    _sensors->setWaitForConversion(false);
    _sensors->requestTemperaturesByAddress(_deviceAddress);
    _lastRequestTime = millis();
    _isWaitingForConversion = true;

    Serial.printf("[TempSensor] DS18B20 detected on GPIO %d\n", _pin);
}

void TempSensor::update()
{
    if (_sensors == nullptr)
    {
        return;
    }

    if (!_sensorConnected)
    {
        if (millis() - _lastRequestTime >= 5000)
        {
            _lastRequestTime = millis();
            _sensorConnected = _sensors->getAddress(_deviceAddress, 0);
            if (_sensorConnected)
            {
                _sensors->setResolution(_deviceAddress, 12);
                _sensors->setWaitForConversion(false);
                _sensors->requestTemperaturesByAddress(_deviceAddress);
                _isWaitingForConversion = true;
                Serial.printf("[TempSensor] DS18B20 detected on GPIO %d\n", _pin);
            }
            else
            {
                Serial.printf("[TempSensor] DS18B20 still not found on GPIO %d\n", _pin);
            }
        }
        return;
    }

    if (_isWaitingForConversion)
    {
        if (millis() - _lastRequestTime >= 750)
        {
            _currentTemp = _sensors->getTempC(_deviceAddress);
            _isWaitingForConversion = false;
            _hasNewData = true;

            if (_currentTemp == DEVICE_DISCONNECTED_C)
            {
                _sensorConnected = false;
                Serial.println("[TempSensor] Failed to read DS18B20 temperature");
            }
        }
        return;
    }

    _sensors->requestTemperaturesByAddress(_deviceAddress);
    _lastRequestTime = millis();
    _isWaitingForConversion = true;
}

float TempSensor::getTemperature()
{
    return _currentTemp;
}

bool TempSensor::isSensorConnected()
{
    return _sensors != nullptr && _sensorConnected && _sensors->getDeviceCount() > 0;
}
