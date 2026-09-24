/*
 * SPDX-FileCopyrightText: 2026 Waveshare
 * SPDX-FileCopyrightText: 2026 RLCD42 sanoTTS demo contributors
 * SPDX-License-Identifier: Apache-2.0
 *
 * Adapted from Waveshare ESP32-S3-RLCD-4.2 example revision eb1f6342.
 * Modified for a 1-bit PSRAM framebuffer, chunked DMA, locking, a compact
 * status renderer, and a throttled mouth animation. See NOTICE.md.
 */
#include "rlcd42_display.h"

#include <stddef.h>
#include <stdio.h>
#include <string.h>

#include "driver/gpio.h"
#include "driver/spi_master.h"
#include "esp_attr.h"
#include "esp_err.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"

#include "rlcd42_board.h"
#include "voice_ui.h"

/* The panel is a write-only ST7305 reflective monochrome LCD. It is not an
 * RGB panel: the complete logical image is exactly 400*300/8 = 15,000 bytes. */
#define RLCD_WIDTH       400
#define RLCD_HEIGHT      300
#define RLCD_FB_BYTES    (RLCD_WIDTH * RLCD_HEIGHT / 8)
#define RLCD_SPI_HOST    SPI3_HOST
#define RLCD_SPI_HZ      (10 * 1000 * 1000)
#define RLCD_DMA_BYTES   512

#define RLCD_PIN_DC      GPIO_NUM_5
#define RLCD_PIN_CS      GPIO_NUM_40
#define RLCD_PIN_SCLK    GPIO_NUM_11
#define RLCD_PIN_MOSI    GPIO_NUM_12
#define RLCD_PIN_RESET   GPIO_NUM_41

#define PIXEL_BLACK 0
#define PIXEL_WHITE 1
#define LEVEL_UNSET 0xFE
#define LEVEL_IDLE  0xFF

_Static_assert(RLCD_FB_BYTES == 15000, "unexpected ST7305 framebuffer size");
_Static_assert(RLCD_PIN_DC != RLCD_PIN_CS &&
               RLCD_PIN_DC != RLCD_PIN_SCLK &&
               RLCD_PIN_DC != RLCD_PIN_MOSI &&
               RLCD_PIN_DC != RLCD_PIN_RESET &&
               RLCD_PIN_CS != RLCD_PIN_SCLK &&
               RLCD_PIN_CS != RLCD_PIN_MOSI &&
               RLCD_PIN_CS != RLCD_PIN_RESET &&
               RLCD_PIN_SCLK != RLCD_PIN_MOSI &&
               RLCD_PIN_SCLK != RLCD_PIN_RESET &&
               RLCD_PIN_MOSI != RLCD_PIN_RESET,
               "duplicate ST7305 GPIO assignment");

#define TAG "rlcd42_display"
static spi_device_handle_t s_spi;
static SemaphoreHandle_t s_lock;
EXT_RAM_BSS_ATTR static uint8_t s_framebuffer[RLCD_FB_BYTES];
static uint8_t *s_dma;
static uint8_t s_last_level = LEVEL_IDLE;
static uint8_t s_last_flush_bucket;
typedef enum {
    UI_STARTING,
    UI_READY,
    UI_SPEAKING,
    UI_PROBE,
    UI_ERROR,
} ui_state_t;
static ui_state_t s_ui_state = UI_STARTING;
static char s_battery_summary[24] = "BAT ADC WAIT";
static char s_error_detail[32];
static voice_ui s_view;
static int64_t s_page_time;
static int64_t s_caption_idle_time;

static bool display_is_ready(void)
{
    return s_spi && s_lock && s_dma;
}

static esp_err_t spi_tx_bytes(const uint8_t *data, size_t length)
{
    while (length > 0) {
        size_t chunk = length > RLCD_DMA_BYTES ? RLCD_DMA_BYTES : length;
        memcpy(s_dma, data, chunk);
        spi_transaction_t transaction = {
            .length = chunk * 8,
            .tx_buffer = s_dma,
        };
        esp_err_t err = spi_device_polling_transmit(s_spi, &transaction);
        if (err != ESP_OK) return err;
        data += chunk;
        length -= chunk;
    }
    return ESP_OK;
}

