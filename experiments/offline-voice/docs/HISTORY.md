# Historical notes: RLCD4.2 Japanese offline STT feasibility lab

This preserves earlier measurements and intermediate states. It is not the current
quick-start; use the repository-root README. Paths below are relative to the original
repository root. In particular, the current firmware includes BOOT voice replies.

**研究用・未完成。ESP32-S3実機でSTT推論に成功、マイクからの復唱を検証中です。**
2026-09-24追記: 待機処理の調整で同じ6.6秒音声のSTTは中央値12.992秒になりました
（3回、従来13.566秒、約4.2%短縮）。認識の全フレームargmaxハッシュは一致。
リアルタイムには未達です。詳細は [高速化記録](docs/stt-speed-20260924.md)。
公開条件は [資産別ライセンス監査](licenses/PUBLICATION_REVIEW.md) を参照。
コードのMITはモデル重みには適用されません。現在の統合イメージ・対話重みの公開は保留です。
続行分の実機マイク検証・学習状況は [docs/progress.md](docs/progress.md) を参照。
Charadock、既存のRLCD/ATOM sanoTTSデモとは独立しています。
2ボタン版: **KEY＝復唱、BOOT＝回答生成**。押して離すと5秒録音します。
PWRは電源用のまま。BOOTを押したまま起動すると書き込みモードになるので避けてください。
回答生成は品質未達の実験機能で、常時録音・ネット通信はしません。
モデル・音声はGitに含めず、固定revisionから外部取得します。

日本語の小型生成LMを追加する独立実験は [tiny_lm/README.md](tiny_lm/README.md) を参照。
約1.46MiBのモデルで実機の短文生成・TTS接続まで確認しましたが、未学習の言い回しは
dev 27/54件のみ期待返答と一致。一般会話には未達で、KEYの動作は従来の復唱のままです。
このLMの重みは外部取得ではなく、同梱の小さな合成コーパスからローカル学習します。

対話の拡張・事前学習・蒸留の比較は [tiny_lm/DIALOGUE_EXPERIMENTS.md](tiny_lm/DIALOGUE_EXPERIMENTS.md)
を参照。ユーザー依頼で約3.07MBのBPE候補を実験導入済みです。
現在の構成は [tiny_lm/BPE_DEVICE.md](tiny_lm/BPE_DEVICE.md) を参照。
生成件数や学習lossを会話精度として扱わず、品質確認前に自動で実機へ反映しません。

## 現在の実装（2026-09-24）

マイク → 音素CTC（W8A8）→ かな → sanoTTS → スピーカーを本体上で実行します。
Wi-FiもPCの音声認識も使いません。PC/GPUは学習とモデル書き込みに使用します。
KEYを押して離すと5秒録音し、認識と読み上げを順番に行います。

- 6層Moonshine encoder＋41音素CTCへ再学習。packedモデルは7,808,724 bytes。
- 6.6秒の公開検証音声をESP32で13.565秒で認識（初版36.031秒から短縮）。ネイティブC版と全フレームの
  argmaxハッシュが一致しました。リアルタイムではありません。
- FLEURS日本語trainの6.69時間で学習。調整に使用したdev64件で音素誤り率は
  FP32最良13.57%、初期W8A8実装14.07%、高速版14.49%。独立test精度や実環境の精度ではありません。
- ユーザー発話を5秒録音→認識（24.228秒）→TTS合成→再生→マイク復帰まで
  実機ログで確認。認識結果の先頭に余分な音が入りました。
  ユーザーが復唱を聴取済みですが、遅延と音質は実用に不足との評価です。
  **高速版の実発話、最新DSPの聴感、USBを抜いた電池動作は確認待ちです。**
- スピーカー・電池は接続したまま。アンプは録音・認識・合成中OFF、再生前に
  ミュート・無音DMA・音量レジスタの照合を行います。

詳しい手順と制約は [docs/progress.md](docs/progress.md) を参照してください。

### 遅延・音質の改善と残る限界

