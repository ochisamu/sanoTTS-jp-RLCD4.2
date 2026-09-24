/*
 * SPDX-FileCopyrightText: 2026 Waveshare
 * SPDX-FileCopyrightText: 2026 RLCD42 sanoTTS demo contributors
 * SPDX-License-Identifier: Apache-2.0
 *
 * The pin, attenuation, calibration scheme and x3 divider follow Waveshare's
 * ESP32-S3-RLCD-4.2 ADC example at revision eb1f6342. Error handling,
 * multisampling and range reporting are specific to this demo.
 */
#include "rlcd42_battery.h"

#include <stddef.h>

#include "esp_adc/adc_cali.h"
#include "esp_adc/adc_cali_scheme.h"
#include "esp_adc/adc_oneshot.h"
#include "driver/gpio.h"
#include "esp_err.h"
#include "esp_log.h"

#define RLCD42_BATTERY_ADC_UNIT    ADC_UNIT_1
#define RLCD42_BATTERY_ADC_CHANNEL ADC_CHANNEL_3
#define RLCD42_BATTERY_ADC_GPIO    GPIO_NUM_4
#define RLCD42_BATTERY_DIVIDER     3u
#define RLCD42_BATTERY_SAMPLES     16u

/* Waveshare's board example maps 3.00 V to 0% and 4.12 V to 100%. The
 * percentage is only an estimate; the voltage and under-load behavior remain
 * the useful bring-up measurements. */
#define RLCD42_BATTERY_EMPTY_MV       3000u
#define RLCD42_BATTERY_FULL_MV        4120u
#define RLCD42_BATTERY_EXPECTED_MIN_MV 3000u
#define RLCD42_BATTERY_EXPECTED_MAX_MV 4200u

#define TAG "rlcd42_battery"
__attribute__((used)) static const char s_battery_capability[] =
    "RLCD42_CAP:battery-adc1-ch3-x3-v1";
static adc_oneshot_unit_handle_t s_adc;
static adc_cali_handle_t s_calibration;

static uint8_t battery_percent(uint32_t millivolts)
{
    if (millivolts <= RLCD42_BATTERY_EMPTY_MV) return 0;
    if (millivolts >= RLCD42_BATTERY_FULL_MV) return 100;
    return (uint8_t)(((millivolts - RLCD42_BATTERY_EMPTY_MV) * 100u) /
                     (RLCD42_BATTERY_FULL_MV - RLCD42_BATTERY_EMPTY_MV));
}

bool rlcd42_battery_init(void)
{
    if (s_adc && s_calibration) return true;

#if !ADC_CALI_SCHEME_CURVE_FITTING_SUPPORTED
    ESP_LOGE(TAG, "ESP32-S3 curve-fitting ADC calibration is unavailable");
    return false;
#else
    adc_unit_t mapped_unit = ADC_UNIT_2;
    adc_channel_t mapped_channel = ADC_CHANNEL_0;
    esp_err_t err = adc_oneshot_io_to_channel(
        RLCD42_BATTERY_ADC_GPIO, &mapped_unit, &mapped_channel);
    if (err != ESP_OK || mapped_unit != RLCD42_BATTERY_ADC_UNIT ||
        mapped_channel != RLCD42_BATTERY_ADC_CHANNEL) {
        ESP_LOGE(TAG, "GPIO%d did not map to ADC1 channel 3", RLCD42_BATTERY_ADC_GPIO);
        return false;
    }

    const adc_oneshot_unit_init_cfg_t unit_config = {
        .unit_id = RLCD42_BATTERY_ADC_UNIT,
        .ulp_mode = ADC_ULP_MODE_DISABLE,
    };
    err = adc_oneshot_new_unit(&unit_config, &s_adc);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "ADC1 initialization failed: %s", esp_err_to_name(err));
        s_adc = NULL;
        return false;
    }

    const adc_oneshot_chan_cfg_t channel_config = {
        .atten = ADC_ATTEN_DB_12,
        .bitwidth = ADC_BITWIDTH_12,
    };
    err = adc_oneshot_config_channel(s_adc, RLCD42_BATTERY_ADC_CHANNEL,
                                     &channel_config);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "GPIO%d ADC channel configuration failed: %s",
                 RLCD42_BATTERY_ADC_GPIO, esp_err_to_name(err));
        (void)adc_oneshot_del_unit(s_adc);
        s_adc = NULL;
        return false;
    }

    const adc_cali_curve_fitting_config_t calibration_config = {
        .unit_id = RLCD42_BATTERY_ADC_UNIT,
        .chan = RLCD42_BATTERY_ADC_CHANNEL,
        .atten = ADC_ATTEN_DB_12,
        .bitwidth = ADC_BITWIDTH_12,
    };
    err = adc_cali_create_scheme_curve_fitting(&calibration_config,
                                                &s_calibration);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "ADC calibration initialization failed: %s",
                 esp_err_to_name(err));
        (void)adc_oneshot_del_unit(s_adc);
        s_adc = NULL;
        s_calibration = NULL;
        return false;
    }

    ESP_LOGI(TAG, "battery monitor ready: GPIO%d/ADC1_CH3, 12 dB, calibrated x3 divider",
             RLCD42_BATTERY_ADC_GPIO);
    ESP_LOGI(TAG, "%s", s_battery_capability);
    return true;