static esp_err_t write_command(uint8_t command, const uint8_t *data, size_t length)
{
    gpio_set_level(RLCD_PIN_CS, 0);
    gpio_set_level(RLCD_PIN_DC, 0);
    esp_err_t err = spi_tx_bytes(&command, 1);
    if (err == ESP_OK && length > 0) {
        gpio_set_level(RLCD_PIN_DC, 1);
        err = spi_tx_bytes(data, length);
    }
    gpio_set_level(RLCD_PIN_CS, 1);
    return err;
}

static esp_err_t initialize_panel(void)
{
    gpio_set_level(RLCD_PIN_RESET, 1);
    vTaskDelay(pdMS_TO_TICKS(50));
    gpio_set_level(RLCD_PIN_RESET, 0);
    vTaskDelay(pdMS_TO_TICKS(20));
    gpio_set_level(RLCD_PIN_RESET, 1);
    vTaskDelay(pdMS_TO_TICKS(50));

    /* Exact ST7305 sequence from Waveshare's ESP-IDF example for this board. */
    static const uint8_t d6[] = {0x17, 0x02};
    static const uint8_t d1[] = {0x01};
    static const uint8_t c0[] = {0x11, 0x04};
    static const uint8_t c1[] = {0x69, 0x69, 0x69, 0x69};
    static const uint8_t c2[] = {0x19, 0x19, 0x19, 0x19};
    static const uint8_t c4[] = {0x4B, 0x4B, 0x4B, 0x4B};
    static const uint8_t d8[] = {0x80, 0xE9};
    static const uint8_t b2[] = {0x02};
    static const uint8_t b3[] = {
        0xE5, 0xF6, 0x05, 0x46, 0x77, 0x77, 0x77, 0x77, 0x76, 0x45,
    };
    static const uint8_t b4[] = {
        0x05, 0x46, 0x77, 0x77, 0x77, 0x77, 0x76, 0x45,
    };
    static const uint8_t gate_timing[] = {0x32, 0x03, 0x1F};
    static const uint8_t b7[] = {0x13};
    static const uint8_t b0[] = {0x64};
    static const uint8_t c9[] = {0x00};
    static const uint8_t madctl[] = {0x48};
    static const uint8_t pixel_format[] = {0x11};
    static const uint8_t b9[] = {0x20};
    static const uint8_t b8[] = {0x29};
    static const uint8_t column_window[] = {0x12, 0x2A};
    static const uint8_t page_window[] = {0x00, 0xC7};
    static const uint8_t te[] = {0x00};
    static const uint8_t d0[] = {0xFF};

    const struct {
        uint8_t command;
        const uint8_t *data;
        size_t length;
    } sequence[] = {
        {0xD6, d6, sizeof d6},
        {0xD1, d1, sizeof d1},
        {0xC0, c0, sizeof c0},
        {0xC1, c1, sizeof c1},
        {0xC2, c2, sizeof c2},
        {0xC4, c4, sizeof c4},
        {0xC5, c2, sizeof c2},
        {0xD8, d8, sizeof d8},
        {0xB2, b2, sizeof b2},
        {0xB3, b3, sizeof b3},
        {0xB4, b4, sizeof b4},
        {0x62, gate_timing, sizeof gate_timing},
        {0xB7, b7, sizeof b7},
        {0xB0, b0, sizeof b0},
    };
    for (size_t i = 0; i < sizeof sequence / sizeof sequence[0]; ++i) {
        esp_err_t err = write_command(sequence[i].command,
                                      sequence[i].data, sequence[i].length);
        if (err != ESP_OK) return err;
    }

    esp_err_t err = write_command(0x11, NULL, 0);
    if (err != ESP_OK) return err;
    vTaskDelay(pdMS_TO_TICKS(200));

    const struct {
        uint8_t command;
        const uint8_t *data;
        size_t length;
    } tail[] = {
        {0xC9, c9, sizeof c9},
        {0x36, madctl, sizeof madctl},
        {0x3A, pixel_format, sizeof pixel_format},
        {0xB9, b9, sizeof b9},
        {0xB8, b8, sizeof b8},
        {0x21, NULL, 0},
        {0x2A, column_window, sizeof column_window},
        {0x2B, page_window, sizeof page_window},
        {0x35, te, sizeof te},
        {0xD0, d0, sizeof d0},
        {0x38, NULL, 0},
        {0x29, NULL, 0},
    };
    for (size_t i = 0; i < sizeof tail / sizeof tail[0]; ++i) {
        err = write_command(tail[i].command, tail[i].data, tail[i].length);
        if (err != ESP_OK) return err;
    }
    return ESP_OK;
}

