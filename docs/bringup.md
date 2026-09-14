# ESP32-S3-RLCD-4.2 physical bring-up record

このチェックシートは各自の実機検証で記入する空のテンプレートです。2026-09-02に実機1台で
表示、I2C、USB文章入力、端末内変換、音声、電池電圧表示まで確認しましたが、個体固有のMAC、
ポート、factory backup、ログはプライバシー保護のため公開リポジトリへ記録しません。
コンパイルや結合binの生成だけで「hardware verified」にしません。

必ず **raw backup → probe → silent TTS → USB audio → 18650／KEY** の順を守ります。
初回は18650、RTC電池、microSDを接続せず、データUSB-Cだけで給電します。USBケーブルを
抜き差しする時、RLCDパネルを押さえたり、パネルを支点に基板を曲げたりしません。

## Device record

- Date / operator:
- SKU: 33298 / 33507 (-EN)
- PCB silkscreen / revision marking（あれば）:
- MAC:
- USB port:
- ESP-IDF / esptool version:
- Factory firmware screen/version:
- Factory raw backup path:
- Factory raw backup SHA-256:
- Backup manifest copied to private second storage: yes / no

## Gate A — USB-only inspection and raw backup

- [ ] 電源を切り、18650とRTC電池を接続していない
- [ ] スピーカー、microSD、拡張ヘッダー配線を外した
- [ ] 基板側を平らな非導電面で支え、画面を持っていない
- [ ] FPC、スピーカー端子、USB-C、電池極性に目視異常がない
- [ ] データ通信対応USB-Cだけを接続した
- [ ] USB-C接続後に `python3 tools/demo.py ports` で対象ポートを特定した
- [ ] `doctor --confirm-board ESP32-S3-RLCD-4.2` がESP32-S3を確認した
- [ ] Flash size = 16 MiB、PSRAM想定 = 8 MiBを確認した
- [ ] Secure Boot / Flash Encryptionは無効だった
- [ ] MACを接続前後で再確認した
- [ ] 0x000000～0xFFFFFFのraw readを2回実施した
- [ ] 2つのraw imageがbyte-identical / SHA-256一致だった
- [ ] final imageとJSON manifestを私有の別ストレージへコピーした

実行コマンド：

```bash
python3 tools/demo.py doctor --port PORT --confirm-board ESP32-S3-RLCD-4.2
python3 tools/demo.py backup --port PORT --confirm-board ESP32-S3-RLCD-4.2
```

診断メモ：

```text
chip:
flash size:
MAC:
security state:
read #1 SHA-256:
read #2 SHA-256:
```

## Gate B — board probe, amplifier locked off

この段階ではスピーカーを接続しません。probeはモデルを読み込まず、GPIO46をLOWに保ちます。

- [ ] `flash --profile probe` が同一MACの有効なfactory backupを要求した
- [ ] reset直後からPA_EN GPIO46 = LOWとログで確認した
- [ ] QIO 16 MB Flashと8 MB Octal PSRAMの初期化に成功した
- [ ] ST7305をSPI mode 0 / 10 MHzで初期化した
- [ ] LCD DC=5、TE=6、SCLK=11、MOSI=12、CS=40、RST=41だった
- [ ] 400x300の白黒テストパターンが正しい向き・極性で表示された
- [ ] 反射型LCDなので照明を当てると見やすくなり、バックライトがないことを正常と判断した
- [ ] KEY GPIO18の押下／解放を認識した
- [ ] BOOT GPIO0を通常操作に誤使用していない
- [ ] I2C SDA=13 / SCL=14で下記アドレスを検出した
- [ ] ES8311 `0x18`
- [ ] ES7210 `0x40`
- [ ] PCF85063 `0x51`
- [ ] SHTC3 `0x70`
- [ ] タッチデバイスを検出しなくてもprobeが成功した
- [ ] GPIO7 / GPIO42をtouch用に初期化していない
- [ ] BAT_ADC GPIO4がADC1_CH3へ対応し、12 dB／12 bit／curve-fitting校正／x3換算だった
- [ ] BAT_ADCのraw値と校正後mV、または明示的なunavailable／ADC errorをログに記録した
- [ ] LCDの `BAT x.xxV`、`BAT --`、`BAT ADC ERR`、`BAT CHECK x.xxV` のいずれかを記録した
- [ ] USB給電中のBAT_ADC値を、セル装着有無、充電中、または給電源の証拠として扱わなかった
- [ ] BAT_ADC失敗時もGPIO46がLOWだった
- [ ] 5回のreset／power cycleで意図しない音、過熱、再起動loopがなかった