最新ファームはCharDock由来のDSPを端末内で実行します。RLCDの聴感に合わせ
300Hz/24dB-octハイパス、550Hz -4dB、2.6kHz +5dB、ソフトニー圧縮、
ピーク上限0.7、前後8msフェードを使用。ES8311音量は工場設定の上限100以内です。
DSP原版はJavaScriptとの比較を維持し、RLCD調整版は別プロファイルにしています。
TTSのduration倍率は0.95（1.45→1.15からさらに高速化、ピッチは維持）です。

STTは整数SIMD注意機構、数学関数の補間表、除算回数削減、内部RAMのタイル化を使用。
5秒の録音から前後の無音を250msの余裕付きで除きますが、録音自体は最大5秒固定です。
**6.6秒入力に13.6秒かかるため、自然な会話の応答速度には達していません。**
補間・量子化による精度低下を含みます。短文での実測前に速度を外挿しないでください。

## 初期の容量検証（以下は履歴）

- COM4実機: ESP32-S3、flash 16MB、PSRAM 8MBを確認。
- RTX 5060 Ti 16GBで日本語STT推論、疑似INT8、層削減、3ステップの学習試験を実施。
- 実測・取得ファイルSHA256: `results/feasibility.json`。
- 初回ベンチマーク時はファームを保持。続行分ではマイク検証用ファームへ書き換え、
  5秒のマイクデータ転送まで確認済み。**端末内STTは未達。**

日本語公開サンプル1件（10.44秒）だけです。精度評価用ベンチマークではありません。
CERは句読点・表記揺れを正規化しない文字編集距離です。

| 実験 | パラメータ数 | INT8重みのみの理論量 | 1件のCER |
| --- | ---: | ---: | ---: |
| Moonshine Tiny Japanese | 27,092,736 | 25.84MiB | 18.75% |
| 8bit丸め→FP32計算 | 同上 | 同上 | 18.75% |
| encoder/decoder各6層→3層、再学習前 | 19,113,696 | 18.23MiB | 100% |

疑似8bitはFP32計算であり、INT8ランタイムや実メモリ削減の検証ではありません。
GPU生成約0.42〜0.49秒はESP32速度に外挿できません。層削減後の短い時間は認識崩壊による
短い出力のためで、性能改善ではありません。

間引いたモデルの全パラメータをAdamWで3ステップ更新できました。
batch=1、10.44秒、BF16 autocast/FP32 parameters、PyTorch peak allocated約392MiB。
これはGPU全使用量や長時間学習の必要容量ではありません。
学習と推論に同じ1件を使用し、汎化・回復学習の成功は示しません。派生重みは保存しません。

## 初期の設計案（現在は上記CTCを実装済み）

語彙embeddingだけで9,437,184パラメータ（INT8理論9MiB）。層の間引きだけでは不十分です。
次は既存encoderを流用し、decoderを小さな**かな/音素CTC出力**へ置き換える案を検証します。
新しい出力層の学習と認識能力の回復が必要です。128記号+blankの仮定なら、
3層encoder+CTCは約4.51MiB/INT8の重み量です（`python budget.py`）。
記号集合は未確定で、これは実装済み認識器ではなく容量見積りです。

1. 利用条件が明確な日本語音声・かな/音素正解を用意し、話者別に学習/評価を分離。
2. 小型CTCを学習し、未学習話者の誤り・無音誤発話を評価。
3. packed INT8とESP32-S3演算を実装し、活性値込みPSRAM・flash・遅延を実測。
4. ES7210マイク入力を独立検証し、録音→認識→sanoTTSを順次実行。
5. かな入力TTSで漢字辞書を省き、STT/TTS作業領域を共用。

既存漢字辞書13,702,320 bytesとTTSモデル654,032 bytesがあるため、
まず漢字表示ではなく**任意の日本語を聞いてかな経由で復唱**する構成を目指します。
重みをflashから読む構成もあるので、8MB PSRAMより重みが大きいことだけで不可能とは
判断しません。作業領域の実測が必要です。完全独立動作・実用精度は未達です。