static void set_pixel(int x, int y, int color)
{
    if ((unsigned)x >= RLCD_WIDTH || (unsigned)y >= RLCD_HEIGHT) return;

    /* ST7305 landscape packing used by Waveshare's 400x300 example: each byte
     * describes two X positions by four inverted-Y positions. */
    const int inverted_y = RLCD_HEIGHT - 1 - y;
    const size_t index = (size_t)(x >> 1) * (RLCD_HEIGHT >> 2) +
                         (size_t)(inverted_y >> 2);
    const unsigned bit = 7u - (unsigned)(((inverted_y & 3) << 1) | (x & 1));
    const uint8_t mask = (uint8_t)(1u << bit);
    if (color == PIXEL_WHITE) s_framebuffer[index] |= mask;
    else s_framebuffer[index] &= (uint8_t)~mask;
}

static void fill_rectangle(int x, int y, int width, int height, int color)
{
    if (x < 0) { width += x; x = 0; }
    if (y < 0) { height += y; y = 0; }
    if (x + width > RLCD_WIDTH) width = RLCD_WIDTH - x;
    if (y + height > RLCD_HEIGHT) height = RLCD_HEIGHT - y;
    if (width <= 0 || height <= 0) return;

    for (int row = y; row < y + height; ++row) {
        for (int column = x; column < x + width; ++column)
            set_pixel(column, row, color);
    }
}

/* Compact 5x7 font. The demo intentionally renders only short ASCII status
 * strings so no LVGL or large font component is linked into the kanji build. */