実行コマンド：

```bash
python3 tools/demo.py flash --port PORT --profile probe --confirm-board ESP32-S3-RLCD-4.2
python3 tools/demo.py monitor --port PORT --profile probe
```

Probe log：

```text
firmware commit:
Flash / PSRAM:
LCD orientation / polarity:
I2C scan:
KEY:
BAT_ADC raw / calibrated mV / display:
GPIO46 initial/readback:
minimum internal DRAM:
```

## Gate C — silent sanoTTS inference

この段階もスピーカーを外したままです。`--silent` ではcodec／PA経路がbuild時に無効で
あることを、ログと生成設定の両方で確認します。

- [ ] `flash --profile kana --silent` を使用した
- [ ] boot中も基準文実行中もGPIO46 = LOWだった
- [ ] model partitionのsize / SHA-256を確認した
- [ ] model mmapとW8A8 + ESP32-S3 PIEを確認した
- [ ] 起動時に自動合成しなかった
- [ ] USBから明示した基準文だけを合成した
- [ ] 基準文が再起動／watchdogなしで完了した
- [ ] v4モデル・duration 1.15倍でのPCM samples／FNV／クリップ数を記録した（旧v3の27136を流用しない）
- [ ] RLCD4.2調整速度1.15倍で増えたPCM samplesを記録した
- [ ] PCM FNV / absmax / sumsqを記録した
- [ ] ST7305の口表示がPCM振幅に合わせて更新された
- [ ] 5回連続の無音合成を完了した
- [ ] steady xRT <= 1.0、または制約を明記した

実行コマンド：

```bash
python3 tools/demo.py flash --port PORT --profile kana --silent --confirm-board ESP32-S3-RLCD-4.2
python3 tools/demo.py demo --port PORT --profile kana --silent --confirm-board ESP32-S3-RLCD-4.2
```

Silent metrics：

```text
first pull latency:
steady xRT:
underruns:
PCM samples:
PCM FNV:
absmax:
sumsq:
clipping:
minimum internal DRAM:
task stack high-water:
```

## Gate D — controlled audio output

Gate A～Cがすべて合格した後だけ実施します。USBを抜いてから付属8 Ω / 2 Wスピーカーを
コネクターへ差し込み、再びUSBだけで給電します。付属スピーカーでは公式factoryの既定値と
同じ音量100で1回再生します。基準TTSのPCMピークは約-10.5 dBFS、クリップ0で、公式factory
の音楽経路は音量90です。

- [ ] 電源OFF中にスピーカーを正しい端子へ確実に接続した
- [ ] GPIO46は明示入力までLOWだった
- [ ] I2S MCLK=16、BCLK=9、LRCK=45、DOUT=8だった
- [ ] sanoTTS出力sample rate = 22,050 Hzで、pitch shiftがなかった
- [ ] 最大262,144-sampleのPSRAM prerollとDMA zero prefill後にだけPAを開始した
- [ ] PA_EN HIGHの前にzero prerollを送った
- [ ] 起動、codec open、PA enable、codec closeでclick/popがなかった
- [ ] volume rampが低い安全値から始まった
- [ ] 基準文が明瞭で、音割れや異常発熱がなかった
- [ ] 末尾zero drain後、PA_ENがLOWへ戻った
- [ ] 口表示が再生音量におおむね同期した
- [ ] 5回連続再生で再起動、underrun、memory減少がなかった
- [ ] USBシリアルから明示送信した1行につき1発話だけを開始した

実行コマンド：

```bash
python3 tools/demo.py flash --port PORT --profile kana --confirm-board ESP32-S3-RLCD-4.2 --yes-speaker-connected
python3 tools/demo.py demo --port PORT --profile kana --confirm-board ESP32-S3-RLCD-4.2 --yes-speaker-connected
```

Audio record：

```text
configured volume:
measured / perceived pitch:
click/pop:
underruns:
PA_EN high/low timing:
codec temperature note:
five-run result:
```

## Gate E — 18650 / KEY standalone demo

Gate A～Dがすべて合格した後だけ実施します。USB接続中の18650電圧表示は実機確認済みですが、
USBを外した電池単独給電と本ファームのKEY固定文再生は未検証です。
書き込み済みのkana audioプロファイルと付属8 Ω / 2 Wスピーカーを使い、USBを外した状態で
固定デモ文だけを試します。任意文入力、再flash、serial log採取はUSBなしでは行いません。

