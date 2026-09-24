# 再現・ビルド・検証

[English](REPRODUCE.en.md) · [トップ](../README.md)

対象はRLCD4.2 N16R8のみ。ATOM Echo等にこのパーティション配置を使用しないでください。
現在の重みは非同梱・非配布です。学習や取得には[ライセンス](../licenses/README.md)への同意が必要。
元ファームを必要に応じてバックアップし、スピーカー・電池は正しい配線のまま使用してください。

## 1. ソースとフォント

Linux/WSLで、取得したリポジトリのルートから実行します。

```sh
git submodule update --init --recursive
python3 tools/prepare_font.py --download
```

フォントは固定revision・4ファイルのSHA256を検証して `.cache/font/` に変換します。
再生成は `python3 tools/prepare_font.py`（ダウンロードなし）。上流スクリプトは実行しません。
submoduleの期待版は `f427b1e6bf743965c9b033d43fdf84b56f8f7543`。

## 2. STTとTTS

STT学習はNVIDIA CUDA環境が必要。検証環境はRTX5060Ti 16GB。
下記は新しい仮想環境用です。他プロジェクトの環境を変更しないでください。

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
# 元モデル条件とAUPを確認した場合だけ:
.venv/bin/python tools/fetch_stt_base.py --accept-community-license
.venv/bin/python fetch_fleurs.py
.venv/bin/python prepare_fleurs.py
.venv/bin/python train_ctc.py --layers 6 --name ctc6 --steps 5000
.venv/bin/python export_ctc.py --name ctc6 --checkpoint best --layers 6
cc -O3 -std=c11 runtime/native.c runtime/ctc_runtime.c -lm -o .cache/ctc-native
.venv/bin/python evaluate_packed.py --qa 5
# TTSモデル条件を確認した場合だけ:
.venv/bin/python fetch_tts.py --accept-model-license
```

CUDA対応のtorch wheelを使用してください。各取得プログラムは固定revisionを使用します。
pyopenjtalkの初回辞書取得は別の外部資産です。実機の漢字辞書とは別で、同梱しません。
STT出力は `.cache/ctc6/model-int8.bin`、TTSは `.cache/tts-v4.bin`。
録音・学習データはGitに入れません。学習結果のbit完全一致は保証しません。

## 3. 対話モデル

[日常会話BPE候補の全手順](../tiny_lm/DIALOGUE_EXPERIMENTS.md)に従います。
教師生成の言い換えを確認する工程は省略しないでください。別の生成物に既存の
確認済みハッシュを流用しないでください。教師の回答そのものを自動採用しません。
必要なパッケージは `tiny_lm/requirements-dialogue.txt`。
親モデル作成後、[追加学習と字幕・知識表の準備](REPLY_UPGRADE.md#再実行)を行います。
現行候補は `.cache/improvement-model-256/model.bin`。公開重みURLはありません。
生成コードを公開しても、学習元・派生物の条件を放棄したことにはなりません。

## 4. ファームをビルド

ESP-IDF **5.5.4**を別途導入し、その `export.sh` を読み込んでください。
既存のsdkconfigを意図せず流用しないよう、次の独立ビルドディレクトリを使用します。

```sh
idf.py -C firmware -B "$PWD/build-public" \
  -DSDKCONFIG="$PWD/build-public/sdkconfig" \
  -DSDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.bpe.defaults" \
  -DKLM_BPE_RUNTIME=ON build
```

ビルドにモデル重みは不要です。フォントと `python tools/prepare_reply_assets.py` による
字幕・知識表の生成は必要です（学習用Python依存環境を使用）。
新しい画面も1bitの15KB framebufferを使用し、字形はFlashに置きます。
オプション `SAAN_KANJI` は有効にしません。

## 5. 書き込み

ポートとチップ・16MB Flashを確認し、他のシリアル端末を閉じてください。
まず `python -m esptool --chip esp32s3 --port YOUR_PORT flash-id` で確認します。
WindowsのCOMポートはWindows Pythonを使用。WSLのパスを渡す場合はWindowsから
読めるUNCパスへ変換してください。Linuxの直接接続では `/dev/ttyACM*` 等を使用します。

初回セットアップには、同じビルドのbootloader・partition table・appと各モデルが必要です。
以下の配置を確認してesptool `write-flash` に渡します。無条件の全消去は不要です。

| アドレス | ファイル |
| --- | --- |
| `0x0` | `build-public/bootloader/bootloader.bin`（初回のみ） |
| `0x8000` | `build-public/partition_table/partition-table.bin`（初回・配置変更時） |
| `0x10000` | `build-public/rlcd42_stt_mic_probe.bin` |
| `0x210000` | `.cache/ctc6/model-int8.bin` |
| `0xa10000` | `.cache/tts-v4.bin` |
| `0xc10000` | `.cache/improvement-model-256/model.bin` |

既に同じ配置・モデルの実機なら、UI更新は `0x10000` のappだけです。
フルflashバックアップはNVSなどを含むため公開しないでください。
`0xb10000` の保存テスト音声は任意です。KEY/BOOT操作には不要。
`TEST`/`ECHO`/`TESTCHAT` はその音声がない新規実機ではエラーになります。
許諾未確認の参照音声を配布・自動取得しないため、ここでは同梱しません。

## 6. 検証

```sh
python3 -m unittest discover -s tests -p test_voice_ui.py -v
cc -Wall -Wextra -Werror -Iruntime tests/voice_buttons_test.c -o .cache/voice-buttons-test
.cache/voice-buttons-test
.venv/bin/python -m unittest test_ctc test_phonemes test_speech_trim -v
python3 tools/publication_check.py
```

任意の画面プレビュー: Pillowを導入したPythonで `tools/preview_ui.py` を実行。
実機と同じ描画コードの出力ですが、パネル写真ではありません。
シリアル115200/UTF-8/LFで `ID`、`ASKSAY きょおわつかれた`。
KEY/BOOTの実発話・音質・電池動作は利用環境で別途確認してください。
字幕は一時表示で、待機に戻って約8秒後に消えます（長文は延長）。文は次の操作まで
メモリに保持します。私的な会話の画面写真・ログを不用意に公開しないでください。
`tools/preview_ui.py --captions` で字幕付きの表示例も生成できます。
