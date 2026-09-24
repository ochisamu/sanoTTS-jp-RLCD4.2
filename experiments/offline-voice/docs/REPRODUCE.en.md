# Reproduction, build and verification

[日本語](REPRODUCE.md) · [Home](../README.en.md)

Only for RLCD4.2 N16R8. Do not flash this layout onto ATOM Echo or other boards.
Weights are not bundled or released. Read the [license guide](../licenses/README.en.md)
before downloading/training. Back up existing firmware if needed; preserve correct
speaker/battery wiring. Do not publish full-flash backups.

## 1. Source and font

From the repository root on Linux/WSL:

```sh
git submodule update --init --recursive
python3 tools/prepare_font.py --download
```

Four font source files are SHA256-checked at a pinned revision, then converted into
`.cache/font/`. Run without `--download` to regenerate offline. No upstream font
scripts are executed. Expected sanoTTS submodule: `f427b1e6bf743965c9b033d43fdf84b56f8f7543`.

## 2. STT and TTS

STT training requires NVIDIA CUDA; the tested GPU is RTX5060Ti 16GB. Use a separate
environment and a CUDA-enabled PyTorch wheel. Do not change another project's environment.

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
# Only after reviewing the model agreement and AUP:
.venv/bin/python tools/fetch_stt_base.py --accept-community-license
.venv/bin/python fetch_fleurs.py
.venv/bin/python prepare_fleurs.py
.venv/bin/python train_ctc.py --layers 6 --name ctc6 --steps 5000
.venv/bin/python export_ctc.py --name ctc6 --checkpoint best --layers 6
cc -O3 -std=c11 runtime/native.c runtime/ctc_runtime.c -lm -o .cache/ctc-native
.venv/bin/python evaluate_packed.py --qa 5
# Only after reviewing the TTS model license:
.venv/bin/python fetch_tts.py --accept-model-license
```

Outputs: `.cache/ctc6/model-int8.bin` and `.cache/tts-v4.bin`. Keep data and weights
outside Git. Pinned sources and seeds do not guarantee identical CUDA-trained weights.
pyopenjtalk's initial host dictionary download is a separate asset, not a device
kanji dictionary; it is not bundled.

## 3. Reply model

Follow the [complete BPE experiment commands](../tiny_lm/DIALOGUE_EXPERIMENTS.md),
using `tiny_lm/requirements-dialogue.txt`. Do not skip paraphrase review or apply an
old reviewed hash to newly generated text. Teacher answers are not automatically
accepted. Then follow [adaptation and reply assets](REPLY_UPGRADE.en.md#reproduction).
The selected output is `.cache/improvement-model-256/model.bin`.
Before building, run `python tools/prepare_reply_assets.py` with the training
dependencies installed; it generates caption/knowledge tables without weights.
There is no public download URL for these weights. Local reproduction still has
upstream data/model obligations.

## 4. Build

Install ESP-IDF **5.5.4** separately and source its `export.sh`. Use a separate
configuration/build directory to avoid silently inheriting a previous sdkconfig:

```sh
idf.py -C firmware -B "$PWD/build-public" \
  -DSDKCONFIG="$PWD/build-public/sdkconfig" \
  -DSDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.bpe.defaults" \
  -DKLM_BPE_RUNTIME=ON build
```

Building requires the generated font, but not model weights. The UI uses a 15KB
1-bit framebuffer and Flash-resident glyphs. Do not enable `SAAN_KANJI` for this layout.

## 5. Flash

Close serial monitors and identify the port/chip/16MB Flash with
`python -m esptool --chip esp32s3 --port YOUR_PORT flash-id`.
Windows COM ports require Windows Python; use Windows-readable/UNC paths for files
stored in WSL. Direct Linux connections typically use `/dev/ttyACM*`.

On a fresh board, use matching bootloader, table and app from the same build, plus
all required models. Verify the address/file pairs before passing them to esptool
`write-flash`; no unconditional whole-chip erase is needed.

| Address | File |
| --- | --- |
| `0x0` | `build-public/bootloader/bootloader.bin` (initial setup only) |
| `0x8000` | `build-public/partition_table/partition-table.bin` (initial setup/layout changes) |
| `0x10000` | `build-public/rlcd42_stt_mic_probe.bin` |
| `0x210000` | `.cache/ctc6/model-int8.bin` |
| `0xa10000` | `.cache/tts-v4.bin` |
| `0xc10000` | `.cache/improvement-model-256/model.bin` |

For an existing matching layout/models, a UI update writes only the app at
`0x10000`. Optional stored test audio at `0xb10000` is not required for KEY/BOOT.
Without it, `TEST`/`ECHO`/`TESTCHAT` report an error; reference audio with unclear
redistribution permission is not bundled or automatically fetched here.

## 6. Verify

```sh
python3 -m unittest discover -s tests -p test_voice_ui.py -v
cc -Wall -Wextra -Werror -Iruntime tests/voice_buttons_test.c -o .cache/voice-buttons-test
.cache/voice-buttons-test
.venv/bin/python -m unittest test_ctc test_phonemes test_speech_trim -v
python3 tools/publication_check.py
```

Optional preview: run `tools/preview_ui.py` with Pillow installed. This uses the
actual renderer but is not a photo of the panel. Serial: 115200 baud, UTF-8, LF;
try `ID` and `ASKSAY きょおわつかれた`. Live button/speech, audibility and battery-only
operation require separate checks in your environment. Captions disappear about eight
seconds after processing (longer for more pages); text remains in memory until the
next operation. Do not inadvertently publish private transcripts in photos or logs.
Use `tools/preview_ui.py --captions` for a captioned preview.