- [ ] 電源を切ってUSB-Cを抜き、基板側を平らな非導電面で支えた
- [ ] 標準の充電式18650であることと極性を二重確認して装着した
- [ ] `WRN` LEDが消灯し、発熱、膨張、異臭、液漏れがなかった
- [ ] 公式FAQどおり最初にUSB-Cを接続して電池保護回路をactivateした
- [ ] USB接続中に `TTS READY` と3.00～4.20 Vの有効な `BAT x.xxV`、BAT_ADCの
      raw／mV／推定%を記録した
- [ ] `BAT ADC ERR`、`BAT --`、`BAT CHECK x.xxV` の場合は不合格として先へ進まず、
      電源を切って電池、極性、基板を再確認した
- [ ] BAT_ADCからセル装着有無、充電中、USB／18650の給電源、安全な残量を判定しなかった
- [ ] USB-Cを抜いた後も電源が維持され、画面が `TTS READY` を示した
- [ ] PWR短押しでON、長押しでOFFとなり、PWRをMCU GPIOとして扱っていなかった
- [ ] KEYを押したまま起動しても発話せず、最初の解放だけでも発話しなかった
- [ ] READY後にKEYを新しく押して解放すると、固定文「今日は良い天気ですね。」を
      固定低音量でちょうど1回発話した
- [ ] KEYの保持、bounce、1回の押下／解放で二重発話せず、再度の新しい押下／解放は1回発話した
- [ ] USBホストがなくてもKEY入力待機が止まらなかった
- [ ] 発話要求前とzero tail後にPA_EN GPIO46がLOWだった
- [ ] click/pop、音割れ、underrun、再起動、異常発熱がなかった
- [ ] 発話終了後にBAT表示が更新され、3.00～4.20 Vの `BAT x.xxV` のままだった
- [ ] 発話後に `BAT ADC ERR`、`BAT --`、`BAT CHECK x.xxV` となった場合は追加発話をせず、
      PWR長押しで停止した（該当しなければN/A）
- [ ] BAT値をファーム内のPA_EN許可／禁止には使わなかった
- [ ] 公式工場プログラムの値を流用せず、このファームの電池持続時間を未測定として記録した

Battery / KEY record：

```text
18650 identification / polarity:
USB activation result:
BAT_ADC raw / mV / estimated percent before unplug:
BAT display after unplug / after utterance:
boot-held KEY result:
fresh press/release utterance count:
configured volume / audio result:
PA_EN / reset / temperature notes:
elapsed battery run (observation only):
```

## Gate F — optional kanji profile

kana silentとkana audioが合格するまで開始しません。

- [ ] `--profile kanji --silent` で辞書size / SHA-256、mmap、変換を無音確認した
- [ ] 漢字基準文の読みとPCM指標を記録した
- [ ] その後だけ `--profile kanji` の低音量再生を1回実施した
- [ ] partition overflowと内部DRAM safety gateを再確認した

## Gate G — raw restore drill

実施前に、使うraw imageとJSON manifestの複製をもう1つ残します。restore中はUSBを抜かず、
画面や基板を動かしません。

- [ ] restoreが隣接JSON manifestなしでは拒否された
- [ ] board id = `ESP32-S3-RLCD-4.2` を確認した
- [ ] manifestのMACが接続個体と一致した
- [ ] image size = 16 MiBだった
- [ ] manifestに2回読取一致の記録があった
- [ ] manifest SHA-256と実ファイルSHA-256が一致した
- [ ] 全Flash writeと`verify_flash`が成功した
- [ ] 工場ファームが起動した
- [ ] 工場画面、KEY、音声テスト、センサーを確認した
- [ ] 復旧後のMACが変わっていない

```bash
python3 tools/demo.py restore "/private/path/rlcd42-backup-TIMESTAMP-MAC.bin" --port PORT --confirm-board ESP32-S3-RLCD-4.2 --dry-run
python3 tools/demo.py restore "/private/path/rlcd42-backup-TIMESTAMP-MAC.bin" --port PORT --confirm-board ESP32-S3-RLCD-4.2 --yes
```

Restore record：

```text
image SHA-256:
manifest MAC:
connected MAC:
write result:
verify result:
factory firmware result:
```

## Hardware verification decision

- [ ] Gates A～Eを完了した
- [ ] 重大／高リスクの未解決事項がない
- [ ] 実測結果とファームcommitをこの文書へ記録した
- [ ] `hardware verified` として扱ってよい

Decision / unresolved limitations：

```text

```
