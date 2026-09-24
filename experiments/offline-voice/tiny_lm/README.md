# Experimental Japanese reply LM / 日本語短文生成LM

[日本語の全体説明](../README.md) · [English overview](../README.en.md)

Current device: BPE W8A8 causal Transformer, four layers, width 256, eight heads,
FF768, context 96 tokens, vocabulary 1,024, 2,910,464 parameters / 3,074,496 bytes.
Generation runs on ESP32-S3, not on a PC. A separate local knowledge lookup path
now answers 16 known facts; unmatched questions use this neural generator.
See [the upgrade report](../docs/REPLY_UPGRADE.en.md) for source logs and limits.
Answer memorization is strong; it is not a general Japanese assistant.

現行はBPEモデルです。KEYは復唱、BOOTは認識→回答生成→読み上げ。
画面に認識したかな・生成した返答を東雲フォントで表示します。
ステータスは英語。長文は待機中にページを切り替えます。
対話履歴は持たず、否定や未知の質問への誤答が残る実験版です。

## Use / 操作

```sh
python -X utf8 tiny_lm/console.py --port YOUR_PORT --say
```

Windows: `console.cmd`. Requires pyserial. Up to 80 kana input characters;
`/quit` exits. Example: `かんたんなりょおりおおしえて`.
`ASK` generates text; `ASKSAY` also speaks; `CHAT` records and replies;
`LISTEN` records and repeats. Neither path sends data to a network.
Output is limited to 40 BPE tokens and a 256-byte buffer, not 40 characters.
Overlong/unrecognized input is rejected instead of silently truncating the question.

## Provenance and reproducibility / 学習元と再現

- [日本語の学習元一覧](../docs/TRAINING.md) / [English provenance](../docs/TRAINING.en.md)
- [日本語のビルド手順](../docs/REPRODUCE.md) / [English build guide](../docs/REPRODUCE.en.md)
- [Training experiment commands and quality limitations](DIALOGUE_EXPERIMENTS.md)
- [Device measurements and rollback](BPE_DEVICE.md)
- [Legacy 26-family character-model history](LEGACY_CHAR_MODEL.md)

LM timing was approximately 1.0–1.9 seconds over 32 test queries, excluding STT/TTS.
32/32 native/device parity is not answer accuracy. Wording-dev exact match was
85/137 within known semantic families; model selection used that dev set.
**Weights/tokenizer distribution is on hold**, because the current lineage includes
RealPersonaChat-derived stages. See [licenses](../licenses/README.en.md).
重み・学習データ・個人録音をGitへ追加しないでください。
