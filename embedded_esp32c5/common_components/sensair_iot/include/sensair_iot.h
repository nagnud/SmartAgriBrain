/*
 * SPDX-FileCopyrightText: 2026
 * SPDX-License-Identifier: Apache-2.0
 */
#pragma once

#include <stdbool.h>
#include <stdint.h>

#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    float temperature_c;
    float humidity_pct;
    float pressure_kpa;
    float gas_resistance_ohm;

    float acc_x_g;
    float acc_y_g;
    float acc_z_g;
    float gyro_x_dps;
    float gyro_y_dps;
    float gyro_z_dps;

    float mag_x_ut;
    float mag_y_ut;
    float mag_z_ut;

    bool environment_valid;
    bool imu_valid;
    bool magnetometer_valid;
    int64_t environment_updated_us;
    int64_t imu_updated_us;
    int64_t magnetometer_updated_us;
} sensair_sensor_snapshot_t;

/** Start serial telemetry, optional Wi-Fi/MQTT, command handling and actuators. */
esp_err_t sensair_iot_start(void);

/** Copy the latest complete sensor snapshot. */
void sensair_sensor_get_snapshot(sensair_sensor_snapshot_t *snapshot);

/** BSEC pressure is supplied in Pa and converted to kPa for the wire protocol. */
void sensair_sensor_update_environment(float temperature_c,
                                       float humidity_pct,
                                       float pressure_pa,
                                       float gas_resistance_ohm);

void sensair_sensor_update_imu(float acc_x_g,
                               float acc_y_g,
                               float acc_z_g,
                               float gyro_x_dps,
                               float gyro_y_dps,
                               float gyro_z_dps);

void sensair_sensor_update_magnetometer(float mag_x_ut,
                                        float mag_y_ut,
                                        float mag_z_ut);

#ifdef __cplusplus
}
#endif

