#include "esp_log.h"

#include "rlcd42_board.h"

#define TAG "rlcd42_entry"

/* Kept in the application image so a raw factory/demo backup can be
 * identified without trusting USB VID/PID (shared by many ESP32-S3 boards). */
__attribute__((used)) static const char s_board_marker[] =
    "rlcd42-sanotts-demo:Waveshare-ESP32-S3-RLCD-4.2";

#if SAAN_KANJI
#define RLCD42_TEXT_PROFILE "kanji"
#else
#define RLCD42_TEXT_PROFILE "kana"
#endif

#if SAAN_SKIP_I2S
#define RLCD42_AUDIO_PROFILE "silent"
#else
#define RLCD42_AUDIO_PROFILE "audio"
#endif

__attribute__((used)) static const char s_profile_marker[] =
    "RLCD42_PROFILE:" RLCD42_TEXT_PROFILE "-" RLCD42_AUDIO_PROFILE;

void saan_upstream_app_main(void);

void app_main(void)
{
    ESP_LOGI(TAG, "safe entry: forcing PA_EN LOW before display/model setup");
    if (!rlcd42_board_init()) {
        ESP_LOGE(TAG, "board safety interlock failed; application will not start");
        return;
    }
    ESP_LOGI(TAG, "%s", s_profile_marker);
    saan_upstream_app_main();
}
