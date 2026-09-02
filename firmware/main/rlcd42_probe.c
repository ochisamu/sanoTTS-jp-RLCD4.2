#include <inttypes.h>

#include "driver/gpio.h"
#include "esp_err.h"
#include "esp_flash.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_psram.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "rlcd42_board.h"
#include "rlcd42_battery.h"
#include "rlcd42_display.h"

#define RLCD42_KEY_GPIO  GPIO_NUM_18
#define RLCD42_BOOT_GPIO GPIO_NUM_0
#define EXPECTED_FLASH_BYTES (16u * 1024u * 1024u)
#define EXPECTED_PSRAM_BYTES (8u * 1024u * 1024u)

#define TAG "rlcd42_probe"
__attribute__((used)) static const char s_board_marker[] =
    "rlcd42-sanotts-demo:Waveshare-ESP32-S3-RLCD-4.2:probe";
__attribute__((used)) static const char s_profile_marker[] =
    "RLCD42_PROFILE:probe";

static bool configure_buttons(void)
{
    const gpio_config_t cfg = {
        .pin_bit_mask = (1ULL << RLCD42_KEY_GPIO) |
                        (1ULL << RLCD42_BOOT_GPIO),
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_ENABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    const esp_err_t err = gpio_config(&cfg);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "button GPIO configuration failed: %s",
                 esp_err_to_name(err));
        return false;
    }
    return true;
}

static void log_button(const char *name, gpio_num_t gpio, int level)
{
    ESP_LOGI(TAG, "%s GPIO%d=%d (%s)", name, gpio, level,
             level == 0 ? "pressed" : "released");
}

static bool probe_memory(void)
{
    uint32_t flash_bytes = 0;
    const size_t psram_bytes = esp_psram_get_size();
    const size_t psram_heap = heap_caps_get_total_size(MALLOC_CAP_SPIRAM);
    if (esp_flash_get_size(NULL, &flash_bytes) != ESP_OK) {
        ESP_LOGE(TAG, "could not read physical Flash size");
        return false;
    }
    ESP_LOGI(TAG, "Flash=%" PRIu32 " bytes; PSRAM=%u bytes (%u-byte heap)",
             flash_bytes, (unsigned)psram_bytes, (unsigned)psram_heap);
    if (flash_bytes != EXPECTED_FLASH_BYTES ||
        psram_bytes != EXPECTED_PSRAM_BYTES || psram_heap == 0) {
        ESP_LOGE(TAG, "expected 16 MiB Flash and initialized 8 MiB Octal PSRAM");
        return false;
    }
    return true;
}

static bool probe_i2c_devices(void)
{
    static const struct {
        uint8_t address;
        const char *name;
    } expected[] = {
        {0x18, "ES8311"},
        {0x40, "ES7210"},
        {0x51, "PCF85063"},
        {0x70, "SHTC3"},
    };
    bool all_present = true;
    for (size_t i = 0; i < sizeof expected / sizeof expected[0]; ++i) {
        const bool present = rlcd42_board_i2c_present(expected[i].address);
        ESP_LOGI(TAG, "I2C 0x%02x %-8s %s", expected[i].address,
                 expected[i].name, present ? "PRESENT" : "MISSING");
        if (!present) all_present = false;
    }
    if (!all_present) ESP_LOGE(TAG, "one or more expected board peripherals are missing");
    return all_present;
}

static void log_battery(const rlcd42_battery_status_t *battery)
{
    if (!battery->voltage_available) {
        ESP_LOGI(TAG, "BAT_ADC raw=%u; VBAT voltage is not available (USB/cell state is not distinguishable)",
                 battery->raw);
        return;
    }
    ESP_LOGI(TAG, "BAT_ADC raw=%u; VBAT=%u mV; estimated level=%u%%; expected range=%s",
             battery->raw, battery->millivolts, battery->percent,
             battery->in_expected_range ? "OK" : "CHECK");
}

void app_main(void)
{
    ESP_LOGI(TAG, "model-free RLCD-4.2 board probe starting");
    ESP_LOGI(TAG, "%s", s_profile_marker);

    if (!rlcd42_board_init()) {
        ESP_LOGE(TAG, "board initialization failed; GPIO46 remains LOW");
        return;
    }
    if (!probe_memory() || !probe_i2c_devices()) {
        ESP_LOGE(TAG, "board fingerprint probe failed; GPIO46 remains LOW");
        return;
    }
    rlcd42_battery_status_t battery;
    if (!rlcd42_battery_init() || !rlcd42_battery_read(&battery)) {
        ESP_LOGE(TAG, "battery ADC probe failed; GPIO46 remains LOW");
        return;
    }
    log_battery(&battery);
    if (!rlcd42_display_init()) {
        ESP_LOGE(TAG, "display initialization failed; GPIO46 remains LOW");
        return;
    }
    rlcd42_display_show_probe_pattern();
    rlcd42_display_set_battery(&battery);
    if (!configure_buttons()) {
        ESP_LOGE(TAG, "button probe failed; GPIO46 remains LOW");
        return;
    }
    if (!rlcd42_board_set_amp_enabled(false) ||
        !rlcd42_board_amp_is_disabled()) {
        ESP_LOGE(TAG, "GPIO46 PA disable verification failed");
        return;
    }

    int key_level = gpio_get_level(RLCD42_KEY_GPIO);
    int boot_level = gpio_get_level(RLCD42_BOOT_GPIO);
    log_button("KEY", RLCD42_KEY_GPIO, key_level);
    log_button("BOOT", RLCD42_BOOT_GPIO, boot_level);
    ESP_LOGI(TAG, "GPIO46 PA_EN=LOW permanently; audio/I2S/mic/Wi-Fi are not initialized");
    ESP_LOGI(TAG, "touch is absent and not initialized");
    ESP_LOGI(TAG, "READY");

    TickType_t last_battery_sample = xTaskGetTickCount();

    for (;;) {
        const int next_key_level = gpio_get_level(RLCD42_KEY_GPIO);
        const int next_boot_level = gpio_get_level(RLCD42_BOOT_GPIO);
        if (next_key_level != key_level) {
            key_level = next_key_level;
            log_button("KEY", RLCD42_KEY_GPIO, key_level);
        }
        if (next_boot_level != boot_level) {
            boot_level = next_boot_level;
            log_button("BOOT", RLCD42_BOOT_GPIO, boot_level);
        }
        if (!rlcd42_board_amp_is_disabled()) {
            ESP_LOGE(TAG, "GPIO46 PA_EN left LOW state; forcing it LOW again");
            (void)rlcd42_board_set_amp_enabled(false);
        }
        const TickType_t now = xTaskGetTickCount();
        if (now - last_battery_sample >= pdMS_TO_TICKS(30000)) {
            rlcd42_battery_status_t next_battery;
            if (rlcd42_battery_read(&next_battery)) {
                log_battery(&next_battery);
                rlcd42_display_set_battery(&next_battery);
            } else {
                ESP_LOGE(TAG, "periodic battery ADC read failed");
                rlcd42_display_set_battery(NULL);
            }
            last_battery_sample = now;
        }
        vTaskDelay(pdMS_TO_TICKS(50));
    }
}
