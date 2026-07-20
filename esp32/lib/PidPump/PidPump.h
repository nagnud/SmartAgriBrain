#ifndef PID_CTRL_PUMP_H
#define PID_CTRL_PUMP_H

void pid_init_pump(float kp, float ki, float kd, float out_min, float out_max);
float pid_compute_pump(float setpoint, float measured_value, float dt);

#endif