#endif
}

bool rlcd42_battery_read(rlcd42_battery_status_t *status)
{
    if (!status || !rlcd42_battery_init()) return false;

    uint32_t raw_sum = 0;
    uint32_t pin_mv_sum = 0;
    /* The 100 nF capacitor on BAT_ADC is allowed to settle with one throwaway
     * conversion. The remaining conversions reduce ADC noise without a task. */
    int raw = 0;
    if (adc_oneshot_read(s_adc, RLCD42_BATTERY_ADC_CHANNEL, &raw) != ESP_OK)
        return false;

    for (unsigned i = 0; i < RLCD42_BATTERY_SAMPLES; ++i) {
        int pin_mv = 0;
        esp_err_t err = adc_oneshot_read(s_adc, RLCD42_BATTERY_ADC_CHANNEL, &raw);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "battery ADC read failed: %s", esp_err_to_name(err));
            return false;
        }
        err = adc_cali_raw_to_voltage(s_calibration, raw, &pin_mv);
        if (err != ESP_OK || pin_mv < 0) {
            ESP_LOGE(TAG, "battery ADC conversion failed: %s", esp_err_to_name(err));
            return false;
        }
        raw_sum += (uint32_t)raw;
        pin_mv_sum += (uint32_t)pin_mv;
    }

    const uint32_t millivolts =
        (pin_mv_sum * RLCD42_BATTERY_DIVIDER + RLCD42_BATTERY_SAMPLES / 2u) /
        RLCD42_BATTERY_SAMPLES;
    status->raw = (uint16_t)((raw_sum + RLCD42_BATTERY_SAMPLES / 2u) /
                            RLCD42_BATTERY_SAMPLES);
    status->millivolts = millivolts > UINT16_MAX ? UINT16_MAX : (uint16_t)millivolts;
    /* A successful calibrated conversion is always reportable, including a
     * suspiciously low value. Hiding it behind a "cell detected" threshold
     * would make first-device bring-up less safe and would still not prove
     * whether a cell is installed. */
    status->voltage_available = true;
    status->percent = battery_percent(millivolts);
    /* This is advisory telemetry only. BAT_ADC cannot distinguish a missing
     * cell, USB charging, or the active power source, so it must not authorize
     * or inhibit GPIO46. The board's hardware power/protection path remains
     * responsible for battery operation. */
    status->in_expected_range =
        millivolts >= RLCD42_BATTERY_EXPECTED_MIN_MV &&
        millivolts <= RLCD42_BATTERY_EXPECTED_MAX_MV;
    return true;
}