## 再実行 (Linux/WSL2 + NVIDIA GPU)

Python 3.12とuvを用意して実行します。

```sh
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python torch==2.10.0 --index-url https://download.pytorch.org/whl/cu128
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python -m unittest -v
.venv/bin/python benchmark.py --download
.venv/bin/python budget.py
```

約108MBのモデル、tokenizer、約670KBの日本語parquet等を取得します。
revision固定、認証token/リモートコード/pickleモデル不使用。
次回は `--download` を省くとmanifestハッシュを検証してローカルのみで実行します。
`results/feasibility.json` は実行ごとに更新されます。必要なら先に結果をコピーしてください。
速度・出力は環境に依存し、CUDAの決定性は保証しません。
今回は既存Python環境を読み取り利用し、追加pyarrowのみignored cacheへ導入しました。
上記のクリーン環境構築手順自体は未検証です。

## 外部資産・公開上の注意

Powered by Moonshine AI

- [モデル固定revision](https://huggingface.co/moonshine-ai/moonshine-tiny-ja/tree/02ca41b3d9e73db07df9a13f316f2b7497a368e2)
  は[Moonshine AI Community License](https://huggingface.co/moonshine-ai/moonshine-tiny-ja/blob/02ca41b3d9e73db07df9a13f316f2b7497a368e2/LICENSE.txt)。
  Apache/MITではありません。配布、商用、派生モデル等の条件を採用前に確認してください。
- [音声サンプル](https://huggingface.co/datasets/UsefulSensors/multilingual_examples/tree/badcb6e16db6bc982b48e2befb30c771f2ebb511)
  のカードには明確なライセンス指定がありません。ローカル動作確認のみとし、
  音声・正解文・生成文をignored cacheに限定。本学習データ・公開物には採用しません。
- 重み/ライセンスは `.cache/model`、音声は `.cache/dataset`。
  再配布する場合は必要なライセンス/NOTICE等を別途同梱してください。
- in-memoryの丸め・層削減・短い学習のみで、派生重みは配布しません。
- MAC、シリアル番号、ユーザー音声、資格情報はレポートに保存しません。
- GitHubへの公開・pushは行っていません。

## English summary

Independent research lab with an experimental on-device STT/phoneme-to-kana/TTS
firmware. A 7.81MB packed W8A8 encoder-CTC model runs on ESP32-S3: 13.565 seconds
for a 6.6-second reference clip, matching the native C frame-argmax hash exactly.
The tuned 64-clip development subset has 14.49% phoneme error in the optimized
runtime (14.07% before approximate attention/math); this is not an
independent test-set result. Fixed-phrase synthesis/playback and microphone reopen
complete on hardware. A live microphone-to-STT-to-TTS run also completed after
fixing a task-stack overflow (24.228 seconds for STT), but recognition inserted an
extra initial phoneme. Actual audibility and unplugged battery operation still
require user verification. CharaDock-derived DSP runs locally with an RLCD-specific
EQ, compressor, limiter and fades. The user confirmed hearing the earlier live
repetition but found latency and quality inadequate. Even the optimized full-clip
runtime is slower than real time; it is not a usable conversational system yet.
Press/release KEY to capture
five seconds. Neither recognition nor synthesis uses a PC or network at runtime.

Historical feasibility experiment: The RLCD was identified as
16MB flash / 8MB PSRAM. Follow-up work flashed a microphone-only probe and verified
five-second PCM transfer (see docs/progress.md). One Japanese 10.44-second
clip was used for GPU inference and three training steps, not an accuracy study.

INT8 weight rounding preserved this clip's raw CER, but the 27.1M model requires
25.84MiB of ideal 8-bit weights alone. Removing half the layers broke recognition.
A pretrained encoder with a new kana/phoneme CTC head is the next hypothesis,
requiring training and evaluation; that follow-up is now implemented as described above.

Commands above reproduce the experiment. External assets use pinned revisions
and are excluded from Git. Review the Community License before distribution.
The sample dataset has no explicit license in its card and is not our training corpus.
