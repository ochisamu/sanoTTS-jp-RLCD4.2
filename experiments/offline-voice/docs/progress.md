# Progress and limitations

## Latency and DSP update

Quiet-input correction: the old precheck rejected any five-second capture with
global RMS below0.002 before looking for speech. Short words could therefore be
rejected even when their local level was above background. The capture now runs
the windowed detector first and uses global RMS only as fallback; short detected
regions retain detection and are padded to one second. Silence and isolated
impulses still fail detection. The display says NO SPEECH - RETRY instead of
mislabeling this input condition as TTS ERROR. Synthetic quiet-short-phrase and
boundary regression tests pass; real-world mic sensitivity still needs testing.

See results/device_optimization.json. The user heard the earlier live repetition,
but judged recognition far too slow and speech muffled/quiet. This is not a
successful practical conversation demo merely because its pipeline runs.

QA5 uses int8 QK/PV attention, bounded math lookup interpolation, FP32 per-frame
norm accumulation, reciprocal quantization and S3 half-even rounding. Same 6.6s
reference: 36.128s -> 13.565s, native/device frame argmax hash bb0f0a32.
Dev64 PER worsens from 14.07% to 14.49%; no independent test claim. Run
`python evaluate_packed.py --qa 5` to evaluate the selected runtime mode.
Runtime mode numbers in ctc_runtime.h are experimental implementation variants.

Live capture remains five seconds; boundary-only energy trimming keeps 250ms
context, does not remove pauses within speech and falls back to full input when
uncertain. It is a heuristic, not a trained VAD; it can still misidentify quiet
unvoiced phonemes. Short-utterance latency and trimming accuracy need live checks.

CharDock DSP was ported via the existing ATOM C implementation (Apache-2.0).
Baseline matches JS within 3 PCM16 LSB; an RLCD-specific profile strengthens
highpass/presence and uses output gain1.2, codec volume100, limited peak0.7.
Processing finishes before DMA playback, so DSP cannot cause streaming underruns.
Unit tests include chunk invariance, short tails, silence, DC suppression,
peak limits and ASan/UBSan. The math interpolation sweep also passes sanitizers.
Latest listening feedback is still required. DSP cannot correct STT mistakes or
restore natural accent information discarded by the phoneme-to-kana bridge.

## Current integrated firmware (2026-09-24)

Local KEY: five-second recording -> W8A8 phoneme CTC -> kana -> sanoTTS -> ES8311.
No network or PC ASR service is involved. Fixed-phrase SAY completed on hardware,
including zero/mute register checks, playback and ES7210 microphone reopen.
The reference ECHO pipeline also completed: STT 36.128 seconds, 51200 generated
TTS samples, same bb0f0a32 hash. Live STT captured user speech in 24.217 seconds,
but the first combined live run overflowed the original 8KB task stack during
TTS. The default is now 24KB; reference ECHO completed after that fix.
After the fix, a live five-second recording completed STT (24.228 seconds), kana
conversion, synthesis (28672 samples), playback and microphone reopen without
reboot. The decoded output contained an extra initial phoneme. User confirmation
of audibility and battery-only operation remain outstanding. A separate
build-repro directory also built successfully from sdkconfig.defaults, reusing
already-downloaded dependencies; a fully clean machine is not yet tested.
The sections below describe earlier stages, not the current capability limit.

The six-layer CTC model occupies 7,808,724 bytes in flash. ESP32 inference on a
6.6-second reference clip took 36.031 seconds; frame argmax FNV-1a hash bb0f0a32
matches native C. Tiling int8 projections reduced 87.098 seconds to 36.031 seconds.
The 5-second live path is not real-time and requires waiting after recording.

Training used 2164 clips / 6.6894 hours from FLEURS Japanese train. The 237-clip
duration-filtered validation set contains 0.7707 hours; only a fixed 64-clip subset
was used to select checkpoints. Best step1600 phoneme error: 13.5665%; packed W8A8:
14.0684% (925 edits / 6575 phones). Do not label these test accuracy or word error.
5000 training steps took 453.4 seconds on RTX 5060 Ti 16GB. Labels are automatic.

### Reproduction of the follow-up

After installing requirements and downloading the pinned base model with benchmark.py:

```sh
git submodule update --init --recursive
python fetch_fleurs.py
python prepare_fleurs.py
python train_ctc.py --layers 6 --name ctc6 --steps 5000
python export_ctc.py --name ctc6 --checkpoint best --layers 6
cc -O3 -std=c11 runtime/native.c runtime/ctc_runtime.c -lm -o .cache/ctc-native
python validate_runtime.py --name ctc6 --layers 6 --checkpoint best
python evaluate_packed.py
python generate_kana_table.py
python fetch_tts.py --accept-model-license
python -m unittest -v
```

