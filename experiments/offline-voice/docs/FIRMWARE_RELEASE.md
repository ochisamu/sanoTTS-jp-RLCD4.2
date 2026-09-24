# Firmware developer preview / ファームウェア開発プレビュー

Target: Waveshare ESP32-S3-RLCD-4.2 **N16R8 only**. Tag: `offline-voice-v0.1.0`.
This package does not contain neural weights, recorded audio, NVS or factory data.
モデル非同梱。新品の実機にこれだけ書き込んでも音声認識・SLM・TTSは使えません。

## Contents / 内容

- `rlcd42-offline-voice-app.bin`: application only, address `0x10000`.
- `bootloader.bin`: address `0x0`, initial setup only.
- `partition-table.bin`: address `0x8000`, this experiment's map only.
- SHA256 manifest, build provenance, license/notice bundle and this guide.

Weights are read from separate partitions. The app contains firmware, Shinonome
glyphs and original authored knowledge/caption tables, not neural weights.
No full-flash/merged image or ELF containing local build paths is distributed.

## Existing matching lab installation / 同じ実験版の更新

Verify the board and partition map first. Close serial consoles, preserve a
private backup, then update only the application:

```sh
python -m esptool --chip esp32s3 --port YOUR_PORT write-flash 0x10000 rlcd42-offline-voice-app.bin
```

This preserves existing weights only when their offsets and formats already
match. Do not use this command for the repository's original TTS-only layout.
既存のTTS専用版とは配置が違います。appだけを混ぜて書き込まないでください。

## Fresh setup / 新規導入

Prepare the models via the [Japanese](https://github.com/ochisamu/sanoTTS-jp-RLCD4.2/blob/main/experiments/offline-voice/docs/REPRODUCE.md) / [English](https://github.com/ochisamu/sanoTTS-jp-RLCD4.2/blob/main/experiments/offline-voice/docs/REPRODUCE.en.md)
source instructions. SLM weights are not currently downloadable from this project:
their parent-data redistribution review is unresolved. Reproduction requires
training and source-license compliance; this release is not turnkey.

| Address | Required content |
| --- | --- |
| `0x0` | bootloader |
| `0x8000` | experiment partition table |
| `0x10000` | application |
| `0x210000` | phoneme STT, 7,808,724 bytes |
| `0xa10000` | sanoTTS v4 INT8, 654,032 bytes |
| `0xc10000` | selected 4-layer BPE SLM, 3,074,496 bytes |

The partition table reserves `0xb10000` for optional local test audio, which is
not shipped. KEY/BOOT live recording does not require it. Never flash an arbitrary
five-layer model or the original TTS kanji dictionary into this layout.
No automatic flashing/erase script is provided; check all offsets and model hashes
in the reproduction/training documentation. Never upload personal flash backups.

## Licenses / ライセンス

Keep the complete accompanying `licenses/` directory. Original code is MIT;
Apache-2.0, MIT/BSD-style component notices, GCC runtime exceptions and Shinonome
terms are preserved. See `licenses/DEPENDENCIES.md`. Model and generated-voice
terms still apply when models are obtained separately. Whole-system MIT claims
are incorrect. This experimental package comes without a reliability warranty.
