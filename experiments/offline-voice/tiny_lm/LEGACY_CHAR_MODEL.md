# Historical character-model measurements / 旧文字モデルの記録

Historical 26-family / 192-wide model notes. The current BPE model, training lineage,
controls and UI are documented in [README.md](README.md) and the root README.
Old commands/metrics below must not be presented as current-model results.

**RLCD4.2上の生成・TTS接続に成功。会話品質は未達です。**
PCは学習と文字入力にだけ使用し、返答生成・音声合成はESP32-S3で行います。
KEYはSTT→復唱、BOOTはSTT→LM→TTSです。通常起動後に押して離してから話してください。
BOOTを押したまま電源を入れるとダウンロードモードになるため注意してください。
LMは研究用機能で、`ASK` / `ASKSAY` の文字入力も引き続き利用できます。

新しい事前学習・日常会話拡張・意味蒸留のホスト実験は
[DIALOGUE_EXPERIMENTS.md](DIALOGUE_EXPERIMENTS.md) を参照。
現在の実機には、ユーザーの依頼で114系統のBPE候補を実験導入しました。
生成32件の一致・メモリ解放を確認。手順と復旧方法は
[BPE_DEVICE.md](BPE_DEVICE.md) を参照してください。
以下の実機実測・学習手順は従来の26系統モデルの記録で、新候補の性能ではありません。

## 2026-09-24 実測

| 項目 | 結果 |
| --- | --- |
| モデル | 自作causal Transformer、4層、幅192、6 heads、FF512、文脈128 |
| 規模 | 1,427,136 parameters、W8A8、128文字語彙、かな中心 |
| 保存容量 | 1,530,672 bytes（約1.46MiB）、語彙・スケール込み |
| 作業メモリ | 実機794,960 bytes。別途、重みをPSRAMへ読み込む |
| 実機の生成速度 | 約33.4〜36.5文字/秒、中央値35.1（80件） |
| 読み込み＋入力処理＋生成 | 0.637〜1.356秒、中央値0.925秒（TTSを含まない） |
| 実機連続検証 | 80/80件でnative C版と返答全文一致、PSRAMの残留減少なし |
| 推論中のPSRAM空き | 5,739,084 bytes（約5.47MiB） |
| 既知の代表質問 | 26/26件で許容返答と完全一致 |
| 未学習の言い回し / dev | 27/54件（50%）で許容返答と完全一致 |

速度はこの短い合成コーパス・単文字tokenizerでの実測です。長文、一般的な
日本語LLM、多ターン会話へ外挿できません。モデル読み込み約208msも含めて測定。
詳細は `results/tiny_lm_device.json` と `results/tiny_lm_dropout_packed.json`。

最初のモデル（dropoutなし、1,000 steps）はdev 17/54（31.5%）。
第2モデル（dropout 0.15、3,000 steps）を採用しました。複数条件を変更しており、
改善をdropoutだけの効果とは断定できません。devをモデル選定に使っているため、
**独立した最終test精度ではありません**。

## 品質の限界と採用判断

- 事前学習済みの日本語モデルではありません。オリジナルの小さな合成データから学習。
  26種の挨拶・気分・自己紹介・不明応答、1,260行（接頭辞などの展開を含む）。
  独立した1,260通りの意味・知識を学んだわけではありません。
- devは質問の言い回しを分離していますが、intentと返答は既知です。
  未知の話題への汎化、事実の正確さ、認識誤りへの頑健さは保証しません。
- 回答一覧から選ぶコードではなく、文字を逐次生成します。ただし学習規模が小さく、
  返答の暗記に強く依存しています。無関係な返答や壊れた語尾も残ります。
- 「りこ」は実験用の仮名です。PCの時刻、天気、ニュース、個人情報には接続しません。
- TTS接続時は句読点をsanoTTSの区切り記号に変換。完全な日本語G2Pやアクセント推定ではなく、
  「は」「へ」、長音などの読み分けは未解決です。現行DSP・duration倍率0.95は保持。
- LM→sanoTTS→再生完了→マイク再開までログで確認。音質・聴感の確認は別途必要です。
- 現状では品質ゲート不合格。ユーザー依頼によりBOOTボタンで実験的にSTT→LM→TTSを接続。
  常時動作ではなく明示的なボタン操作でのみ起動します。既存STTの遅さもこの追加では解決しません。

次の判断材料は、十分に多様な日本語対話データを用いた事前学習／蒸留と、
話題・言い回しを分離した未使用testです。容量と演算速度は確認できたので、
今後はファームよりデータと汎化を優先します。外部データを使う場合は利用条件も確認します。

## 今すぐ試す（書き込み済み実機）

Windowsで `console.cmd` を開くと、かな入力を繰り返せます。`/quit` で終了。
既存の `%USERPROFILE%\.platformio\penv\Scripts\python.exe` を使用します。
別環境では `KLM_PYTHON` にpyserial導入済みPythonの絶対パスを設定してください。
シリアルモニターなど、COM4を使用する他のアプリは閉じてください。

```text
kana> きょうはつかれた
LM_REPLY:がんばったね。ゆっくりやすんでね。
kana> なまえをおしえて
kana> /quit
```

コンソールは文字だけを送ります。PCでLM推論や音声生成はしません。
漢字は未対応。かな最大80文字、返答最大40文字。未対応入力はエラーとして拒否。
PCから切断するとこの文字入力は使えませんが、推論にPCは不要です。

