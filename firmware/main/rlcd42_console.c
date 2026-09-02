/*
 * SPDX-FileCopyrightText: 2025 sanoTTS-jp contributors
 * SPDX-FileCopyrightText: 2026 RLCD42 sanoTTS demo contributors
 * SPDX-License-Identifier: MIT
 *
 * RLCD4.2 console adapter. It preserves sanoTTS-jp's tested UTF-8 line state
 * machine and adds a debounced, local KEY trigger for battery-only use.
 */
#include "saan_console.h"

#if SAAN_INTERACTIVE

#include <string.h>

#include "driver/gpio.h"
#include "driver/usb_serial_jtag.h"
#include "esp_err.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "sdkconfig.h"

#include "demo_ids.h"
#include "line.h"

#if !defined(CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG)
#error "RLCD4.2 local KEY console requires the native USB Serial/JTAG console"
#endif

#define RLCD42_KEY_GPIO       GPIO_NUM_18
#define KEY_POLL_MS           20
#define KEY_DEBOUNCE_SAMPLES  3
#define PROMPT                "かな> "

_Static_assert(RLCD42_KEY_GPIO != GPIO_NUM_4,
               "KEY must not conflict with the battery ADC");

#define TAG "rlcd42_console"
__attribute__((used)) static const char s_key_capability[] =
    "RLCD42_CAP:key-local-demo-v1";
static char s_buffer[SAAN_CONSOLE_LINE_MAX];
static saan_line s_line;
static int s_key_last_raw;
static int s_key_stable;
static unsigned s_key_stable_samples;
static TickType_t s_key_last_sample;
static bool s_key_seen_released;
static bool s_key_pressed;

static void port_write(const char *text, size_t length)
{
    /* There may be no USB host while the board runs from its 18650. Never let
     * prompt/echo output prevent the task from returning to the KEY poll. A
     * connected terminal normally drains this immediately; otherwise partial
     * UI output is intentionally dropped after the bounded wait. */
    while (length > 0) {
        const int written = usb_serial_jtag_write_bytes(
            text, length, pdMS_TO_TICKS(5));
        if (written <= 0) return;
        text += written;
        length -= (size_t)written;
    }
}

static void put(const char *text)
{
    port_write(text, strlen(text));
}

static void redraw(void)
{
    put("\r\x1b[K" PROMPT);
    if (s_line.len > 0) port_write(s_line.buf, s_line.len);
}

/* Returns true once, on the debounced release following a fresh press. A KEY
 * held during startup is deliberately ignored until it is released and
 * pressed again, preventing an unexpected utterance during power-up. */
static bool key_demo_requested(void)
{
    const TickType_t now = xTaskGetTickCount();
    if (now - s_key_last_sample < pdMS_TO_TICKS(KEY_POLL_MS)) return false;
    s_key_last_sample = now;
    const int raw = gpio_get_level(RLCD42_KEY_GPIO);
    if (raw != s_key_last_raw) {
        s_key_last_raw = raw;
        s_key_stable_samples = 1;
        return false;
    }
    if (s_key_stable_samples < KEY_DEBOUNCE_SAMPLES)
        ++s_key_stable_samples;
    if (s_key_stable_samples < KEY_DEBOUNCE_SAMPLES || raw == s_key_stable)
        return false;

    s_key_stable = raw;
    if (raw == 0) {
        if (s_key_seen_released) s_key_pressed = true;
        return false;
    }

    s_key_seen_released = true;
    if (!s_key_pressed) return false;
    s_key_pressed = false;
    return true;
}

bool saan_console_init(void)
{
    usb_serial_jtag_driver_config_t usb_config =
        USB_SERIAL_JTAG_DRIVER_CONFIG_DEFAULT();
    esp_err_t err = usb_serial_jtag_driver_install(&usb_config);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "USB Serial/JTAG driver installation failed: %s",
                 esp_err_to_name(err));
        return false;
    }

    const gpio_config_t key_config = {
        .pin_bit_mask = 1ULL << RLCD42_KEY_GPIO,
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_ENABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    err = gpio_config(&key_config);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "KEY GPIO%d configuration failed: %s",
                 RLCD42_KEY_GPIO, esp_err_to_name(err));
        return false;
    }

    saan_line_reset(&s_line, s_buffer, sizeof s_buffer);
    s_key_last_raw = gpio_get_level(RLCD42_KEY_GPIO);
    s_key_stable = s_key_last_raw;
    s_key_stable_samples = KEY_DEBOUNCE_SAMPLES;
    s_key_last_sample = xTaskGetTickCount();
    s_key_seen_released = s_key_stable != 0;
    s_key_pressed = false;
    ESP_LOGI(TAG, "input ready: USB Serial/JTAG or KEY GPIO%d fixed demo",
             RLCD42_KEY_GPIO);
    ESP_LOGI(TAG, "%s", s_key_capability);
    return true;
}

int saan_console_readline(const char **out)
{
    *out = s_buffer;
    put("\r\n" PROMPT);

    for (;;) {
        unsigned char byte = 0;
        const int received = usb_serial_jtag_read_bytes(
            &byte, 1, pdMS_TO_TICKS(KEY_POLL_MS));
        if (received == 1) {
            switch (saan_line_feed(&s_line, byte)) {
            case SAAN_LINE_DONE:
                put("\r\n");
                return s_line.overflow ? SAAN_CONSOLE_TOO_LONG : (int)s_line.len;
            case SAAN_LINE_EDIT:
                redraw();
                break;
            case SAAN_LINE_ECHO:
                port_write((const char *)&byte, 1);
                break;
            case SAAN_LINE_MORE:
                break;
            }
        } else if (received < 0) {
            ESP_LOGE(TAG, "USB Serial/JTAG read failed");
            return SAAN_CONSOLE_ERROR;
        }

        if (!key_demo_requested()) continue;
        /* DONE deliberately retains the completed USB line until the next USB
         * byte so a delayed LF can be swallowed after CR. That retained line
         * is not an edit conflict: KEY must still work after USB is unplugged. */
        if (!s_line.done && (s_line.len != 0 || s_line.overflow || s_line.esc)) {
            ESP_LOGW(TAG, "KEY demo ignored while a USB input line is being edited");
            continue;
        }
        *out = SAAN_DEMO_INTERMEDIATE;
        put("\r\n[KEY] " SAAN_DEMO_INTERMEDIATE "\r\n");
        ESP_LOGI(TAG, "KEY demo requested: %s", SAAN_DEMO_TEXT);
        return SAAN_DEMO_INTERMEDIATE_BYTES;
    }
}

#endif /* SAAN_INTERACTIVE */