static const uint8_t *glyph(char character)
{
    static const uint8_t blank[5] = {0, 0, 0, 0, 0};
    static const uint8_t letters[26][5] = {
        {0x7E,0x11,0x11,0x11,0x7E}, {0x7F,0x49,0x49,0x49,0x36},
        {0x3E,0x41,0x41,0x41,0x22}, {0x7F,0x41,0x41,0x22,0x1C},
        {0x7F,0x49,0x49,0x49,0x41}, {0x7F,0x09,0x09,0x09,0x01},
        {0x3E,0x41,0x49,0x49,0x7A}, {0x7F,0x08,0x08,0x08,0x7F},
        {0x00,0x41,0x7F,0x41,0x00}, {0x20,0x40,0x41,0x3F,0x01},
        {0x7F,0x08,0x14,0x22,0x41}, {0x7F,0x40,0x40,0x40,0x40},
        {0x7F,0x02,0x0C,0x02,0x7F}, {0x7F,0x04,0x08,0x10,0x7F},
        {0x3E,0x41,0x41,0x41,0x3E}, {0x7F,0x09,0x09,0x09,0x06},
        {0x3E,0x41,0x51,0x21,0x5E}, {0x7F,0x09,0x19,0x29,0x46},
        {0x46,0x49,0x49,0x49,0x31}, {0x01,0x01,0x7F,0x01,0x01},
        {0x3F,0x40,0x40,0x40,0x3F}, {0x1F,0x20,0x40,0x20,0x1F},
        {0x3F,0x40,0x38,0x40,0x3F}, {0x63,0x14,0x08,0x14,0x63},
        {0x07,0x08,0x70,0x08,0x07}, {0x61,0x51,0x49,0x45,0x43},
    };
    static const uint8_t digits[10][5] = {
        {0x3E,0x51,0x49,0x45,0x3E}, {0x00,0x42,0x7F,0x40,0x00},
        {0x42,0x61,0x51,0x49,0x46}, {0x21,0x41,0x45,0x4B,0x31},
        {0x18,0x14,0x12,0x7F,0x10}, {0x27,0x45,0x45,0x45,0x39},
        {0x3C,0x4A,0x49,0x49,0x30}, {0x01,0x71,0x09,0x05,0x03},
        {0x36,0x49,0x49,0x49,0x36}, {0x06,0x49,0x49,0x29,0x1E},
    };
    static const uint8_t dash[5] = {0x08,0x08,0x08,0x08,0x08};
    static const uint8_t dot[5] = {0x00,0x60,0x60,0x00,0x00};
    static const uint8_t colon[5] = {0x00,0x36,0x36,0x00,0x00};
    static const uint8_t slash[5] = {0x20,0x10,0x08,0x04,0x02};

    if (character >= 'a' && character <= 'z') character -= ('a' - 'A');
    if (character >= 'A' && character <= 'Z') return letters[character - 'A'];
    if (character >= '0' && character <= '9') return digits[character - '0'];
    if (character == '-') return dash;
    if (character == '.') return dot;
    if (character == ':') return colon;
    if (character == '/') return slash;
    return blank;
}

static void draw_text(int x, int y, const char *text, int scale, int color)
{
    if (!text || scale <= 0) return;
    while (*text && x + 5 * scale <= RLCD_WIDTH) {
        const uint8_t *columns = glyph(*text++);
        for (int column = 0; column < 5; ++column) {
            for (int row = 0; row < 7; ++row) {
                if (columns[column] & (1u << row)) {
                    fill_rectangle(x + column * scale, y + row * scale,
                                   scale, scale, color);
                }
            }
        }
        x += 6 * scale;
    }
}

static void draw_text_centered(int y, const char *text, int scale, int color)
{
    const size_t length = text ? strlen(text) : 0;
    const int width = length > 0 ? (int)((length * 6 - 1) * (size_t)scale) : 0;
    int x = (RLCD_WIDTH - width) / 2;
    if (x < 0) x = 0;
    draw_text(x, y, text, scale, color);
}

static void draw_mouth(uint8_t level, bool speaking)
{
    voice_ui_mouth(s_framebuffer,level,speaking);
}

static void draw_status(const char *status, const char *detail)
{
    (void)detail;
    voice_ui_copy(s_view.status,sizeof(s_view.status),status);
    voice_ui_copy(s_view.battery,sizeof(s_view.battery),s_battery_summary);
    voice_ui_draw(s_framebuffer,&s_view);
}

static void draw_current_status(void)
{
    char detail[48];
    switch (s_ui_state) {
    case UI_READY:
        (void)snprintf(detail, sizeof detail, "%s KEY:ECHO BOOT:CHAT", s_battery_summary);
        draw_status("VOICE READY", detail);
        break;
    case UI_SPEAKING:
        draw_status("TTS SPEAKING", s_battery_summary);
        break;
    case UI_PROBE:
        (void)snprintf(detail, sizeof detail, "%s / PA OFF", s_battery_summary);
        draw_status("PROBE READY", detail);
        break;
    case UI_ERROR:
        draw_status(s_error_detail, s_error_detail);
        break;
    case UI_STARTING:
    default:
        draw_status("TTS STARTING", s_battery_summary);
        break;
    }
}

static void draw_base_screen(void)
{
    memset(&s_view,0,sizeof(s_view));
    s_ui_state = UI_STARTING;
    draw_current_status();
}

