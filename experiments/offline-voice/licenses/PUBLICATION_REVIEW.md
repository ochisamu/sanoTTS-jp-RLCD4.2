# Publication review / 公開条件の一次監査

Reviewed 2026-09-24. Technical provenance review, not legal advice or release approval.
The initial review did not publish files. The source publication now includes a
model-free developer-preview firmware package; weights remain withheld.
See [release scope](../docs/FIRMWARE_RELEASE.md) and [binary notices](DEPENDENCIES.md).

## 結論

コードと再現手順の公開は、第三者表示を保持し、重み・録音・データを分離する方針で
進められます。ただし現状はリリース監査完了ではありません。
**システム全体・統合flashイメージ・派生重みをMITとして配布しないでください。**
モデルを外部取得にしても利用条件は消えません。

| 対象 | 確認結果 / 公開前の条件 |
| --- | --- |
| 自作コード | MIT。ただし第三者由来部分のライセンス・著作権表示を保持 |
| CharDock DSP / Waveshare BSP | Apache-2.0。本文・NOTICE・改変説明を同梱 |
| STT派生重み | Moonshine Community License。条件付き再配布可。MITではない |
| FLEURS音声・加工データ | CC BY 4.0。出典・作者・変更表示等が必要。今回は非同梱 |
| 現在のBPE対話重み・tokenizer | RealPersonaChat由来工程あり。重みへのShareAlike適用・配布条件が未確定なので配布保留 |
| sanoTTS-jpコード | MIT。モデルは別条件 |
| sanoTTS-jp v4重み・統合イメージ | 独自モデル条件。帰属・用途制限・条件の引継ぎ、Apache本文などが必要 |
| 個人録音・flash全体バックアップ | 公開しない。NVSなどを含む可能性もある |
| UsefulSensors/multilingual_examples | カードに明示許諾がないため音声・正解文・加工物の同梱を保留 |

## Moonshine STT

固定revisionの `.cache/model/LICENSE.txt` を確認し、全文を
`Moonshine-Community-LICENSE.txt` に保存。改変説明は `NOTICE-Moonshine.txt`。
[公式ライセンス](https://huggingface.co/moonshine-ai/moonshine-tiny-ja/blob/main/LICENSE.txt)
は研究・非商用、および条件付き商用利用・再配布を許諾しています。

- 配布時に契約全文と指定NOTICE、目立つ `Powered by Moonshine AI` 表示が必要。
- 商用は登録が必要。関連会社を含む年間売上が100万米ドルを超える場合は別契約が必要
  （統合エンドユーザー製品の受領者に関する例外など、正確な条件は全文を参照）。
- モデルや出力による、別の基盤生成AIモデルの作成・改善には制限あり。
  現在の対話モデルの学習はSTT認識結果を使用していません。
  STT出力を単に推論入力として渡す設計と、再学習に流用する設計は区別してください。
- [AUP](https://moonshine.ai/use-policy) は年齢条件と、相手に知らせない録音・監視の禁止等を含む。
- 今後さらにSTTを蒸留・縮小しても、派生モデルの条件を自動的に除去できません。

## 対話LM

親モデル SHA256: `985505b6abfe3504ccadd6b535a48a87e8a48ebb61183af0e9d8305cf5ef26e7`。
現行の追加学習モデルは `0c9037b28e675339719cc496e8cd3d180712ed0838292170de241d6b1687b53c`。
どちらの重みも今回のReleaseに含めません。
日常会話の最終回答は自作でも、BPE学習・事前学習・意味蒸留の工程に
[RealPersonaChat](https://github.com/nu-dialogue/real-persona-chat) を使っています。
加工データには[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)を尊重する必要があり、
学習重みが法的に翻案物に当たるかはこの技術監査では確定できません。
「CC BY-SAは商用不可」ではありません。また「学習すれば自動的にMIT」でもありません。

公開を簡素化するなら、当該コーパスを使わずtokenizerから再構築し、重みも初期化して
独自データ等で再学習する別系統が候補です。既存重みの追加学習だけでは履歴を除去できません。
OASST、Qwen、E5等の別条件・出典は `dialogue-data-NOTICE.md` を参照。

## TTS / デモ動画

`fetch_tts.py` はv1.0.0のv4重みを取得します。v3のJSUT表示を機械的に付けないでください。
上流 `third_party/sanoTTS-jp/LICENSE-MODEL.md` と `NOTICE.md` が基準です。
初回監査で欠けていたTTS専用NOTICEとApache本文は補完しました。
日英の利用条件と音声出力規約も追加済みです。漢字プロファイル用の参照NOTICEは未同梱ですが、
現在のかな専用ビルドには漢字辞書は入っていません。将来含めるなら再監査が必要です。

[つくよみちゃん公式条件](https://tyc.rei-yumesaki.net/material/corpus/) は
2026-09-17更新表示でした。ソフト公開時の帰属と出力利用規約を明示し、派生・再配布にも
引き継ぐ必要があります。別キャラクター専用の音声合成ソフトとしての公開と、
生成音声のアテレコ利用は扱いが異なるため、独自キャラ製品化時は提供元に確認してください。

動作紹介動画は、音声を自由な再利用素材として配らず、禁止用途に該当しない内容にし、
研究発表として適切なクレジットを付ける方向で検討できます。元コーパス音声の転載とは別です。
自動生成回答が問題のある内容になる可能性があるので、公開動画の音声は事前確認してください。

## 公開前に残る作業

1. 初回ソース候補の機械チェックを `tools/publication_check.py` で実施。現時点で親リポジトリにコミット履歴はない。
   公開直前に再実行し、新しい履歴・submodule・対象ファイルの最終レビューを行う。
2. TTS v4の必須帰属文は固定上流と機械照合。提供元条件の変更を公開直前に再確認する。
3. ESP-IDF / esp_codec_devの本文と依存一覧、東雲原文・作者・固定ハッシュを追加済み。
   バイナリRelease前にはツールチェーンも含む全リンク依存の表示を最終確認する。
4. 対話重みの条件を解決するまで、統合イメージ・重みReleaseは作らない。
5. STT商用利用を想定する場合は登録・売上条件・AUPを利用主体に確認。

English: source publication and weight publication are separate decisions.
Source/docs can proceed after attribution and artifact checks. Do not claim the
whole system is MIT or ship the current combined flash image as license-cleared.
Current dialogue weights remain on hold; legal uncertainty is not a finding that
CC BY-SA prohibits ML training or commercial use.
