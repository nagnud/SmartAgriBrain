#include "Dht11Sensor.h"

#include <math.h>

Dht11Sensor::Dht11Sensor(uint8_t dataPin, uint32_t sampleIntervalMs)
    : dataPin_(dataPin),
      sampleIntervalMs_(max(sampleIntervalMs, 1000U)),
      lastSampleMs_(0),
      firstSamplePending_(true),
      temperatureC_(NAN),
      humidityPercent_(NAN),
      dht_(dataPin, DHT11)
{
}

void Dht11Sensor::begin()
{
  dht_.begin();
  firstSamplePending_ = true;
  temperatureC_ = NAN;
  humidityPercent_ = NAN;

  Serial.printf("[SENSOR][INIT_OK] name=DHT11 data_gpio=%u sample_interval_ms=%u\n",
                dataPin_,
                sampleIntervalMs_);
}

void Dht11Sensor::update()
{
  const uint32_t now = millis();

  // Unsigned subtraction remains correct when millis() wraps after long uptime.
  if (!firstSamplePending_ && now - lastSampleMs_ < sampleIntervalMs_)
  {
    return;
  }

  firstSamplePending_ = false;
  lastSampleMs_ = now;

  // The Adafruit driver caches one physical transaction, so these two getters
  // describe the same DHT11 sample instead of triggering two bus reads.
  const float sampledHumidityPercent = dht_.readHumidity();
  const float sampledTemperatureC = dht_.readTemperature(false);

  humidityPercent_ = isfinite(sampledHumidityPercent) ? sampledHumidityPercent : NAN;
  temperatureC_ = isfinite(sampledTemperatureC) ? sampledTemperatureC : NAN;

  if (!isfinite(humidityPercent_) || !isfinite(temperatureC_))
  {
    Serial.printf("[SENSOR][READ_FAIL] name=DHT11 data_gpio=%u temperature_valid=%u humidity_valid=%u\n",
                  dataPin_,
                  isfinite(temperatureC_) ? 1U : 0U,
                  isfinite(humidityPercent_) ? 1U : 0U);
    return;
  }

  Serial.printf("[SENSOR][READ_OK] name=DHT11 temperature_c=%.1f humidity_pct=%.1f\n",
                temperatureC_,
                humidityPercent_);
}

float Dht11Sensor::getTemperatureC() const
{
  return temperatureC_;
}

float Dht11Sensor::getHumidityPercent() const
{
  return humidityPercent_;
}
