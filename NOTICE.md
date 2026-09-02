# Notices

Except for files that carry a different SPDX identifier, this repository's
original code is MIT licensed. The following third-party work is used or
adapted and keeps its own license and notices.

## sanoTTS-jp

Code: Copyright ayutaz and contributors, MIT License.

Source: https://github.com/ayutaz/sanoTTS-jp

Pinned revision: `8f76437fe82604b3d77dc6a5ddbd0e4f557a750d`

`firmware/main/rlcd42_console.c` preserves sanoTTS-jp's MIT-licensed console
line-state behavior and adds this repository's board-specific local KEY input.

The model weights are **not MIT licensed**. They are downloaded separately
and are covered by `licenses/sanoTTS-jp-model.md`. Generated audio is also
subject to the output-use restrictions in that license.

Required model attribution (reproduced verbatim from the model license):

```text
This model was distilled from a piper-plus teacher model.
sanoTTS-jp — https://github.com/ayutaz/sanoTTS-jp

つくよみちゃんコーパス
  本ソフトウェアの音声合成には、フリー素材キャラクター「つくよみちゃん」
  （© 夢前黎）が無料公開している音声データを使用しています。
  https://tyc.rei-yumesaki.net/material/corpus/

MOE-Speech (litagin) — https://huggingface.co/spaces/litagin/moe-speech-license
  著作権法 30 条の 4（情報解析のための利用）に基づき学習に使用。

蒸留に使用したテキストコーパス:
  - Common Voice ja (Mozilla) — CC0-1.0
      https://github.com/common-voice/common-voice
  - ROHAN4600 (森勢将雅) — CC0-1.0
      https://github.com/mmorise/rohan4600
  - ITA コーパス — CC0-1.0
      https://github.com/mmorise/ita-corpus
  - JSUT ver1.1 (高道慎之介) — CC-BY-SA-4.0 ほか（subset 別）
      https://sites.google.com/site/shinnosuketakamichi/publication/jsut

教師実装: piper-plus (MIT) — https://github.com/ayutaz/piper-plus
```

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

## Kanji profile third-party notices

The optional kanji profile includes Open JTalk-derived code and a dictionary
derived from NAIST/UniDic data. Their binary-redistribution notices are kept in:

- `licenses/NOTICE-openjtalk.txt`
- `licenses/NOTICE-dictionary.txt`
- `licenses/openjtalk-PROVENANCE.md`
