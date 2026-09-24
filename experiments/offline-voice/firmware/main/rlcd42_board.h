#ifndef RLCD42_BOARD_H
#define RLCD42_BOARD_H

#include <stdbool.h>
#include <stdint.h>

#include "driver/i2c_master.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Initializes only the peripherals needed by the demo. The very first GPIO
 * mutation latches the NS4150B amplifier enable LOW, makes it an output, and
 * reads the pad back before I2C or any audio object can be created. */
bool rlcd42_board_init(void);

i2c_master_bus_handle_t rlcd42_board_i2c_bus(void);

/* Read-only address probe. Addresses are 7-bit values; ES8311 is 0x18 here,
 * while esp_codec_dev's ES8311_CODEC_DEFAULT_ADDR is the 8-bit value 0x30. */
bool rlcd42_board_i2c_present(uint8_t address);

/* GPIO46 drives the external NS4150B amplifier enable, active high. Enabling
 * is rejected until the board fingerprint probe has succeeded. */
bool rlcd42_board_set_amp_enabled(bool enabled);
bool rlcd42_board_amp_is_disabled(void);

#ifdef __cplusplus
}
#endif

#endif
