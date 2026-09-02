# Safety and recovery

## Non-negotiable invariants

1. 対象はWaveshare `ESP32-S3-RLCD-4.2` / `ESP32-S3-RLCD-4.2-EN`だけです。
   `doctor`、`backup`、`flash`、`restore`は明示的な
   `--confirm-board ESP32-S3-RLCD-4.2` と、接続個体のESP32-S3／16 MiB／MAC確認を要求します。
2. 初回bring-upは18650、RTC電池、microSD、スピーカー、拡張配線を外し、データUSB-C
   だけで行います。
3. USBの抜き差し、電池の着脱、BOOT操作でRLCDを持ったり支点にしたりしません。
   基板側を平らな非導電面で支えます。
4. GPIO46（NS4150B PA_EN）はbootの最初にLOWへ設定し、最大262,144 sampleのPCM prerollと
   明示的な再生要求が揃うまでHIGHにしません。エラー時はLOWへ戻します。
5. bootは音声合成も再生もしません。TTS実行にはUSBシリアルの完了行、またはREADY後の
   新しいKEY押下とデバウンス済み解放が必要です。KEYは固定デモ文1回だけを要求し、
   起動時から押されていたKEYは解放後に改めて押すまで無視します。
6. LCDはST7305専用配線 GPIO5/6/11/12/40/41だけで扱います。タッチを初期化しません。
7. 書き込み前に0x000000～0xFFFFFFを2回読み、同一SHA-256の16 MiB raw factory
   backupと同一MACのmanifestがあることを必須にします。
8. このプロジェクトはeFuseを書かず、Secure BootやFlash Encryptionを有効化せず、
   一般利用者向けの`erase_flash`コマンドを提供しません。
9. Secure BootまたはFlash Encryptionがすでに有効な個体では、custom flashとraw
   restoreを拒否します。

## Physical handling

4.2インチRLCDは薄く、基板より大きい精密部品です。Waveshare公式も、USBケーブルの
接続や18650の着脱時に画面を力の支点にしないよう明記しています。

- USB-Cを挿す時はコネクター近くの基板を支える。
- 画面を押さえつけた状態でコネクターや電池をこじらない。
- 落下、衝撃、FPCの折り曲げ、金属面での通電を避ける。
- 画面が暗いことを故障と決めつけない。反射型でバックライトがなく、明るい環境ほど見やすい。
- 初回は電池を装着しない。後の電池試験でも極性を二重確認する。
- RTC端子にはML1220等の充電式セルだけを使う。CR1220等の一次電池は接続しない。

18650を後から装着した場合、公式FAQでは最初にUSB-C給電で保護回路をactivateする必要が
あるとされています。PWRは専用power-latchへのボタンで、MCUのプログラマブルGPIOでは
ありません。短押しでON、長押しでOFFです。

## Battery telemetry and standalone KEY safety

18650／KEY試験はUSB給電のprobe、silent TTS、低音量audioが合格した後だけ実施します。

- 標準の充電式18650だけを使い、電源OFF／USB切断中に極性を二重確認して装着する。
- 逆接警告の `WRN` LEDが点灯した場合や、発熱、膨張、異臭、液漏れがある場合は使用を
  中止して電源を外す。
- 装着後は公式FAQどおり最初にUSB-C給電で保護回路をactivateし、その後に単独給電を試す。
- BAT_ADCはGPIO4 / ADC1_CH3の200 kΩ / 100 kΩ分圧点の観測だけに使う。表示電圧や推定%から
  セル装着有無、充電中か、USB／18650のどちらが給電中か、安全な残量かを推測しない。
- `BAT --`、`BAT ADC ERR`、`BAT CHECK` をpower-off命令やPA_ENの許可条件にしない。この
  ファームには電池のsoftware cutoffを実装せず、基板の電源／保護回路を置き換えない。
- ただし初回実機Gate Eでは上の3表示を人間側の停止条件とする。3.00～4.20 Vの有効な
  `BAT x.xxV` を確認できるまでUSBを抜かず、電池単独発話へ進まない。
- READY後にKEYを新しく押して解放した時だけ、固定低音量の基準文を1回再生する。起動中から
  KEYを保持しても発話せず、長押しやbounceで連続再生しないことを実機gateで確認する。
- 公式工場プログラムの稼働時間をsanoTTSファームの電池持続時間として引用しない。USB接続中の
  BAT_ADC表示は実機確認済みだが、電池単独の持続時間と本ファームのKEY固定文は未検証である。

## Why generic sanoTTS firmware is not valid

上流sanoTTSの汎用ESP32-S3テンプレートは仮I2SとしてBCLK=GPIO5、WS=GPIO6、
DOUT=GPIO7を使います。このボードではGPIO5はST7305 DC、GPIO6はST7305 TEであり、
実際のcodec配線は次のとおりです。

```text
MCLK  GPIO16
BCLK  GPIO9
LRCK  GPIO45
DOUT  GPIO8   (MCU -> ES8311)
DIN   GPIO10  (ES7210 -> MCU)
PA_EN GPIO46
I2C   SDA13 / SCL14
```

汎用binでは音が出ないだけでなくLCD信号を誤駆動します。上流配布binをこのボードへ
書き込まず、このリポジトリの専用BSPだけを使います。

## Touch documentation discrepancy

