# RLCD 4.2 — sanoTTS / Offline Japanese Voice Lab

[日本語](README.md) · [Voice lab](experiments/offline-voice/README.en.md) · [Training sources](experiments/offline-voice/docs/TRAINING.en.md) · [Licenses](experiments/offline-voice/licenses/README.en.md)

[![RLCD4.2 device demo — click for video with sound](media/offline-voice-preview.gif)](https://github.com/ochisamu/sanoTTS-jp-RLCD4.2/blob/main/media/offline-voice-demo.mp4)

Click for the video with sound. The inline preview is silent with a reduced frame
rate; inference delays have not been removed. This user-supplied recording shows
an earlier caption-label version; current labels are `HEARD` and `REPLY`.

**Powered by Moonshine AI**

The experimental [offline voice lab](experiments/offline-voice/README.en.md) runs
Japanese speech recognition → kana → local knowledge or a tiny generative LM →
sanoTTS synthesis on one Waveshare ESP32-S3-RLCD-4.2 N16R8. No cloud, Wi-Fi or
PC inference. KEY repeats speech; BOOT answers and speaks. The display uses a
large original face, English status and temporary Japanese captions.

**This is a research demo, not a reliable general Japanese assistant.** It can
misrecognize speech, misunderstand negation and produce unrelated answers.

## Two distinct firmware projects

| Location | Purpose |
| --- | --- |
| `firmware/`, `tools/demo.py` | Original TTS-only demo, USB text input and optional kanji dictionary |
| `experiments/offline-voice/` | New STT + SLM + TTS experiment, kana recognition and known-answer kanji captions |

The flash layouts are different. Never mix their binaries or flashing commands.
The [Release](https://github.com/ochisamu/sanoTTS-jp-RLCD4.2/releases) contains a
**model-free developer-preview firmware package**, not a turnkey voice assistant.
STT/SLM/TTS weights must be acquired or trained separately under their respective
terms. Read the [firmware release guide](experiments/offline-voice/docs/FIRMWARE_RELEASE.md).
No weights, downloaded corpora, recordings or device backups are shipped. Current
dialogue weights remain withheld pending a redistribution review.

For the original TTS-only setup, see the [existing Japanese instructions](README.md#既存のtts専用版).
For the new experiment, use the [English reproduction guide](experiments/offline-voice/docs/REPRODUCE.en.md).

## Credits and licensing

Original code: MIT, except explicitly attributed third-party derivatives.
The complete system is not MIT; firmware includes separately licensed components
and fonts. Model and generated-voice conditions are separate.

本ソフトウェアの音声合成には、フリー素材キャラクター「つくよみちゃん」
（© Rei Yumesaki）が無料公開している音声データを使用しています。
[Tsukuyomi-chan corpus (CV. Rei Yumesaki)](https://tyc.rei-yumesaki.net/material/corpus/)

Voice synthesis uses sanoTTS-jp and Tsukuyomi-chan voice data. This is not an
official character product or endorsement. Preserve the
[voice terms](experiments/offline-voice/licenses/VOICE_TERMS.md) and accompanying
notices. The demo video is not offered as reusable voice-training/audio material.
