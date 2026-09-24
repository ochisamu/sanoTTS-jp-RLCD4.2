# ライセンス・公開範囲

[English](README.en.md) · [トップ](../README.md)

2026-09-24確認。法的保証ではなく、出典と条件を追跡するための案内です。
自作コードは[MIT](../LICENSE)。以下の別条件を上書きするものではありません。

| 区分 | 条件 / 保存した表示 |
| --- | --- |
| STT重み | [Moonshine Community全文](Moonshine-Community-LICENSE.txt)・[NOTICEと改変内容](NOTICE-Moonshine.txt) |
| FLEURS | CC BY 4.0、作者・出典・音素化等の加工内容は同NOTICE。データ非同梱 |
| LM学習データ・教師 | [固定版・作者・利用目的](dialogue-data-NOTICE.md)。RealPersonaChat CC BY-SA由来の重み配布は保留 |
| sanoTTSコード | [MIT全文](sanoTTS-jp-MIT.txt)、固定submodule版を使用 |
| sanoTTS v4重み | [モデル条件](sanoTTS-jp-model.md)・[必須NOTICE](sanoTTS-jp-NOTICE.txt)・[Apache全文](sanoTTS-jp-Apache-2.0.txt) |
| 生成音声 | [音声利用条件](VOICE_TERMS.md)。用途制限と再配布時の引継ぎあり |
| CharDock DSP | Apache-2.0、[NOTICE](NOTICE-CharaDock.txt)と[本文](waveshare-examples-Apache-2.0.txt) |
| Waveshare BSP | Apache-2.0、[出典と改変](rlcd-demo-NOTICE.md)・同Apache本文 |
| 東雲16ドット | [原文](Shinonome-LICENSE.txt)・[作者一覧](Shinonome-AUTHORS.txt)・[変換履歴](Shinonome-NOTICE.md)。組込み・改変・再配布を許諾 |
| ESP-IDF / esp_codec_dev | [依存表示](DEPENDENCIES.md)。バイナリRelease時はリンク済み依存全体の確認も必要 |

## 公開するもの・しないもの

コード・再現手順・原文ライセンス・著者表示・自作テスト・公開可能な集計値を準備します。
Gitにはモデル重み、tokenizerの学習成果物、ダウンロードデータ、個人録音、flashバックアップ、
ビルド成果物、資格情報を入れません。生成フォントは固定原本からローカル再生成します。

**現行LM重みと統合ファームReleaseは保留**です。CC BY-SAが商用不可という意味ではなく、
当該学習重みへの条件の適用が未確定のためです。MITと表示して回避することはできません。
外部取得や利用者自身の学習にも、それぞれの利用条件は適用されます。

Moonshineの商用利用は登録が必要で、関連会社を含む年商100万米ドル超では別契約が必要です。
指定NOTICE・契約全文・目立つ `Powered by Moonshine AI` 表示を保持してください。
[AUP](https://moonshine.ai/use-policy)の年齢条件・無断録音禁止等にも従ってください。
別の基盤生成AIモデルの学習への流用には制限があり、当ラボはSTT出力をLM学習に使用しません。

TTS必須NOTICE・Apache本文は補完済み。読み上げ声の提供元表示は日英READMEにも掲載。
漢字フォントが入っていても、Open JTalkの大きな漢字辞書を実機へ組み込んだわけではありません。
将来漢字入力プロファイルを有効にする場合は辞書等を別途監査してください。

`python tools/publication_check.py` は混入物と必須表示の機械的チェックです。
法的な許諾確認・依存コードの完全な監査・公開承認を代替しません。
[残る確認事項](PUBLICATION_REVIEW.md)も参照してください。