```sh
python -X utf8 tiny_lm/console.py --port COM4 --say
# 一度だけ。--sayを省略すると音を出さず、文字生成のみ
python -X utf8 tiny_lm/console.py --question "きょうはつかれた" --say
```

任意のシリアル端末（115200 baud、UTF-8、行末LF）からも使えます。
`ASK きょうはつかれた`、`ASKSAY きょうはつかれた`、`LMBENCH`。
入力・音声はネットへ送りません。`--log` 指定時だけ質問と応答をローカル保存します。

## 学習・評価の再実行

Linux/WSL、NVIDIA CUDA対応GPU、Cコンパイラを使用。実測環境はRTX5060Ti 16GB、
PyTorch 2.10.0+cu128、numpy 2.2.6、safetensors 0.7.0。
選択モデルの学習・評価は約27秒、PyTorch peak allocated約148MiBでした。
**この小さなコーパスだけの値**で、一般的な日本語事前学習の費用ではありません。

```sh
python -m venv .venv-lm
.venv-lm/bin/pip install torch==2.10.0 --index-url https://download.pytorch.org/whl/cu128
.venv-lm/bin/pip install -r tiny_lm/requirements.txt
.venv-lm/bin/python tiny_lm/train.py --steps 3000 --dropout 0.15 --out .cache/tiny-lm-dropout
.venv-lm/bin/python tiny_lm/evaluate.py --model .cache/tiny-lm-dropout/model.bin --out results/tiny_lm_dropout_packed.json
KLM_TEST_MODEL=.cache/tiny-lm-dropout/model.bin .venv-lm/bin/python -m unittest discover -s tiny_lm -p 'test_lm.py' -v
```

初回比較は `--steps 1000 --dropout 0 --out .cache/tiny-lm`。
学習スクリプトは指定outの生成物を更新するため、比較時は別のoutを指定してください。
seed固定でもCUDA・バージョン差によるbit単位の再現は保証しません。
採用重みSHA256：`8cb6fbb462db6c0d8b2600fd6cdd2508eeabe4d6dc8cd90ece17e57bb4f6deef`。
外部重みの取得は不要。この実験はゼロから学習します。重みをGitに入れません。

## ファームの再現（RLCD4.2 N16R8専用）

既存STT/TTS資産はリポジトリ本体の手順で用意してください。LMだけではそれらを代替しません。
ESP-IDF 5.5.4をactivateし、リポジトリルートから実行します。

```sh
idf.py -C firmware -B build-lm -DSDKCONFIG="$PWD/build-lm/sdkconfig" build
```

**専用SDKCONFIGを明示してください。** 既存の `firmware/sdkconfig` には古い
single-app設定が残り得ます。`build-lm/sdkconfig` でcustom partitionと
`CONFIG_ESP_MAIN_TASK_STACK_SIZE=24576` を確認してください。

追加領域は `tiny_lm: 0xc10000, 0x200000`。既存app/STT/TTS/testaudioは移動しません。
まだ約1.94MiBが未割り当てです。ブートローダー/eFuse/セキュリティ設定は変更しません。

既存ラボファームの動くRLCD、16MB flash/8MB PSRAMを識別し、バックアップを確認してから：

```sh
python -X utf8 -m esptool --chip esp32s3 --port COM4 --baud 460800 write-flash 0x8000 build-lm/partition_table/partition-table.bin 0x10000 build-lm/rlcd42_stt_mic_probe.bin 0xc10000 .cache/tiny-lm-dropout/model.bin
python -X utf8 tiny_lm/device_eval.py --out .cache/tiny-lm/device-recheck.json
```

WindowsのCOMポートにはWindows Pythonを使用します（WSLのPythonからCOM4は開けません）。
これは**既存ラボからの更新手順**で、初期状態からの完全インストールではありません。
`device_eval.py` は元の80問を再測定する回帰テストで、独立testではありません。
既存レポートの上書きを避けるため、出力先が存在すると停止します。

元へ戻す場合、この作業前のapp `firmware/build-stt/rlcd42_stt_mic_probe.bin` と
読み取り保存した `.cache/tiny-lm/pre-lm-partitions.bin` をそれぞれ0x10000/0x8000へ戻せます。
残るLMデータは旧ファームから使われず、全Flash消去は不要です。

## English summary

Experimental 1.43M-parameter, character-level kana decoder trained from scratch
on a tiny original synthetic reply corpus. The 1,530,672-byte W8A8 model runs
entirely on an ESP32-S3 RLCD4.2, alongside the existing STT and sanoTTS assets.
Eighty device replies matched native C exactly, with no residual PSRAM loss.
Median load+prefill+generation: 925ms; median decoding: 35.1 characters/second.
These timings exclude STT and TTS. The selected model gets 26/26 canonical
questions but only 27/54 held-out phrasings exactly right; this is a tuned dev
set with known intents/answers, NOT an independent test or general conversation.

Text-to-LM-to-TTS playback completed on hardware. Audibility is a separate check.
KEY still performs the original microphone echo: automatic voice-to-LM is not
enabled because reply quality has not passed the gate. Use the opt-in UTF-8
serial `ASK`/`ASKSAY` commands or `console.py --say` (kana only). No PC inference,
network services, downloaded weights, or paid APIs are used. Training weights
remain in ignored cache directories. No publication or push was performed.

The portable C implementation is original lab code, except the PIE dot-product
adapted from MIT-licensed sanoTTS-jp (see `licenses/sanoTTS-jp-MIT.txt`). No Ivy AI
or MineralLLM code/weights were imported. Existing STT/TTS assets retain their
own separate upstream terms.
