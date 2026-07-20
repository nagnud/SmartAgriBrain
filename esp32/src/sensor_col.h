#ifndef SENSOR_COL_H
#define SENSOR_COL_H

float sensor_ambient_light(unsigned long current_millis);
float sensor_get_sensor_reading(float ambient_light, float current_pwm_duty);

#endif