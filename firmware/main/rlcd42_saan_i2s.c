#include "saan_i2s.h"

#include <inttypes.h>
#include <math.h>

#include "driver/i2s_std.h"
#include "esp_codec_dev.h"
#include "esp_codec_dev_defaults.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "rlcd42_board.h"
#include "rlcd42_battery.h"
#include "rlcd42_display.h"
#include "saanotts_stream.h"

/* Waveshare ESP32-S3-RLCD-4.2 schematic (ESP32-S3-WROOM-1-N16R8). */
#define RLCD42_I2S_MCLK GPIO_NUM_16
#define RLCD42_I2S_BCLK GPIO_NUM_9
#define RLCD42_I2S_WS   GPIO_NUM_45
#define RLCD42_I2S_DOUT GPIO_NUM_8
#define RLCD42_I2S_DIN  GPIO_NUM_10

#define AUDIO_DMA_DESC     6
#define AUDIO_DMA_FRAME    512
#define AUDIO_VOLUME       100
#define SPEECH_DURATION_SCALE 1.15f
#define PCM_PLAYBACK_GAIN     1.00f
#define SAAN_I2S_MAXBUF    2048
#define TRANSPORT_CHANNELS 2
#define ES8311_DAC_MUTE_REG   0x31
#define ES8311_DAC_VOLUME_REG 0x32
#define ES8311_DAC_MUTE_MASK  0x60
#define ES8311_VOLUME_ZERO    0x00

/* The board carries an ES7210 input path too, but this demo deliberately does
 * not initialize the microphones. Only MCU -> ES8311 playback is configured. */
_Static_assert(RLCD42_I2S_MCLK == GPIO_NUM_16, "wrong RLCD4.2 MCLK");
_Static_assert(RLCD42_I2S_BCLK == GPIO_NUM_9, "wrong RLCD4.2 BCLK");
_Static_assert(RLCD42_I2S_WS == GPIO_NUM_45, "wrong RLCD4.2 LRCLK");
_Static_assert(RLCD42_I2S_DOUT == GPIO_NUM_8, "wrong RLCD4.2 speaker data pin");
_Static_assert(RLCD42_I2S_DIN == GPIO_NUM_10, "wrong RLCD4.2 microphone data pin");

#define TAG "rlcd42_audio"

#if !SAAN_SKIP_I2S
static i2s_chan_handle_t s_tx;
static const audio_codec_data_if_t *s_data_if;
static const audio_codec_ctrl_if_t *s_ctrl_if;
static const audio_codec_gpio_if_t *s_gpio_if;
static const audio_codec_if_t *s_codec_if;
static esp_codec_dev_handle_t s_output;
static bool s_audio_open;
#endif

/* PCM work buffers live in PSRAM. The ES8311 transport uses two slots, so the
 * mono synthesizer output is duplicated to L/R immediately before each write. */
static int16_t *s_stereo;
static int16_t *s_preroll;
static uint64_t s_pcm_fnv = 1469598103934665603ull;
static uint64_t s_pcm_sqsum;
static uint32_t s_clips;
static uint32_t s_pcm_n;
static size_t s_preroll_fill;
static uint16_t s_pcm_absmax;
static bool s_utterance_transport_ok;
static rlcd42_battery_status_t s_battery;
static bool s_battery_valid;

static bool refresh_battery(void)
{
    rlcd42_battery_status_t status;
    if (!rlcd42_battery_read(&status)) {
        s_battery_valid = false;
        rlcd42_display_set_battery(NULL);
        ESP_LOGE(TAG, "battery ADC read failed");
        return false;
    }
    s_battery = status;
    s_battery_valid = true;
    rlcd42_display_set_battery(&status);
    if (!status.voltage_available) {
        ESP_LOGI(TAG, "BAT_ADC raw=%u; VBAT voltage unavailable; power source cannot be distinguished",
                 status.raw);
    } else {
        ESP_LOGI(TAG, "VBAT=%u mV (raw=%u, estimated %u%%, expected range=%s)",
                 status.millivolts, status.raw, status.percent,
                 status.in_expected_range ? "OK" : "CHECK");
        if (!status.in_expected_range)
            ESP_LOGW(TAG, "VBAT is outside the expected 3.00-4.20 V reporting range");
    }
    return true;
}

