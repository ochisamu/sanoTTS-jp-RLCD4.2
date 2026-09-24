# 学習元・モデル構成・評価

[English](TRAINING.en.md) · [トップ](../README.md)

モデル重み・コーパスは同梱しません。以下は現在の実機BPE候補の由来です。
別々の学習段階や不採用の教師を「すべて実機で動くモデル」と混同しないでください。

| 資産 | 用途 | 固定版 / 条件 |
| --- | --- | --- |
| [Moonshine Tiny Japanese](https://huggingface.co/moonshine-ai/moonshine-tiny-ja) | STTの初期encoder。decoderを41音素CTCに置換し6層を再学習 | `02ca41b3d9e73db07df9a13f316f2b7497a368e2` / Community License |
| [Google FLEURS](https://huggingface.co/datasets/google/fleurs) | 日本語train約6.69時間、2,164発話。正解文を自動音素化 | `70bb2e84b976b7e960aa89f1c648e09c59f894dd` / CC BY 4.0 |
| [LLM-jp OASST1 Japanese](https://huggingface.co/datasets/llm-jp/oasst1-21k-ja) | 日本語かな言語事前学習 | `f05b5816a8c1ce8c1f5ae3cd87ae5a7b6409fea5` / Apache-2.0 |
| [RealPersonaChat](https://github.com/nu-dialogue/real-persona-chat) | BPE・対話学習・意味蒸留用テキスト | `28d0b6b3865b29cabc26c230a2db37cdf315e937` / CC BY-SA 4.0 |
| [Qwen3-4B-Instruct-2507](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507) | PC上のみ。自作質問の言い換え候補を生成 | `cdbee75f17c01a7cc42f958dc650907174af0554` / Apache-2.0 |
| [multilingual-e5-small](https://huggingface.co/intfloat/multilingual-e5-small) | PC上のみ。入力表現の意味蒸留 | `614241f622f53c4eeff9890bdc4f31cfecc418b3` / MIT |
| [sanoTTS-jp](https://github.com/ayutaz/sanoTTS-jp) | 外部取得のv4 INT8音声合成。ここでは再学習しない | コード `f427b1e6bf743965c9b033d43fdf84b56f8f7543` / MIT、重みは独自条件 |

作者・論文・加工内容の詳細は [STT NOTICE](../licenses/NOTICE-Moonshine.txt)、
[対話データNOTICE](../licenses/dialogue-data-NOTICE.md)、[TTS NOTICE](../licenses/sanoTTS-jp-NOTICE.txt)。
`sarashina2.2-3b-instruct-v0.1` は教師候補の監査実験に使用しましたが、その生成回答を
自動採用せず、実機にも載せていません。元データの話者プロフィール・IDは対話学習から除外。
ユーザーの会話・個人録音は学習に使用していません。STT出力をLM学習に流用していません。

## 対話モデルの学習

かな変換 → BPE 1,024語彙 → 言語事前学習 → E5意味蒸留 → 日常短文への調整。
自作114系統・286質問に、確認済みの教師言い換え336件を加え、独立質問は622件。
接頭辞などの展開後14,928行ですが、14,928種類の意味を学んだわけではありません。
最終回答は自作の短文です。確認は開発エージェントによるもので、外部の人手評価ではありません。
この親モデル単体はトークン生成で、暗記依存が強いです。
現行機はさらに38分野の追加学習と別経路の知識表を導入しています。
[新しい比較結果・モデルSHA・漢字字幕・知識表](REPLY_UPGRADE.md)を参照。
以下のLM測定値とSHAは追加学習前の親モデルの記録です。

| 評価 | 結果と限界 |
| --- | --- |
| STT | 調整用dev64件。FP32最良PER13.57%、高速W8A8 PER14.49%。漢字CERではない |
| LM代表質問 | 114/114完全一致。学習済みの意味・返答での確認 |
| LM言い換えdev | 85/137完全一致。既知の意味に対する未学習表現。選定にも利用 |
| 選定後40質問 | エージェント評定21合格・4部分・15失敗。独立の会話精度ではない |
| 実機32質問 | 全文がnative Cと一致。意味の正しさを証明するものではない |

STT SHA256は生成物のmanifest、実機LMは
`985505b6abfe3504ccadd6b535a48a87e8a48ebb61183af0e9d8305cf5ef26e7`、TTSは
`a1eb6b0812e2ad2a228836088a3e34160cb66731492fb957a5891605db2fa1b6`。
学習seed固定でもCUDA等の差で完全同一の重みになるとは限りません。
[再実行手順](REPRODUCE.md)、[学習コマンド詳細](../tiny_lm/DIALOGUE_EXPERIMENTS.md)を参照。

## 公開上の注意

RealPersonaChat由来の加工データには継承条件があり、学習重みへの適用は未確定です。
追加学習しても由来は消えないため、現在の対話重み・tokenizerは配布保留です。
制約を減らす別系統は、許諾を整理したデータでtokenizerと重みの初期化から再学習する必要があります。
UsefulSensorsの検証音声は許諾不明のため同梱せず、学習にも使いません。
