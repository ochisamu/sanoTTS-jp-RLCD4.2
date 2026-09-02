/*
 * SPDX-FileCopyrightText: 2026 Waveshare
 * SPDX-FileCopyrightText: 2026 RLCD42 sanoTTS demo contributors
 * SPDX-License-Identifier: Apache-2.0
 */
#ifndef RLCD42_BATTERY_H
#define RLCD42_BATTERY_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* GPIO4 is ADC1 channel 3 behind the board's 200 kOhm / 100 kOhm divider.
 * `voltage_available` means a calibrated value can be shown; a successful
 * rlcd42_battery_read() sets it even for an out-of-range value. The board does
 * not expose a software-readable cell-presence, charge-state or USB-power-
 * source pin. */
typedef struct {
    uint16_t raw;
    uint16_t millivolts;
    uint8_t percent;
    bool voltage_available;
    bool in_expected_range;
} rlcd42_battery_status_t;

bool rlcd42_battery_init(void);
bool rlcd42_battery_read(rlcd42_battery_status_t *status);

#ifdef __cplusplus
}
#endif

#endif