static uint8_t pcm_level(const int16_t *pcm, size_t samples)
{
    int32_t peak = 0;
    for (size_t i = 0; i < samples; ++i) {
        int32_t value = pcm[i];
        if (value < 0) value = -value;
        if (value > peak) peak = value;
    }
    if (peak > 12000) peak = 12000;
    return (uint8_t)(peak * 255 / 12000);
}

#if !SAAN_SKIP_I2S
static bool codec_volume_is(uint8_t expected, const char *phase)
{
    int value = -1;
    const int err = esp_codec_dev_read_reg(s_output, ES8311_DAC_VOLUME_REG, &value);
    if (err != ESP_CODEC_DEV_OK || (value & 0xFF) != expected) {
        ESP_LOGE(TAG, "ES8311 volume readback failed at %s: err=%d reg32=0x%02x expected=0x%02x",
                 phase, err, value & 0xFF, expected);
        s_utterance_transport_ok = false;
        return false;
    }
    return true;
}

static bool codec_mute_is(bool muted, const char *phase)
{
    int value = -1;
    const int err = esp_codec_dev_read_reg(s_output, ES8311_DAC_MUTE_REG, &value);
    const uint8_t expected = muted ? ES8311_DAC_MUTE_MASK : 0;
    if (err != ESP_CODEC_DEV_OK ||
        ((uint8_t)value & ES8311_DAC_MUTE_MASK) != expected) {
        ESP_LOGE(TAG, "ES8311 mute readback failed at %s: err=%d reg31=0x%02x expected-mask=0x%02x",
                 phase, err, value & 0xFF, expected);
        s_utterance_transport_ok = false;
        return false;
    }
    return true;
}

static void destroy_codec_objects(void)
{
    s_audio_open = false;
    if (s_output) {
        esp_codec_dev_delete(s_output);
        s_output = NULL;
    }
    if (s_codec_if) {
        (void)audio_codec_delete_codec_if(s_codec_if);
        s_codec_if = NULL;
    }
    if (s_gpio_if) {
        (void)audio_codec_delete_gpio_if(s_gpio_if);
        s_gpio_if = NULL;
    }
    if (s_ctrl_if) {
        (void)audio_codec_delete_ctrl_if(s_ctrl_if);
        s_ctrl_if = NULL;
    }
}
#endif

static bool write_mono(const int16_t *pcm, size_t samples)
{
    if (samples > SAAN_I2S_MAXBUF) {
        ESP_LOGE(TAG, "refusing %u mono samples; work buffer holds %u",
                 (unsigned)samples, (unsigned)SAAN_I2S_MAXBUF);
        s_utterance_transport_ok = false;
        return false;
    }
    rlcd42_display_set_level(pcm_level(pcm, samples));
#if SAAN_SKIP_I2S
    (void)pcm;
    (void)samples;
    return true;
#else
    if (!s_audio_open || !s_output || !s_stereo) {
        ESP_LOGE(TAG, "audio codec is not open");
        s_utterance_transport_ok = false;
        return false;
    }
    /* Expand backwards so pcm may point at the first half of s_stereo. */
    for (size_t i = samples; i-- > 0;) {
        const int16_t value = pcm[i];
        s_stereo[2 * i] = value;
        s_stereo[2 * i + 1] = value;
    }
    const size_t bytes = samples * TRANSPORT_CHANNELS * sizeof(int16_t);
    int err = esp_codec_dev_write(s_output, s_stereo, bytes);
    if (err != ESP_CODEC_DEV_OK) {
        ESP_LOGE(TAG, "esp_codec_dev_write failed: %d", err);
        s_utterance_transport_ok = false;
        return false;
    }
    return true;
#endif
}

static bool write_mono_chunks(const int16_t *pcm, size_t samples)
{
    while (samples > 0) {
        const size_t count = samples > SAAN_I2S_MAXBUF ? SAAN_I2S_MAXBUF : samples;
        if (!write_mono(pcm, count)) return false;
        pcm += count;
        samples -= count;
    }
    return true;
}

