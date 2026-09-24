#ifndef TTS_BRIDGE_H
#define TTS_BRIDGE_H
#include <stdbool.h>
#include "audio_codec_data_if.h"
#include "driver/i2s_std.h"
bool tts_bridge_init(const audio_codec_data_if_t *data);
bool tts_bridge_say(const char *kana,i2s_chan_handle_t tx);
#endif
