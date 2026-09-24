# BPE experimental deployment / BPE候補の実機導入

This page records the original deployment. The current adapted checkpoint,
hybrid knowledge path and kanji captions are documented in
[Japanese](../docs/REPLY_UPGRADE.md) / [English](../docs/REPLY_UPGRADE.en.md).

2026-09-24: user-authorized experimental installation on RLCD4.2 N16R8.
会話品質ゲートは依然不合格です。実機動作成功と、質問への正しい返答は別です。
否定・未知の話題・言い換えで誤応答します。一般用途の対話モデルではありません。

## Installed / 導入内容

- W8A8 causal Transformer: 4 layers, dimension 256, 8 heads, FF768.
- BPE vocabulary 1,024, context 96 tokens; model 3,074,496 bytes.
- SHA256: `985505b6abfe3504ccadd6b535a48a87e8a48ebb61183af0e9d8305cf5ef26e7`.
- 114 training families; authored answers, not general knowledge. See the training log for data terms.
- Firmware: `KLM_BPE_RUNTIME=ON`; `firmware/partitions-bpe.csv` enlarges only
  `tiny_lm` at `0xc10000` from 2 MiB to 3 MiB. STT/TTS/testaudio offsets unchanged.
- Bootloader, STT/TTS assets and recorded test audio were not written.

32 deterministic sampled queries matched the native C reference exactly, with
PSRAM returning to 8,056,196 bytes each time. This is runtime parity, NOT 100% accuracy.
Model loading + prefill + decoding: 1,000–1,891 ms, median 1,327.5 ms, excluding STT/TTS.
Workspace: 805,344 bytes; free PSRAM during inference: 4,195,260 bytes.
Local logs: `.cache/rlcd-bpe-deploy-20260924/` (ignored; contains machine-specific files).

## Try / 試す

Open `tiny_lm/console.cmd` on Windows after closing other COM4 monitors.
This sends text only; the ESP32 generates the reply and synthesizes speech.

```text
kana> かんたんなりょおりおおしえて
kana> しゅくだいがおわった
kana> /quit
```

Phonetic kana, maximum 80 input characters. Prefer `きょお`, `りょおり` matching
training normalization. Output is capped at 40 BPE tokens and a 256-byte buffer,
not 40 characters. Unsupported input is rejected. No multi-turn memory.
Two-button update: **KEY (GPIO18) repeats recognized speech; BOOT (GPIO0)
recognizes speech, generates a reply, and speaks it.** Press and release after
normal startup, then speak during the five-second listening window. PWR is
unchanged. Do not hold BOOT while powering on; that enters download mode.
Held-at-startup/busy buttons and simultaneous presses are ignored. There is no
background listening. `LISTEN` selects microphone echo, `CHAT` microphone reply.
`TESTCHAT` runs the stored test clip through STT → LM → TTS, without recording.
`ASKSAY <kana>` still accepts typed questions (`ASK` for text only).
Failed/overlong recognition or generation does not trigger a guessed fallback
answer. This connection does not improve the experimental model's reply quality.

## Build / 再ビルド

For a fresh checkout, use the current [Japanese](../docs/REPRODUCE.md) /
[English](../docs/REPRODUCE.en.md) instructions, including Shinonome generation.
The cached sdkconfig path below records the original local deployment; it is not
a file shipped to new users. Current firmware also includes the text/face UI.

Reproduce the selected model using `DIALOGUE_EXPERIMENTS.md`; weights stay outside Git.
Activate ESP-IDF 5.5.4. Copy a working N16R8 sdkconfig into a separate build config,
set both partition-table filename entries to `partitions-bpe.csv`, retain the 24,576-byte
main task stack and octal PSRAM settings, then build from the repository root:

```sh
idf.py -C firmware -B "$PWD/build-lm-bpe" -DSDKCONFIG="$PWD/.cache/rlcd-bpe-deploy-20260924/sdkconfig" -DKLM_BPE_RUNTIME=ON build
```

After verifying device identity and backups, write only these address/file pairs
using esptool on the OS that owns the serial port (Windows Python for COM4 here):

```text
0x8000   build-lm-bpe/partition_table/partition-table.bin
0x10000  build-lm-bpe/rlcd42_stt_mic_probe.bin
0xc10000 .cache/daily-semantic-bpe-256/model.bin
```

Do not erase the whole flash. Do not use this partition map for a 4 MiB device.
`device_bpe_eval.py --reference <wording-dev-packed.json> --out <new-report.json>`
checks device/native parity; pyserial is required. It is not an end-to-end speech test.

## Rollback / 復旧

Before installation, old app and model were verified against actual flash by digest.
The original 4 KiB partition table was read successfully. Restore these saved files
with esptool `write-flash` (paths relative to `.cache/rlcd-bpe-deploy-20260924/`):

```text
0x8000   before-partitions.bin
0x10000  before-app.bin
0xc10000 before-model.bin
```

Bulk flash reads stopped early; `before-system.bin` and `before-system-retry.bin`
are incomplete and MUST NOT be used as backups. The three files above are the
validated rollback set. Serial download and bootloader are preserved.