static esp_err_t flush_framebuffer(void)
{
    static const uint8_t column_window[] = {0x12, 0x2A};
    static const uint8_t page_window[] = {0x00, 0xC7};
    esp_err_t err = write_command(0x2A, column_window, sizeof column_window);
    if (err == ESP_OK) err = write_command(0x2B, page_window, sizeof page_window);
    if (err != ESP_OK) return err;

    const uint8_t write_memory = 0x2C;
    gpio_set_level(RLCD_PIN_CS, 0);
    gpio_set_level(RLCD_PIN_DC, 0);
    err = spi_tx_bytes(&write_memory, 1);
    if (err == ESP_OK) {
        gpio_set_level(RLCD_PIN_DC, 1);
        err = spi_tx_bytes(s_framebuffer, RLCD_FB_BYTES);
    }
    gpio_set_level(RLCD_PIN_CS, 1);
    return err;
}

static bool lock_display(void)
{
    return s_lock && xSemaphoreTake(s_lock, pdMS_TO_TICKS(500)) == pdTRUE;
}

static void unlock_display(void)
{
    xSemaphoreGive(s_lock);
}

static bool flush_and_log_error(void)
{
    esp_err_t err = flush_framebuffer();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "ST7305 transfer failed: %s", esp_err_to_name(err));
        return false;
    }
    return true;
}

static void cleanup_failed_init(bool spi_bus_owned)
{
    if (s_spi) {
        (void)spi_bus_remove_device(s_spi);
        s_spi = NULL;
    }
    if (spi_bus_owned) {
        (void)spi_bus_free(RLCD_SPI_HOST);
    }
    if (s_dma) {
        heap_caps_free(s_dma);
        s_dma = NULL;
    }
    if (s_lock) {
        vSemaphoreDelete(s_lock);
        s_lock = NULL;
    }
}

bool rlcd42_display_init(void)
{
    if (display_is_ready()) return true;
    if (!rlcd42_board_init()) return false;
    bool spi_bus_owned = false;

    s_lock = xSemaphoreCreateMutex();
    s_dma = heap_caps_malloc(RLCD_DMA_BYTES,
                             MALLOC_CAP_DMA | MALLOC_CAP_INTERNAL);
    if (!s_lock || !s_dma) {
        ESP_LOGE(TAG, "display resource allocation failed (DMA=%d B)",
                 RLCD_DMA_BYTES);
        cleanup_failed_init(spi_bus_owned);
        return false;
    }

    /* Preload inactive levels before enabling the output drivers. */
    gpio_set_level(RLCD_PIN_CS, 1);
    gpio_set_level(RLCD_PIN_DC, 1);
    gpio_set_level(RLCD_PIN_RESET, 1);
    const gpio_config_t output_cfg = {
        .pin_bit_mask = (1ULL << RLCD_PIN_CS) |
                        (1ULL << RLCD_PIN_DC) |
                        (1ULL << RLCD_PIN_RESET),
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    if (gpio_config(&output_cfg) != ESP_OK) {
        ESP_LOGE(TAG, "display control GPIO configuration failed");
        cleanup_failed_init(spi_bus_owned);
        return false;
    }

    const spi_bus_config_t bus_cfg = {
        .mosi_io_num = RLCD_PIN_MOSI,
        .miso_io_num = GPIO_NUM_NC,
        .sclk_io_num = RLCD_PIN_SCLK,
        .quadwp_io_num = GPIO_NUM_NC,
        .quadhd_io_num = GPIO_NUM_NC,
        .max_transfer_sz = RLCD_DMA_BYTES,
    };
    esp_err_t err = spi_bus_initialize(RLCD_SPI_HOST, &bus_cfg, SPI_DMA_CH_AUTO);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "SPI bus initialization failed: %s", esp_err_to_name(err));
        cleanup_failed_init(spi_bus_owned);
        return false;
    }
    spi_bus_owned = true;

    const spi_device_interface_config_t device_cfg = {
        .clock_speed_hz = RLCD_SPI_HZ,
        .mode = 0,
        .spics_io_num = GPIO_NUM_NC, /* CS stays asserted across DMA chunks. */
        .queue_size = 1,
    };
    err = spi_bus_add_device(RLCD_SPI_HOST, &device_cfg, &s_spi);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "ST7305 SPI device creation failed: %s", esp_err_to_name(err));
        cleanup_failed_init(spi_bus_owned);
        return false;
    }

    if (!lock_display()) {
        ESP_LOGE(TAG, "display lock failed during initialization");
        cleanup_failed_init(spi_bus_owned);
        return false;
    }
    err = initialize_panel();
    if (err == ESP_OK) {
        draw_base_screen();
        err = flush_framebuffer();
    }
    unlock_display();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "ST7305 initialization failed: %s", esp_err_to_name(err));
        cleanup_failed_init(spi_bus_owned);
        return false;
    }

    ESP_LOGI(TAG, "ST7305 ready: 400x300 1-bit, SPI mode 0 at %d MHz, "
                  "%d B PSRAM framebuffer, %d B internal DMA chunk",
             RLCD_SPI_HZ / 1000000, RLCD_FB_BYTES, RLCD_DMA_BYTES);
    return true;
}

