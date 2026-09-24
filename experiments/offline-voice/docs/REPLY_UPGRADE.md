# 漢字字幕・追加学習・端末内知識

[English](REPLY_UPGRADE.en.md) · [トップ](../README.md)

## 回答経路

認識結果（かな）→端末内の知識表を検索→一致すれば確認済み短文、
一致しなければSLMがトークン生成→表示文と読みを分離→sanoTTS。
KEYの復唱は変更せず、BOOT/CHAT/ASK/ASKSAYの回答経路だけに適用します。
ネット接続・PC推論・常時録音・会話履歴は追加していません。

知識は16項目・48種類の質問表現。句読点と一部の呼びかけを除く全文一致です。
計算・単位・端末の使い方が対象で、任意の計算機や意味検索ではありません。
数字違いの質問を近似一致で誤って拾わないため、部分一致を使いません。
該当しない質問はSLMへ渡すので、未知の質問を必ず拒否できる保証もありません。
これは「検索して文章をSLMへ渡すRAG」ではなく、知識表と生成モデルの併用です。
ログの `REPLY_SOURCE:LOCAL_KNOWLEDGE:<id>` / `REPLY_SOURCE:SLM` で区別できます。

漢字字幕は149種類の確認可能な回答全文と読みの対応表です。未知・曖昧な読みは
かなのままにし、自由文のかな漢字変換は行いません。TTSへ漢字は渡しません。
`DISPLAY_REPLY:` が表示文、`LM_REPLY:` が読みです。歴史的なコマンド互換のため
知識表経路でも `LM_REPLY` という名前ですが、その経路でLMを実行した意味ではありません。
STTの字幕は引き続きかなです。大きな顔・英語ステータス・一時字幕・DSPは維持します。

## 追加学習と比較

自作38分野・114問を追加。否定、曖昧さ、未知情報、知識表の短い事実を含みます。
接頭辞と反復による重み付け後、既存データと合わせ17,664行。
反復行は独立した質問ではありません。利用者の録音・会話は学習していません。
元データは `tiny_lm/improvement_data.py` と `knowledge_data.py`（自作MIT）。
親モデルのRealPersonaChat等に関する条件は継承し、重み配布は引き続き保留です。

同じ旧モデルからRTX5060Tiで追加学習。4層・幅256・6000ステップ、最良dev NLLの
2000ステップのチェックポイントを採用。約121秒、学習GPUメモリ約716MiB。
W8A8化後のモデルは3,074,496 bytesで、旧モデルから増えていません。

| 未学習の質問表現での完全一致 | 旧モデル | 追加学習4層 |
| --- | --- | --- |
| 既存分野 | 85/137 | 88/137 |
| 追加分野 | 2/38 | 27/38 |
| 合計 | 87/175 | 115/175 |

句読点を除いた完全一致で、知識検索を使わないSLM単体の評価です。
既知の回答分野の開発用セットであり、一般会話の正答率・独立した最終試験ではありません。
同義の適切な返答も不一致になります。一方「見つからなかった」に「見つかってよかった」
と答える例など、明確な誤答も残ります。医療・法律・投資判断などには使えません。

導入モデルSHA256:
`0c9037b28e675339719cc496e8cd3d180712ed0838292170de241d6b1687b53c`。

5層候補も同じ親モデル・データ・6000ステップで比較しました。追加した最後のブロックは
残差の出力をゼロ初期化し、最初は恒等変換にしています。結果は113/175（既存83/137、
追加30/38）、3,740,096 bytes。4層より大きく、既存分野の成績も低いため採用しません。
これは一条件での比較であり「大型化は常に無効」という結論ではありません。
5層はホストW8A8評価のみで、実機速度は未測定。実機の区画は変更していません。

4層の実機検証は32/32が参照出力と一致し、確認したSLM31件は999–1719ms
（認識・TTSを除く）。残る1件は知識経路です。別途16項目すべてで読みと漢字表示文を
ログ検証し、知識経路とSLM経路の両方でTTS完了を確認しました。聴感・画面の見え方は
利用者による確認が別途必要です。

## 再実行

まず [既存学習手順](../tiny_lm/DIALOGUE_EXPERIMENTS.md) に従って依存関係・
`.cache/daily-aug-bpe/` と旧 `.cache/daily-semantic-bpe-256/best.safetensors` を準備。
重み・コーパスの取得や再学習には各条件への同意が必要です。
以下の `python` は既存の学習依存環境を指します。別プロジェクトの環境を変更しないでください。

```sh
python tiny_lm/prepare_improvement.py
python tools/prepare_reply_assets.py
python tiny_lm/dialogue_train.py --stage dialogue --steps 6000 --dim 256 --bpe --resume .cache/daily-semantic-bpe-256/best.safetensors --data .cache/improvement-bpe --out .cache/improvement-model-256 --lr 0.00015
python tiny_lm/export_bpe.py --checkpoint .cache/improvement-model-256/best.safetensors --tokenizer .cache/improvement-bpe/tokenizer.json --out .cache/improvement-model-256/model.bin
python tiny_lm/evaluate_daily.py --model .cache/improvement-model-256/model.bin --data .cache/improvement-bpe --out .cache/improvement-model-256/eval.json
python -m unittest discover -s tests -p test_reply_support.py -v
```

5層の比較のみ（現行機へ書き込まない）:

```sh
python tiny_lm/dialogue_train.py --stage dialogue --steps 6000 --dim 256 --layers 5 --expand-last --bpe --resume .cache/daily-semantic-bpe-256/best.safetensors --data .cache/improvement-bpe --out .cache/improvement-model-5layer --lr 0.00015
python tiny_lm/export_bpe.py --checkpoint .cache/improvement-model-5layer/best.safetensors --tokenizer .cache/improvement-bpe/tokenizer.json --layers 5 --max-bytes 0x3f0000 --out .cache/improvement-model-5layer/model.bin
python tiny_lm/evaluate_daily.py --model .cache/improvement-model-5layer/model.bin --data .cache/improvement-bpe --out .cache/improvement-model-5layer/eval.json
```

既存の学習結果を上書きしないため、準備済みデータや完了した学習ディレクトリでの再実行は
拒否します。新しい実験では別ディレクトリを使用してください。
字幕・知識のC表だけなら `tools/prepare_reply_assets.py` は学習コーパス・重みなしで
自作ソースから再生成できます（かな変換等のPython依存は必要）。生成先は `.cache/reply-assets/`。
ビルド手順は [再現ガイド](REPRODUCE.md)。同じ区画の実機更新はapp `0x10000` と
新SLM `0xc10000` のみ。STT/TTS・bootloader・partition tableは変更しません。
5層候補は別実験であり、既存3MiB区画に収まらないためそのまま書き込まないでください。

試す言葉: 「一週間は何日」「一足す一は」「宿題はまだ終わってない」。
音声認識の誤りは別途起こり得ます。入力例・成功例だけで精度を判断しないでください。
