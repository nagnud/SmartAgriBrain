#include <Arduino.h>

#include "Dht11Sensor.h"

// GPIO4 is the confirmed DATA connection for the project's DHT11.
Dht11Sensor diagnosticDht11Sensor(4);

void setup_TestDht11Sensor()
{
  Serial.begin(115200);
  diagnosticDht11Sensor.begin();
}

void loop_TestDht11Sensor()
{
  diagnosticDht11Sensor.update();

  Serial.printf("DHT11 temperature: %.1f degC, humidity: %.1f %%RH\n",
                diagnosticDht11Sensor.getTemperatureC(),
                diagnosticDht11Sensor.getHumidityPercent());

  // The driver enforces its own sampling interval; this delay only keeps the
  // standalone diagnostic output readable.
  delay(2000);
}