void rlcd42_display_set_ready(void)
{
    if (!display_is_ready() || !lock_display()) return;
    s_last_level = LEVEL_IDLE;
    s_ui_state = UI_READY;
    s_caption_idle_time=esp_timer_get_time();
    draw_mouth(0, false);
    draw_current_status();
    (void)flush_and_log_error();
    unlock_display();
}
void rlcd42_display_status(const char *title)
{
    if (!display_is_ready() || !lock_display()) return;
    s_last_level=LEVEL_IDLE;
    draw_mouth(0,false);
    draw_status(title,s_battery_summary);
    (void)flush_and_log_error();
    unlock_display();
}

void rlcd42_display_begin(bool reply) {
    if(!display_is_ready() || !lock_display())return;
    s_view.reply=reply;s_view.heard[0]=0;s_view.spoken[0]=0;s_view.page=0;
    s_view.captions=false;
    s_page_time=esp_timer_get_time();s_ui_state=UI_READY;
    draw_current_status();(void)flush_and_log_error();unlock_display();
}
void rlcd42_display_heard(const char *text) {
    if(!display_is_ready() || !lock_display())return;
    voice_ui_copy(s_view.heard,sizeof(s_view.heard),text);
    s_view.captions=true;
    s_view.page=0;s_page_time=esp_timer_get_time();
    voice_ui_draw(s_framebuffer,&s_view);(void)flush_and_log_error();unlock_display();
}
void rlcd42_display_spoken(const char *text) {
    if(!display_is_ready() || !lock_display())return;
    voice_ui_copy(s_view.spoken,sizeof(s_view.spoken),text);
    s_view.captions=true;
    s_view.page=0;s_page_time=esp_timer_get_time();
    voice_ui_draw(s_framebuffer,&s_view);(void)flush_and_log_error();unlock_display();
}
void rlcd42_display_tick(void) {
    if(!display_is_ready() || esp_timer_get_time()-s_page_time<4000000 || !lock_display())return;
    unsigned pages=voice_ui_pages(s_view.spoken[0]?s_view.spoken:s_view.heard);
    int64_t linger=(int64_t)(pages>2?pages:2)*4000000;
    if(s_ui_state==UI_READY && s_view.captions) {
        if(esp_timer_get_time()-s_caption_idle_time>=linger)s_view.captions=false;
        else if(pages>1)s_view.page++;
        voice_ui_draw(s_framebuffer,&s_view);(void)flush_and_log_error();
    }
    s_page_time=esp_timer_get_time();unlock_display();
}

