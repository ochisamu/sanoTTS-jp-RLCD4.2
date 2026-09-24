# RLCD4.2 Japanese offline voice lab

[日本語](README.md) · [Reproduction](docs/REPRODUCE.en.md) · [Training provenance](docs/TRAINING.en.md) · [Licenses](licenses/README.en.md)

**Powered by Moonshine AI**

An independent research project running Japanese recognition, short reply generation
and sanoTTS-jp speech synthesis on a Waveshare ESP32-S3-RLCD-4.2, 16MB Flash / 8MB PSRAM.
Inference is on-device: no cloud API, Wi-Fi, or PC-generated audio. A PC/GPU is used
for training, flashing, and optional text input. This is separate from CharaDock
and the earlier ATOM Echo demo.

**Experimental, not a general conversational assistant.** The LM can give unrelated
answers or mishandle negation. Low latency, robust speech accuracy, and long-term
battery-only operation are not established. Weights and combined flash images
are excluded from the current publication scope.

## Controls and display

| Control | Action |
| --- | --- |
| Press/release KEY | Record 5 seconds → recognize → repeat |
| Press/release BOOT | Record 5 seconds → recognize → generate a reply → speak |
| PWR | Original power function |

Speak after the listening display appears. Do not hold BOOT while powering on:
that selects download mode. Held-at-startup/busy buttons and chords are ignored.
There is no always-on listening and no multi-turn conversation memory.

The 400×300 monochrome UI uses Shinonome 16px (6,974 glyphs) and an original
large geometric face and prominent English status. Japanese captions appear only
when needed: `HEARD` shows recognized kana; `REPLY` shows the repeated
sentence or generated reply. One three-line panel changes pages every four seconds
while idle and disappears about eight seconds after processing (longer for more pages).
Text remains in memory until the next operation. Audio EQ reduces low-mid boxiness
without increasing gain or the output ceiling. Kanji glyphs
are supported, but STT/LM output remains kana. Unknown glyphs appear as boxes.
No Stack-chan artwork or code is bundled.
149 known answers have kanji display forms; unmapped generated text stays kana.

For typed questions, use `tiny_lm/console.cmd` on Windows or:

```sh
python -X utf8 tiny_lm/console.py --port YOUR_PORT --say
```

Requires pyserial. Input up to 80 kana characters; `/quit` exits. Example:
`かんたんなりょおりおおしえて`. Phonetic spelling such as `きょお` matches training.
Kanji input, general knowledge lookup, and PC-side inference are not provided.

## Architecture and measurements

Microphone → silence trimming/level adjustment → six-layer phoneme CTC → kana →
[KEY: repeat / BOOT: 16 local fact cards, otherwise four-layer generative LM] → sanoTTS-jp → DSP → speaker.
Recording/STT temporaries are freed before LM loading; LM memory is freed before TTS.

| Component | Configuration / measurement |
| --- | --- |
| STT | Moonshine-derived six-layer encoder, 41 phonemes, W8A8, 7,808,724 bytes |
| STT timing | About 13 seconds for one stored 6.6-second clip, not a live-latency distribution |
| LM | Four layers, width 256, 2.91M parameters, 1,024 BPE tokens, W8A8, 3,074,496 bytes |
| LM timing | About 1.0–1.9 seconds over 32 queries, excluding capture/STT/TTS |
| TTS | sanoTTS-jp v1.0.0 / v4 INT8, 654,032 bytes |
| Audio | RLCD-tuned CharaDock-derived DSP; current volume/duration settings retained |
| Display | 15,000-byte 1-bit framebuffer; approximately 251KB of Flash-resident glyphs |

32/32 LM matches mean parity with the native C reference, NOT 100% answer accuracy.
STT dev phoneme error 14.49% and adapted LM wording-dev exact match 115/175 are tuning-set
results, not independent final tests or general conversation accuracy.
See [training provenance and limitations](docs/TRAINING.en.md).
[Kanji captions, adaptation and local knowledge](docs/REPLY_UPGRADE.en.md) explains the hybrid paths and reproduction.

## Publication and licenses

Original lab code is MIT; third-party code, fonts and models retain separate terms.
**The whole system is not MIT. Downloading weights externally does not remove their terms.**
Read the [license guide](licenses/README.en.md), including the [voice output rules](licenses/VOICE_TERMS.md).

本ソフトウェアの音声合成には、フリー素材キャラクター「つくよみちゃん」
（© Rei Yumesaki）が無料公開している音声データを使用しています。
[つくよみちゃんコーパス（CV.夢前黎）](https://tyc.rei-yumesaki.net/material/corpus/)
This software uses voice data provided by Rei Yumesaki for Tsukuyomi-chan through
the upstream TTS model. This is not an endorsement or an official collaboration.

Weights, downloaded datasets, recordings, backups and secrets stay outside Git.
Current dialogue weights remain on hold for distribution. Run
`python tools/publication_check.py`; it is an artifact check, not legal clearance.

[Reproduction](docs/REPRODUCE.en.md) · [Publication review](licenses/PUBLICATION_REVIEW.md)
· [Historical lab notes](docs/HISTORY.md) · [Dialogue experiments](tiny_lm/DIALOGUE_EXPERIMENTS.md).
Historical records describe older states, not current specifications.
