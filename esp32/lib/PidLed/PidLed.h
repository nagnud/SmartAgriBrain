#ifndef PID_CTRL_H
#define PID_CTRL_H

void pid_init(float kp, float ki, float kd, float out_min, float out_max);
float pid_compute(float setpoint, float measured_value, float dt);

#endif