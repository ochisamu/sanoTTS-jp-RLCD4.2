# sanoTTS-jp v1.0.0 対応（2026-09-14）

上流はタグ `v1.0.0`、コミット
`f427b1e6bf743965c9b033d43fdf84b56f8f7543` に固定しています。
独立したRLCD4.2用リポジトリ内の変更であり、上流ソース自体は改変していません。

## 変更内容

- v4 int8モデル（654,032 bytes）を公式Releaseから取得し、サイズとSHA-256を検証。
  辞書は従来と同じ内容です。モデル・辞書・生成ファームはGitに含めません。
- 新しい `saan_audio` / `saan_pcm` APIにRLCD4.2のES8311出力を接続。
  発話開始時にプリロールをリセットし、容量を超える要求は拒否します。
- 新しいconsole poll APIにUSB連続入力とGPIO18 KEYを接続。
  USB待ち時間を制限し、USB未接続時にもKEYを処理します。
- 専用画面は既存のRLCDドライバが管理します。上流UIにはnull実装を使用します。
- duration 1.15倍、PCMゲイン1.0倍、PAの起動時OFFとミュート／音量読戻しを維持。
- v4用モデルライセンス、モデルカード、帰属表示とApache-2.0全文を更新。
  `dist/` の生成物にも同梱します。

## 更新手順

このリポジトリ内で実行します。ESP-IDF 5.5.4の環境を有効にしてください。

```bash
git pull --ff-only
git submodule update --init --recursive
python3 tools/demo.py fetch --kanji --accept-model-license
python3 tools/demo.py check
python3 -m unittest discover -s tests -v
python3 tools/demo.py build --profile kanji
```

`--accept-model-license` は更新されたライセンスを読んで同意した場合に指定します。
書き込みはREADMEの既存の復旧・ボード確認手順に従ってください。
**アプリだけではなくv4モデルも更新が必要です。** `tools/demo.py flash` が使う
ビルドのflash設定にはモデルと漢字辞書も含まれます。旧モデルを使ったまま
新アプリだけを書き込まないでください。USB文章入力の `speak.cmd` は従来どおりです。

## 検証結果と未確認事項

- ESP-IDF 5.5.4：probe、kana、kana-silent、kanji、kanji-silent の全5構成がビルド成功。
  silent構成の指定方法は `--profile kana --silent` / `--profile kanji --silent`。
- 漢字音声版のDIRAMリンク余裕：55,421 bytes（実行時の空きヒープとは異なります）。
- ホスト側自動テスト35件とソース契約チェック成功。
- 上流 `csrc/golden_test.c` をホスト上でコンパイルし、公式
  `saanotts-jp-v4-int8.bin` と `golden-v4-int8.bin` を比較。
  W8A32のPCM SNRは113.77 dB、durationは53/53一致、陽性対照も成功。
  これはホスト検証であり、ESP32のW8A8/PIE音声の実機検証ではありません。
- **この更新では実機へ書き込んでいません。** 音質・発話速度・連続入力・KEY・
  電池動作はv1対応版を実機へ書き込んだ後に確認が必要です。
  旧版のサンプル数・FNVや音量の聴感結果をv4の検証結果として流用しません。
