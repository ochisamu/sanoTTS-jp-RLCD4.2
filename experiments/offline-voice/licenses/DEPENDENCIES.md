# Build dependency notices / ビルド依存の表示

Current target: ESP32-S3-RLCD-4.2 N16R8, ESP-IDF 5.5.4, esp_codec_dev 1.5.4.
Versions and the codec component hash are pinned in `firmware/dependencies.lock`.

- ESP-IDF: Espressif Systems and contributors, Apache-2.0 except separately
  licensed components; original top-level text is `ESP-IDF-LICENSE.txt`.
  Source: https://github.com/espressif/esp-idf/tree/v5.5.4
- esp_codec_dev: Espressif Systems and contributors, Apache-2.0; original text is
  `esp_codec_dev-Apache-2.0.txt`. Component source:
  https://components.espressif.com/components/espressif/esp_codec_dev/versions/1.5.4
  Its ZL38063 device directory has a separate Microsemi 2018 MIT notice, preserved
  as `esp_codec_dev-Microsemi-MIT.txt` for completeness, not as a claim that this
  board contains that codec. RLCD uses ES7210 and ES8311.
- sanoTTS-jp submodule: `f427b1e6bf743965c9b033d43fdf84b56f8f7543`, MIT code;
  model license separate. The current build does not enable `SAAN_KANJI`, M5Unified,
  M5GFX, IPA fonts or the Open JTalk device dictionary.
- Display fonts are Shinonome, not IPA/M5 fonts. See `Shinonome-NOTICE.md`.
- Host training dependencies (PyTorch, Transformers, pyopenjtalk, etc.) are
  installed separately under their own licenses; their packages/dictionaries are
  not redistributed by this source repository. See requirements files for versions.

## Model-free binary preview supplement

`binary/COMPILED-NOTICES.txt` preserves notice preambles from the compiled source
inventory, including Cadence Xtensa HAL and Amazon FreeRTOS copyright notices.
It is inclusive: not every compiled object is retained in the final binary.
The published package also preserves the following runtime license texts:

- Newlib libc/libm: `binary/Newlib-COPYING.txt` (collection of permissive notices).
- GCC libgcc/libstdc++: `binary/GPL-3.0.txt` with `GCC-RUNTIME-EXCEPTION.txt`.
  The firmware was built using the unmodified supplied GCC toolchain; no
  proprietary GCC intermediate-representation optimizer is used.
- FreeRTOS: MIT; original copyright preambles and `FreeRTOS-MIT.txt`.
- TLSF and BSD portions: `BSD-3-Clause.txt`, with original file-level notices.
- Mbed TLS: the Apache-2.0 option of its dual license is selected;
  the original complete dual-license text is in `MbedTLS-LICENSE.txt`.
- ESP-IDF, codec, sanoTTS code, Shinonome and BSP/DSP: original texts in this directory.

This supplement supports only the model-free app/bootloader/partition-table
developer preview. No neural weights, NVS, test audio or merged flash backup is
packaged. Keep the full notice bundle with redistributed binaries.

The initial source-only audit below is retained for context:

This list is not a claim that every object linked into an ESP-IDF binary has only
Apache terms. ESP-IDF/toolchain components include separate permissive licenses
and runtime exceptions. A binary release still requires a complete linked-object
notice inventory, plus model permission review; no combined binary is cleared here.

上記はソース公開準備の依存一覧です。ESP-IDFやツールチェーン全体をApacheだけと
みなさないでください。重み配布の問題に加え、バイナリRelease前には実リンク依存の
表示を確定する必要があります。ホスト用辞書やパッケージは同梱しません。