Read the upstream TTS model license before using the acceptance flag. Trained
weights retain the Moonshine Community License. Neither weights nor recordings
are committed. Training results can vary; seeds do not guarantee CUDA determinism.

Build with ESP-IDF 5.5.4: `idf.py -C firmware build`. Flash only the identified
ESP32-S3-RLCD4.2, after backing up firmware. Layout: app 0x10000, STT 0x210000,
TTS 0xa10000. Bootloader and partition table from the same build must be installed
on a fresh device. Do not apply this layout to ATOM Echo or another board.
TEST/ECHO diagnostics also require the optional reference audio at 0xb10000;
KEY/LISTEN/SAY do not depend on it. A complete clean-machine flash script is pending.

Windows/pyserial: `python device.py --command SAY` plays a fixed kana sentence;
`python device.py --watch` observes a KEY-triggered run for up to 300 seconds.
`--command LISTEN` starts recording immediately; prefer KEY for human timing.
The earlier `--record` path is a diagnostic raw recording only, not the STT path.

The shared ESP32-S3 full-duplex I2S must keep RX clocking for TX DMA to progress.
Closing the microphone codec is distinct from stopping the RX clock. Explicit
clock priming and restoration fixed playback transfer failure. Model synthesis
returns frame counts; PCM length is frames times SAAN_HOP (256).

## Hardware

RLCD4.2: ESP32-S3, 16MB flash, 8MB PSRAM, USB Serial/JTAG COM4.
Microphone probe firmware successfully written and identified via a capability string.
Five seconds of stereo 16kHz/16-bit PCM (320000 bytes) transferred successfully.
Initial ambient RMS 18.54/20.29, peaks 237/260, zero clipping; PSRAM free 8056844 bytes.
This proves data transport, not intelligible speech capture. User speech check remains.
PA GPIO46 stays LOW. No Wi-Fi or automatic recording. Existing speaker and battery remain connected.
No eFuse/security modifications. Bootloader USB flashing remains supported.

The first capture failed because ESP-IDF's USB driver queues an entire item into its
ring buffer: a 320KB item cannot fit in 4KB. Sending 512-byte chunks fixed the transfer.
The failed capture was not saved.

## Training

JVS official download was temporarily unavailable due to its Google Drive quota.
Use Google FLEURS Japanese instead: pinned revision
`70bb2e84b976b7e960aa89f1c648e09c59f894dd`, CC-BY-4.0, train/dev files only.
Data remains outside Git. Transcript phonemes are generated with pyopenjtalk 0.4.1
and Open JTalk dictionary 1.11; these labels can contain pronunciation errors.
Vowels are lowercased, so devoicing labels are folded; N is retained.

New phoneme CTC head replaces the large text decoder. Encoder layers 0/2/4 reuse
Moonshine Japanese weights. CTC learning is required; this is not a working STT
model just because its tensor sizes fit. Batch=1, accumulation=4 avoids padded
audio corrupting the pretrained global GroupNorm statistics.
Dev text overlap with training is checked explicitly. The FLEURS metadata used here
does not expose speaker identifiers; speaker-disjointness has not been independently
verified. Do not claim it based only on the train/dev file names.
The final test split is not used for tuning and has not been downloaded yet.

## Local commands

With dependencies from requirements.txt installed:

```sh
python fetch_fleurs.py
python prepare_fleurs.py
python train_ctc.py --steps 1200
```

Checkpoints remain in `.cache/ctc`, and results in `results/ctc_training.json`.
`--resume` resumes weights only, with a fresh optimizer; this is explicitly recorded.
The experiment is not a redistribution of trained model weights.

Firmware build: ESP-IDF 5.5.4, `idf.py -C firmware build`.
On Windows with pyserial: `python device.py --port COM4` identifies the probe.
`python device.py --port COM4 --record .cache/recording.wav` explicitly records five seconds.
The host refuses to overwrite an existing WAV. Microphone data is never uploaded.

## Sources

- [FLEURS](https://huggingface.co/datasets/google/fleurs)
- [JVS official terms and download](https://sites.google.com/site/shinnosuketakamichi/research-topics/jvs_corpus)
- [RLCD official board configuration](https://github.com/waveshareteam/ESP32-S3-RLCD-4.2/blob/eb1f63427d735a22b9c30e22fa63ebddae1834d3/02_Example/ESP-IDF/10_FactoryProgram/components/ExternLib/codec_board/board_cfg.txt)
- [Reference ESP32-S3 English Conformer runtime](https://github.com/lspr98/conformer-stt-s3)

Board/battery code copied from the user's MIT-licensed rlcd42-sanotts-demo;
display code includes Apache-2.0 Waveshare adaptations. Notices are in licenses/.
esp_codec_dev is fetched at version 1.5.4 via its
component manifest. The STT model retains the separate Moonshine Community License.
