#include "rlcd42_board.h"

#include "driver/gpio.h"
#include "esp_err.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#define RLCD42_I2C_PORT I2C_NUM_0
#define RLCD42_I2C_SDA  GPIO_NUM_13
#define RLCD42_I2C_SCL  GPIO_NUM_14
#define RLCD42_PA_EN     GPIO_NUM_46

#define ES8311_I2C_ADDR_7BIT 0x18

_Static_assert(RLCD42_PA_EN != RLCD42_I2C_SDA &&
               RLCD42_PA_EN != RLCD42_I2C_SCL,
               "amplifier enable conflicts with I2C");

#define TAG "rlcd42_board"
static i2c_master_bus_handle_t s_bus;
#define BOARD_AMP_LATCHED (1u << 0)
#define BOARD_READY       (1u << 1)
static uint8_t s_state;

static bool force_amp_low_first(void)
{
    /* gpio_set_level() writes the output latch even while the pad is still an
     * input. This order prevents a high pulse when output-enable is asserted. */
    if (gpio_set_level(RLCD42_PA_EN, 0) != ESP_OK) {
        ESP_LOGE(TAG, "could not preload GPIO%d LOW", RLCD42_PA_EN);
        return false;
    }

    const gpio_config_t cfg = {
        .pin_bit_mask = 1ULL << RLCD42_PA_EN,
        .mode = GPIO_MODE_INPUT_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    if (gpio_config(&cfg) != ESP_OK ||
        gpio_set_level(RLCD42_PA_EN, 0) != ESP_OK ||
        gpio_get_level(RLCD42_PA_EN) != 0) {
        ESP_LOGE(TAG, "GPIO%d amplifier-disable readback failed", RLCD42_PA_EN);
        return false;
    }

    s_state |= BOARD_AMP_LATCHED;
    ESP_LOGI(TAG, "speaker amplifier GPIO%d forced LOW (low-first, readback OK)",
             RLCD42_PA_EN);
    return true;
}

bool rlcd42_board_i2c_present(uint8_t address)
{
    if (!s_bus) return false;
    return i2c_master_probe(s_bus, address, 50) == ESP_OK;
}

bool rlcd42_board_init(void)
{
    if (s_state & BOARD_READY) return true;

    /* Keep this before bus creation and every other board mutation. */
    if (!(s_state & BOARD_AMP_LATCHED) && !force_amp_low_first()) return false;
    if (!rlcd42_board_amp_is_disabled()) {
        ESP_LOGE(TAG, "amplifier was not disabled at board entry");
        return false;
    }

    if (!s_bus) {
        const i2c_master_bus_config_t cfg = {
            .i2c_port = RLCD42_I2C_PORT,
            .sda_io_num = RLCD42_I2C_SDA,
            .scl_io_num = RLCD42_I2C_SCL,
            .clk_source = I2C_CLK_SRC_DEFAULT,
            .glitch_ignore_cnt = 7,
            .intr_priority = 0,
            .trans_queue_depth = 0,
            .flags.enable_internal_pullup = true,
        };
        esp_err_t err = i2c_new_master_bus(&cfg, &s_bus);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "I2C%d creation failed: %s", RLCD42_I2C_PORT,
                     esp_err_to_name(err));
            return false;
        }
    }

    /* This is intentionally only an address probe: board bring-up must not
     * change codec registers or enable its output path. Retry because the
     * codec may need a few milliseconds after board power stabilizes. */
    bool codec_present = false;
    for (int attempt = 0; attempt < 5 && !codec_present; ++attempt) {
        codec_present = rlcd42_board_i2c_present(ES8311_I2C_ADDR_7BIT);
        if (!codec_present && attempt < 4) vTaskDelay(pdMS_TO_TICKS(20));
    }
    if (!codec_present) {
        ESP_LOGE(TAG, "ES8311 not found at 7-bit address 0x%02x; amplifier remains OFF",
                 ES8311_I2C_ADDR_7BIT);
        return false;
    }
    if (!rlcd42_board_amp_is_disabled()) {
        ESP_LOGE(TAG, "amplifier changed state during read-only board probe");
        (void)gpio_set_level(RLCD42_PA_EN, 0);
        return false;
    }

    s_state |= BOARD_READY;
    ESP_LOGI(TAG, "RLCD-4.2 fingerprint OK: I2C%d SDA=%d SCL=%d, ES8311=0x%02x",
             RLCD42_I2C_PORT, RLCD42_I2C_SDA, RLCD42_I2C_SCL,
             ES8311_I2C_ADDR_7BIT);
    return true;
}

i2c_master_bus_handle_t rlcd42_board_i2c_bus(void)
{
    return s_bus;
}

bool rlcd42_board_set_amp_enabled(bool enabled)
{
    if (enabled && !(s_state & BOARD_READY)) {
        ESP_LOGE(TAG, "refusing amplifier enable before board fingerprint succeeds");
        return false;
    }
    if (!(s_state & BOARD_AMP_LATCHED) && !force_amp_low_first()) return false;

    const int level = enabled ? 1 : 0;
    if (gpio_set_level(RLCD42_PA_EN, level) != ESP_OK ||
        gpio_get_level(RLCD42_PA_EN) != level) {
        ESP_LOGE(TAG, "amplifier GPIO%d %s readback failed", RLCD42_PA_EN,
                 enabled ? "enable" : "disable");
        (void)gpio_set_level(RLCD42_PA_EN, 0);
        return false;
    }
    ESP_LOGI(TAG, "speaker amplifier %s", enabled ? "ON" : "OFF");
    return true;
}

bool rlcd42_board_amp_is_disabled(void)
{
    return (s_state & BOARD_AMP_LATCHED) && gpio_get_level(RLCD42_PA_EN) == 0;
}