製品名と製品仕様にtouchの記載はありません。現行公式回路図では、LCDコネクターの
`TP_RESET`、`TP_INT`、`TP_SDA`、`TP_SCL` はすべてNCで、touch controllerもありません。
一方、公式インターフェース画像には GPIO42／7／13／14 の古いTPラベルが残っています。

安全側の判断は次のとおりです。

- touchなしを正常とする。
- GPIO7、GPIO42をtouch controlとして駆動しない。
- shared I2C上にtouch addressがないことをdoctor失敗にしない。
- 将来別リビジョンでtouchが追加された場合も、型番だけで推測せず回路図、silkscreen、
  I2C probeを確認して別profileとして扱う。

## Audio safety

スピーカーは付属の着脱式8 Ω / 2 W品です。probeとsilent TTSでは外したままにします。
audio gateへ進む時だけ、USBを抜いた状態でコネクターへ接続します。

- GPIO46を内部pull任せにせず、アプリの最初に明示LOWにする。
- ES8311 `0x18`、I2S、sample rateを確認してからPAを有効にする。
- 最大262,144 sampleを先行生成し、zero preroll、volume rampの順で開始する。
- 末尾に十分なzero framesを送信してDMAをdrainしてからPAをLOWへ戻す。
- codec／I2S／model errorと通常の発話終了ではPAをLOWへ戻す。DMAはzero-prefillと
  auto-clearを使い、生成遅延時に未初期化データを再生しない。
- 最初の有音試験は1回、低音量。異音、click/pop、音割れ、発熱があれば即座にUSBを抜く。
- ES7210とマイクは初回再生には不要。output-onlyが合格するまで同時録音やAECを有効にしない。

## Backup acceptance

`tools/demo.py backup` は次をすべて満たすイメージだけを採用します。

- chip = ESP32-S3
- board confirmation = `ESP32-S3-RLCD-4.2`
- detected Flash size = 16 MiB
- normalized security stateを記録（custom writeは両項目が明示的disabledの時だけ）
- address 0x000000から16 MiBを2回read
- 2 readのsizeとSHA-256が一致
- 読取前後で同じMAC
- final imageの実SHA-256とJSON manifestが一致
- 同じMACで最初に受理したイメージを`recovery-baseline`とし、後続は`snapshot`にする

`flash`が自動選択するのは最初の`recovery-baseline`だけです。custom firmwareを書いた後の
snapshotが、より新しいという理由で工場復旧イメージに昇格することはありません。

raw FlashにはWi-Fi資格情報、factory NVS、端末固有情報が入っている可能性があります。
CLIはリポジトリ外のユーザーデータディレクトリへ保存します。public cloudやissueへ
添付せず、復旧用に暗号化された私有の別ストレージへ1コピー置きます。

## Flash order

安全順序を飛ばしません。

```text
doctor
  -> raw recovery baseline (two identical reads)
  -> probe (PA always off; no model)
  -> kana --silent (model + metrics; speaker path absent)
  -> kana audio over USB (low-volume single utterance)
  -> repeated USB-powered audio
  -> 18650 + KEY fixed low-volume single utterance
  -> optional kanji --silent
  -> optional kanji audio
```

新しいprofileへ進む前に、前段階のログと [bringup.md](bringup.md) のgateを記録します。

## Restore paths

### Exact per-device recovery

優先経路は同じ個体のraw 16 MiB backupです。

```bash
python3 tools/demo.py restore "/private/path/rlcd42-backup-TIMESTAMP-MAC.bin" --port PORT --confirm-board ESP32-S3-RLCD-4.2 --dry-run
python3 tools/demo.py restore "/private/path/rlcd42-backup-TIMESTAMP-MAC.bin" --port PORT --confirm-board ESP32-S3-RLCD-4.2 --yes
```

restoreは隣接JSON manifest、board id、MAC、size、2-read記録、manifest SHA-256、
実ファイルSHA-256を確認し、書き込み直前にもMACを再確認します。0x000000から全領域を
writeし、完了後にfull `verify_flash`を行います。別MACのbackupは使えません。

### Official factory fallback

Waveshare公式リポジトリには
[`03_Firmware/01_Factory_V1.bin`](https://github.com/waveshareteam/ESP32-S3-RLCD-4.2/blob/main/03_Firmware/01_Factory_V1.bin)
と
[`10_FactoryProgram`](https://github.com/waveshareteam/ESP32-S3-RLCD-4.2/tree/main/02_Example/ESP-IDF/10_FactoryProgram)
があります。公式binは約4.5 MBのfactory demo用merged imageで、このCLIが要求する
16 MiB raw backupではないため`restore`には渡せません。個体固有NVSまで完全に戻す保証も
ないため、自分のraw backupを優先し、公式binはWaveshare公式手順で扱います。

通常接続できない場合は、BOOTを押したままUSBの再接続またはpower cycleを行い、
download modeへ入れます。この操作でも画面を押さえず、基板側だけを支えます。

## Official safety sources

- [Product documentation and handling cautions](https://docs.waveshare.com/ESP32-S3-RLCD-4.2)
- [Official FAQ: power, battery, RLCD, download mode](https://docs.waveshare.com/ESP32-S3-RLCD-4.2/FAQ)
- [Official schematic](https://files.waveshare.com/wiki/ESP32-S3-RLCD-4.2/ESP32-S3-RLCD-4.2-schematic.pdf)
- [Official resources and source repository](https://docs.waveshare.com/ESP32-S3-RLCD-4.2/Resources-And-Documents)
