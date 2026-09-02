#ifndef RLCD42_DISPLAY_H
#define RLCD42_DISPLAY_H

#include <stdbool.h>
#include <stdint.h>

#include "rlcd42_battery.h"

#ifdef __cplusplus
extern "C" {
#endif

bool rlcd42_display_init(void);
void rlcd42_display_show_probe_pattern(void);
void rlcd42_display_set_battery(const rlcd42_battery_status_t *status);
void rlcd42_display_set_ready(void);
void rlcd42_display_set_speaking(bool speaking);
void rlcd42_display_set_level(uint8_t level);
void rlcd42_display_show_error(const char *short_message);

#ifdef __cplusplus
}
#endif

#endif