void rlcd42_display_show_probe_pattern(void)
{
    if (!display_is_ready() || !lock_display()) return;
    memset(s_framebuffer, 0xFF, RLCD_FB_BYTES);
    fill_rectangle(0, 0, RLCD_WIDTH, 5, PIXEL_BLACK);
    fill_rectangle(0, RLCD_HEIGHT - 5, RLCD_WIDTH, 5, PIXEL_BLACK);
    fill_rectangle(0, 0, 5, RLCD_HEIGHT, PIXEL_BLACK);
    fill_rectangle(RLCD_WIDTH - 5, 0, 5, RLCD_HEIGHT, PIXEL_BLACK);
    fill_rectangle(12, 12, 64, 64, PIXEL_BLACK);
    fill_rectangle(24, 24, 40, 40, PIXEL_WHITE);
    draw_text(96, 24, "TOP", 5, PIXEL_BLACK);
    draw_text_centered(108, "RLCD PROBE", 4, PIXEL_BLACK);
    for (int x = 24; x < RLCD_WIDTH - 24; x += 32)
        fill_rectangle(x, 174, 16, 38, PIXEL_BLACK);
    s_ui_state = UI_PROBE;
    draw_current_status();
    (void)flush_and_log_error();
    unlock_display();
}

void rlcd42_display_set_battery(const rlcd42_battery_status_t *status)
{
    if (!display_is_ready() || !lock_display()) return;
    if (!status) {
        (void)snprintf(s_battery_summary, sizeof s_battery_summary, "BAT ADC ERR");
    } else if (!status->voltage_available) {
        (void)snprintf(s_battery_summary, sizeof s_battery_summary, "BAT --");
    } else if (!status->in_expected_range) {
        (void)snprintf(s_battery_summary, sizeof s_battery_summary,
                       "BAT CHECK %u.%02uV", status->millivolts / 1000u,
                       (status->millivolts % 1000u) / 10u);
    } else {
        (void)snprintf(s_battery_summary, sizeof s_battery_summary,
                       "BAT %u.%02uV", status->millivolts / 1000u,
                       (status->millivolts % 1000u) / 10u);
    }
    draw_current_status();
    (void)flush_and_log_error();
    unlock_display();
}

void rlcd42_display_set_speaking(bool speaking)
{
    if (!display_is_ready() || !lock_display()) return;
    s_last_level = speaking ? LEVEL_UNSET : LEVEL_IDLE;
    s_ui_state = speaking ? UI_SPEAKING : UI_READY;
    if(!speaking)s_caption_idle_time=esp_timer_get_time();
    draw_mouth(0, speaking);
    draw_current_status();
    (void)flush_and_log_error();
    s_last_flush_bucket = (uint8_t)(esp_timer_get_time() / 200000);
    unlock_display();
}

void rlcd42_display_set_level(uint8_t level)
{
    if (!display_is_ready() || !lock_display()) return;

    /* The display state and flush bucket are shared with the UI state setters.
     * Recheck them under the same mutex so a PCM task cannot redraw a stale
     * speaking mouth after another task has switched back to READY. */
    const uint8_t bucket = (uint8_t)(esp_timer_get_time() / 200000);
    if (s_last_level == LEVEL_IDLE || bucket == s_last_flush_bucket) {
        unlock_display();
        return; /* at most 5 FPS */
    }
    if (s_last_level != LEVEL_UNSET) {
        const int delta = (int)level - (int)s_last_level;
        if (delta > -12 && delta < 12) {
            unlock_display();
            return;
        }
    }
    if (level >= LEVEL_UNSET) level = LEVEL_UNSET - 1;
    s_last_level = level;
    draw_mouth(level, true);
    if (flush_and_log_error()) s_last_flush_bucket = bucket;
    unlock_display();
}

void rlcd42_display_show_error(const char *short_message)
{
    if (!display_is_ready() || !lock_display()) return;
    s_last_level = LEVEL_IDLE;
    s_ui_state = UI_ERROR;
    (void)snprintf(s_error_detail, sizeof s_error_detail, "%s",
                   short_message ? short_message : "UNKNOWN");
    draw_mouth(0, false);
    draw_current_status();
    (void)flush_and_log_error();
    unlock_display();
}
