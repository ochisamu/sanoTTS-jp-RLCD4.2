# Notices

Except for files that carry a different SPDX identifier, this repository's
original code is MIT licensed. The following third-party work is used or
adapted and keeps its own license and notices.

## sanoTTS-jp

Code: Copyright ayutaz and contributors, MIT License.

Source: https://github.com/ayutaz/sanoTTS-jp

Pinned revision: `f427b1e6bf743965c9b033d43fdf84b56f8f7543`

`firmware/main/rlcd42_console.c` preserves sanoTTS-jp's MIT-licensed console
line-state behavior and adds this repository's board-specific local KEY input.

The model weights are **not MIT licensed**. They are downloaded separately
and are covered by `licenses/sanoTTS-jp-model.md`. Generated audio is also
subject to the output-use restrictions in that license.

Required v4 model attribution is preserved verbatim in
`licenses/sanoTTS-jp-NOTICE.txt`, together with the required Apache-2.0
license in `licenses/sanoTTS-jp-Apache-2.0.txt`. Both accompany built artifacts.

## Waveshare ESP32-S3-RLCD-4.2 hardware support

The ST7305 initialization sequence and landscape framebuffer mapping in
`firmware/main/rlcd42_display.c`, the GPIO4 / ADC1_CH3, 12 dB calibrated x3
battery conversion in `firmware/main/rlcd42_battery.c`, and the board pin
assignments used by this demo were adapted for this repository from Waveshare's
Apache-2.0 ESP-IDF examples:

https://github.com/waveshareteam/ESP32-S3-RLCD-4.2

Pinned reference revision: `eb1f63427d735a22b9c30e22fa63ebddae1834d3`

Pinned ADC reference:
https://github.com/waveshareteam/ESP32-S3-RLCD-4.2/blob/eb1f63427d735a22b9c30e22fa63ebddae1834d3/02_Example/ESP-IDF/10_FactoryProgram/components/port_bsp/adc_bsp.cpp

The adapted files have been substantially changed for a 1-bit PSRAM
framebuffer, chunked DMA transfers, fail-closed amplifier handling, and this
demo's status UI. The upstream Apache License 2.0 text is preserved in
`licenses/waveshare-examples-Apache-2.0.txt`.

These attributions do not imply validation on every hardware revision. One
physical ESP32-S3-RLCD-4.2 was tested on 2026-09-02 for display, speaker output,
battery telemetry, on-device Japanese conversion, and serial text input.

Copyright 2026 Waveshare.

## Optional kanji-input profile (not enabled in this lab build)

The current build uses kana input and Shinonome display glyphs, not an on-device
Open JTalk/NAIST/UniDic dictionary. Displaying kanji is not kanji-input support.
The old demo's dictionary notice filenames are not present in this repository.
If enabling the upstream optional kanji-input profile, preserve its COPYING,
dictionary provenance and notices before distributing. See upstream
`third_party/sanoTTS-jp/NOTICE.md`; do not claim this profile is license-cleared here.