int16_t saan_f32_to_i16(float x)
{
    /* Keep the generated PCM at unity gain. The codec is already at the
     * official factory volume ceiling, and software boost sounded distorted
     * on the physical RLCD4.2 speaker even without numerical clipping. */
    long value = lrintf(x * PCM_PLAYBACK_GAIN * 32767.0f);
    if (value > 32767) {
        value = 32767;
        ++s_clips;
    } else if (value < -32768) {
        value = -32768;
        ++s_clips;
    }

    const uint16_t u = (uint16_t)(int16_t)value;
    s_pcm_fnv = (s_pcm_fnv ^ (uint8_t)(u & 0xFFu)) * 1099511628211ull;
    s_pcm_fnv = (s_pcm_fnv ^ (uint8_t)(u >> 8)) * 1099511628211ull;
    int32_t absolute = value < 0 ? -(int32_t)value : (int32_t)value;
    if (absolute > s_pcm_absmax) s_pcm_absmax = absolute;
    s_pcm_sqsum += (uint64_t)((int64_t)value * (int64_t)value);
    ++s_pcm_n;
    return (int16_t)value;
}

void saan_i2s_pcm_reset(void)
{
    s_pcm_fnv = 1469598103934665603ull;
    s_pcm_n = 0;
    s_pcm_absmax = 0;
    s_pcm_sqsum = 0;
    s_clips = 0;
    s_preroll_fill = 0;
    s_utterance_transport_ok = true;
}

/* main.c is compiled with saan_stream_pull renamed to this wrapper. That keeps
 * the pinned upstream submodule byte-for-byte intact while ensuring a core
 * synthesis failure cannot be mistaken for successful audio transport. */
saan_status rlcd42_saan_stream_pull(saan_stream *stream, float *pcm, int32_t *frames)
{
    const saan_status status = saan_stream_pull(stream, pcm, frames);
    if (status != SAAN_OK) s_utterance_transport_ok = false;
    return status;
}

saan_status rlcd42_saan_stream_init(saan_stream *stream, const saan_weights *weights,
                                    saan_arena *arena, const int32_t *ids,
                                    int32_t id_count, float duration_scale)
{
    /* Scale the model's per-token duration rather than lowering the I2S sample
     * rate. This slows delivery without lowering the voice pitch. */
    return saan_stream_init(stream, weights, arena, ids, id_count,
                            duration_scale * SPEECH_DURATION_SCALE);
}

uint32_t saan_i2s_clip_count(void) { return s_clips; }
uint64_t saan_i2s_pcm_checksum(void) { return s_pcm_fnv; }
uint32_t saan_i2s_pcm_samples(void) { return s_pcm_n; }
int32_t saan_i2s_pcm_absmax(void) { return (int32_t)s_pcm_absmax; }
uint64_t saan_i2s_pcm_sqsum(void) { return s_pcm_sqsum; }

