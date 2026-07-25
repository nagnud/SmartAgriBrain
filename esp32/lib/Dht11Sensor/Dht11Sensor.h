#ifndef DHT11_SENSOR_H
#define DHT11_SENSOR_H

#include <Arduino.h>
#include <DHT.h>

/**
 * DHT11 temperature and relative-humidity driver.
 *
 * The wrapper owns the hardware driver and enforces a non-blocking sampling
 * schedule. Call update() on every main-loop pass; values are exposed through
 * the getters and become NAN when the latest acquisition is invalid.
 */
class Dht11Sensor
{
public:
  /**
   * Create a DHT11 sensor instance.
   *
   * @param dataPin ESP32 GPIO connected to the DHT11 DATA signal.
   * @param sampleIntervalMs Minimum interval between physical acquisitions.
   *        DHT11 must not be sampled faster than once per second; this project
   *        defaults to 2000 ms to provide timing margin.
   */
  explicit Dht11Sensor(uint8_t dataPin, uint32_t sampleIntervalMs = 2000U);

  /** Initialize the DHT11 driver. Call exactly once from setup(). */
  void begin();

  /**
   * Acquire a new sample when the configured interval has elapsed.
   *
   * This method never delays merely to wait for the next sampling deadline, so
   * it is safe to call on every Arduino loop iteration.
   */
  void update();

  /**
   * Return the latest air temperature.
   *
   * @return Temperature in degrees Celsius, or NAN if no valid sample exists.
   */
  float getTemperatureC() const;

  /**
   * Return the latest air relative humidity.
   *
   * @return Relative humidity in %RH, or NAN if no valid sample exists.
   */
  float getHumidityPercent() const;

private:
  uint8_t dataPin_;                 // GPIO number used by the one-wire-like DHT DATA signal.
  uint32_t sampleIntervalMs_;       // Minimum time between two physical DHT11 reads.
  uint32_t lastSampleMs_;           // millis() timestamp of the latest acquisition attempt.
  bool firstSamplePending_;         // Allows the first loop pass to sample without a startup delay.
  float temperatureC_;              // Latest temperature, or NAN after a failed acquisition.
  float humidityPercent_;           // Latest relative humidity, or NAN after a failed acquisition.
  DHT dht_;                         // Adafruit hardware driver configured permanently as DHT11.
};

#endif