bool saan_i2s_setup(uint32_t sample_rate)
{
    if (!rlcd42_board_init()) {
        ESP_LOGE(TAG, "RLCD4.2 safety initialization failed; PA remains off");
        return false;
    }
    if (!rlcd42_battery_init() || !refresh_battery()) {
        s_battery_valid = false;
        ESP_LOGW(TAG, "battery telemetry unavailable; USB/audio operation will continue");
    }
    if (!s_stereo) {
        s_stereo = heap_caps_malloc(SAAN_I2S_MAXBUF * TRANSPORT_CHANNELS * sizeof(*s_stereo),
                                    MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    }
    if (!s_preroll) {
        s_preroll = heap_caps_malloc(SAAN_I2S_PREROLL_SAMPLES * sizeof(*s_preroll),
                                     MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    }
    if (!s_stereo || !s_preroll) {
        ESP_LOGE(TAG, "could not allocate PCM work buffers in PSRAM");
        return false;
    }
    if (!rlcd42_display_init()) {
        ESP_LOGE(TAG, "display initialization failed; refusing audio and keeping PA LOW");
        return false;
    }
    if (s_battery_valid)
        rlcd42_display_set_battery(&s_battery);
    else
        rlcd42_display_set_battery(NULL);
    rlcd42_display_set_ready();

#if SAAN_SKIP_I2S
    ESP_LOGW(TAG, "SAAN_SKIP_I2S=1: PCM is measured; ES8311/I2S/PA stay disabled");
    return true;
#else
    if (!rlcd42_board_i2c_present(0x18)) {
        ESP_LOGE(TAG, "ES8311 was not detected at I2C address 0x18; refusing audio");
        return false;
    }
    i2s_chan_config_t channel = I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_0, I2S_ROLE_MASTER);
    channel.dma_desc_num = AUDIO_DMA_DESC;
    channel.dma_frame_num = AUDIO_DMA_FRAME;
    channel.auto_clear = true;
    esp_err_t err = i2s_new_channel(&channel, &s_tx, NULL);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "i2s_new_channel: %s", esp_err_to_name(err));
        return false;
    }

    i2s_std_config_t config = {
        .clk_cfg = I2S_STD_CLK_DEFAULT_CONFIG(sample_rate),
        .slot_cfg = I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_16BIT,
                                                        I2S_SLOT_MODE_STEREO),
        .gpio_cfg = {
            .mclk = RLCD42_I2S_MCLK,
            .bclk = RLCD42_I2S_BCLK,
            .ws = RLCD42_I2S_WS,
            .dout = RLCD42_I2S_DOUT,
            .din = I2S_GPIO_UNUSED,
            .invert_flags = {
                .mclk_inv = false,
                .bclk_inv = false,
                .ws_inv = false,
            },
        },
    };
    config.clk_cfg.mclk_multiple = I2S_MCLK_MULTIPLE_256;
    err = i2s_channel_init_std_mode(s_tx, &config);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "I2S initialization: %s", esp_err_to_name(err));
        return false;
    }

    audio_codec_i2s_cfg_t i2s_cfg = {
        .port = I2S_NUM_0,
        .rx_handle = NULL,
        .tx_handle = s_tx,
    };
    s_data_if = audio_codec_new_i2s_data(&i2s_cfg);
    if (!s_data_if) {
        ESP_LOGE(TAG, "audio_codec_new_i2s_data failed");
        return false;
    }
    ESP_LOGI(TAG, "ES8311 transport: %" PRIu32 " Hz / 16-bit / stereo duplicate; "
                  "MCLK=%d BCLK=%d WS=%d DOUT=%d; safe volume=%d%%",
             sample_rate, RLCD42_I2S_MCLK, RLCD42_I2S_BCLK,
             RLCD42_I2S_WS, RLCD42_I2S_DOUT, AUDIO_VOLUME);
    ESP_LOGI(TAG, "speech tuning: duration %.2fx (pitch preserved), PCM gain %.2fx",
             (double)SPEECH_DURATION_SCALE, (double)PCM_PLAYBACK_GAIN);
    ESP_LOGI(TAG, "PA remains LOW until zero prefill and explicit utterance start");
    return true;
#endif
}

bool saan_i2s_preroll_push(const float *pcm, size_t samples)
{
    if ((size_t)s_preroll_fill + samples > SAAN_I2S_PREROLL_SAMPLES) {
        s_utterance_transport_ok = false;
        return false;
    }
    for (size_t i = 0; i < samples; ++i)
        s_preroll[s_preroll_fill + i] = saan_f32_to_i16(pcm[i]);
    s_preroll_fill += samples;
    return true;
}

bool saan_i2s_start(void)
{
#if SAAN_SKIP_I2S
    rlcd42_display_set_speaking(true);
    if (s_preroll_fill && !write_mono_chunks(s_preroll, s_preroll_fill)) return false;
    s_preroll_fill = 0;
    ESP_LOGI(TAG, "RLCD42_SILENT_START:OK");
    return true;
#else
    /* Waveshare's RLCD4.2 codec_board enables I2S before constructing the
     * ES8311 codec because this codec needs MCLK while its reset/clock
     * registers are programmed. PA_EN is still LOW here. esp_codec_dev_open
     * will briefly disable the channel to reconfigure it for 22.05 kHz and
     * then enable it again. Repeat this before every utterance because close()
     * disables the channel. */
    esp_err_t clock_err = i2s_channel_enable(s_tx);
    if (clock_err != ESP_OK) {
        ESP_LOGE(TAG, "could not prime ES8311 MCLK before codec init: %s",
                 esp_err_to_name(clock_err));
        goto codec_fail;
    }
    ESP_LOGI(TAG, "ES8311 MCLK primed before codec reset/config; PA remains LOW");
    vTaskDelay(pdMS_TO_TICKS(1));

    /* esp_codec_dev expects the 8-bit wire address and shifts it for the IDF
     * 7-bit bus API. Keep GPIO46 outside the codec driver: PA sequencing is an
     * explicit board safety invariant. */
    audio_codec_i2c_cfg_t i2c_cfg = {
        .port = I2C_NUM_0,
        .addr = ES8311_CODEC_DEFAULT_ADDR,
        .bus_handle = rlcd42_board_i2c_bus(),
    };
    s_ctrl_if = audio_codec_new_i2c_ctrl(&i2c_cfg);
    s_gpio_if = audio_codec_new_gpio();
    if (!s_ctrl_if || !s_gpio_if) {
        ESP_LOGE(TAG, "ES8311 control interface allocation failed");
        goto codec_fail;
    }
    es8311_codec_cfg_t codec_cfg = {
        .ctrl_if = s_ctrl_if,
        .gpio_if = s_gpio_if,
        .codec_mode = ESP_CODEC_DEV_WORK_MODE_DAC,
        .pa_pin = GPIO_NUM_NC,
        .master_mode = false,
        .use_mclk = true,
        .hw_gain = {
            .pa_gain = 6.0f,
        },
    };
    s_codec_if = es8311_codec_new(&codec_cfg);
    if (!s_codec_if) {
        ESP_LOGE(TAG, "es8311_codec_new failed");
        goto codec_fail;
    }
    esp_codec_dev_cfg_t output_cfg = {
        .dev_type = ESP_CODEC_DEV_TYPE_OUT,
        .codec_if = s_codec_if,
        .data_if = s_data_if,
    };
    s_output = esp_codec_dev_new(&output_cfg);
    if (!s_output) {
        ESP_LOGE(TAG, "esp_codec_dev_new failed");
        goto codec_fail;
    }
    esp_codec_dev_sample_info_t format = {
        .sample_rate = 22050,
        .channel = TRANSPORT_CHANNELS,
        .bits_per_sample = 16,
        .channel_mask = 0,
        .mclk_multiple = 256,
    };
    int err = esp_codec_dev_open(s_output, &format);
    if (err != ESP_CODEC_DEV_OK) {
        ESP_LOGE(TAG, "esp_codec_dev_open failed: %d", err);
        goto codec_fail;
    }
    s_audio_open = true;
    if (esp_codec_dev_set_out_vol(s_output, 0) != ESP_CODEC_DEV_OK) {
        ESP_LOGE(TAG, "could not establish zero ES8311 volume");
        goto codec_fail;
    }
    /* esp_codec_dev 1.5.4 special-cases public volume 0 as -96 dB, which
     * clamps ES8311 REG32 to 0x00. REG31 is verified separately because a
     * zero volume setting is not a substitute for the codec's mute bit. */
    if (!codec_volume_is(ES8311_VOLUME_ZERO, "zero-volume-before-PA")) goto codec_fail;
    if (esp_codec_dev_set_out_mute(s_output, true) != ESP_CODEC_DEV_OK) {
        ESP_LOGE(TAG, "could not mute ES8311 before PA enable");
        goto codec_fail;
    }
    if (!codec_mute_is(true, "mute-before-PA")) goto codec_fail;

    /* Prime the entire configured DMA ring with zeros while PA_EN is LOW. */
    int16_t silence[AUDIO_DMA_FRAME * TRANSPORT_CHANNELS] = {0};
    for (int i = 0; i < AUDIO_DMA_DESC; ++i) {
        if (esp_codec_dev_write(s_output, silence, sizeof silence) != ESP_CODEC_DEV_OK)
            goto codec_fail;
    }
    if (!rlcd42_board_set_amp_enabled(true)) goto codec_fail;
    /* With the pinned esp_codec_dev curve and the configured +6 dB PA gain,
     * even public volumes 2..100 map linearly to REG32 0x58..0xBA. Volume 100
     * is the official Waveshare factory default; its music path uses 90. The
     * sanoTTS reference PCM peaks at about -10.5 dBFS with zero clipping, so
     * this remains below a normalized factory track at volume 90. The setter
     * in esp_codec_dev 1.5.4 discards the ES8311 write error, so every 2-point
     * ramp step is read back directly before playback is accepted. */
    for (int volume = 2; volume <= AUDIO_VOLUME; volume += 2) {
        if (esp_codec_dev_set_out_vol(s_output, volume) != ESP_CODEC_DEV_OK) {
            ESP_LOGE(TAG, "ES8311 volume ramp failed at %d%%", volume);
            goto codec_fail;
        }
        if (!codec_volume_is((uint8_t)(0x56 + volume), "volume-ramp"))
            goto codec_fail;
        vTaskDelay(pdMS_TO_TICKS(3));
    }
    if (esp_codec_dev_set_out_mute(s_output, false) != ESP_CODEC_DEV_OK) {
        ESP_LOGE(TAG, "could not unmute ES8311 after the verified ramp");
        goto codec_fail;
    }
    if (!codec_mute_is(false, "unmute-before-preroll")) goto codec_fail;
    rlcd42_display_set_speaking(true);

    if (s_preroll_fill && !write_mono_chunks(s_preroll, s_preroll_fill)) goto codec_fail;
    s_preroll_fill = 0;
    ESP_LOGI(TAG, "RLCD42_AUDIO_START:OK PA=HIGH VOLUME=%d", AUDIO_VOLUME);
    return true;

codec_fail:
    s_utterance_transport_ok = false;
    (void)rlcd42_board_set_amp_enabled(false);
    if (s_audio_open && s_output)
        (void)esp_codec_dev_close(s_output);
    else if (s_tx)
        (void)i2s_channel_disable(s_tx);
    destroy_codec_objects();
    ESP_LOGE(TAG, "RLCD42_AUDIO_START:FAIL PA=LOW");
    return false;
#endif
}

bool saan_i2s_write_f32(const float *pcm, size_t samples)
{
    while (samples > 0) {
        const size_t count = samples > SAAN_I2S_MAXBUF ? SAAN_I2S_MAXBUF : samples;
        int16_t *mono = s_stereo;
        for (size_t i = 0; i < count; ++i) mono[i] = saan_f32_to_i16(pcm[i]);
        if (!write_mono(mono, count)) return false;
        pcm += count;
        samples -= count;
    }
    return true;
}

void saan_i2s_stop(void)
{
#if !SAAN_SKIP_I2S
    bool shutdown_ok = s_utterance_transport_ok;
    if (s_audio_open && s_output) {
        int16_t silence[AUDIO_DMA_FRAME * TRANSPORT_CHANNELS] = {0};
        for (int i = 0; i < AUDIO_DMA_DESC; ++i) {
            if (esp_codec_dev_write(s_output, silence, sizeof silence) != ESP_CODEC_DEV_OK)
                shutdown_ok = false;
        }
        for (int volume = AUDIO_VOLUME; volume >= 0; volume -= 2) {
            if (esp_codec_dev_set_out_vol(s_output, volume) != ESP_CODEC_DEV_OK)
                shutdown_ok = false;
            vTaskDelay(pdMS_TO_TICKS(2));
        }
        if (esp_codec_dev_set_out_vol(s_output, 0) != ESP_CODEC_DEV_OK)
            shutdown_ok = false;
        if (!codec_volume_is(ES8311_VOLUME_ZERO, "zero-volume-before-PA-off"))
            shutdown_ok = false;
        if (esp_codec_dev_set_out_mute(s_output, true) != ESP_CODEC_DEV_OK)
            shutdown_ok = false;
        if (!codec_mute_is(true, "mute-before-PA-off")) shutdown_ok = false;
        if (!rlcd42_board_set_amp_enabled(false)) shutdown_ok = false;
        if (esp_codec_dev_close(s_output) != ESP_CODEC_DEV_OK) shutdown_ok = false;
    } else {
        if (!rlcd42_board_set_amp_enabled(false))
            shutdown_ok = false;
    }
    if (!rlcd42_board_amp_is_disabled()) shutdown_ok = false;
    if (shutdown_ok)
        ESP_LOGI(TAG, "RLCD42_AUDIO_RESULT:OK PA=LOW");
    else
        ESP_LOGE(TAG, "RLCD42_AUDIO_RESULT:FAIL PA=LOW_REQUESTED");
    destroy_codec_objects();
#else
    if (s_utterance_transport_ok)
        ESP_LOGI(TAG, "RLCD42_SILENT_RESULT:OK PA=COMPILED_OUT");
    else
        ESP_LOGE(TAG, "RLCD42_SILENT_RESULT:FAIL PA=COMPILED_OUT");
#endif
    s_preroll_fill = 0;
    rlcd42_display_set_level(0);
    rlcd42_display_set_speaking(false);
    (void)refresh_battery();
}
