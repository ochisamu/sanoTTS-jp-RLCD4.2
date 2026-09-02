# Architecture

このファームはWaveshare ESP32-S3-RLCD-4.2専用です。公式回路図、公式ESP-IDF
`Audio_Test`／`FactoryProgram`、ST7305とES8311のデータシートを基準にしています。
他ボードのBSPや自動ピン判定は持ちません。

```text
USB Serial/JTAG --> arbitrary kana ----------------------------------+
USB Serial/JTAG --> optional !kanji -> Open JTalk + mmap dictionary -+--> sanoTTS kana G2P
KEY GPIO18 --> debounced release --> fixed kana demo ----------------+
                                                                         |
                                                                         v
int8 model mmap -> W8A8 + ESP32-S3 PIE -> up to 262,144-sample PCM preroll
      |                                      |
      |                                      +-> sample/FNV/absmax/sumsq/xRT log
      v
float mono 22.05 kHz -> int16 -> I2S -> ES8311 -> NS4150B -> detachable speaker
                                           ^
                                           +-- PA_EN GPIO46, explicit playback only

PCM amplitude ---------------------------> ST7305 monochrome mouth animation

BAT_ADC GPIO4 -> calibrated ADC1_CH3 x3 -> ST7305 / advisory log only
```

RLCD4.2向けの再生調整は、モデルが予測した音素durationを1.15倍して声の高さを維持したまま
少し遅くします。codec音量は公式factory既定と同じ100が上限です。PCMのソフトウェア増幅は
実機スピーカーで歪みが出たため1.0倍に戻し、飽和制限とクリップ数の計測だけを残します。

ES7210とデュアルマイクは基板診断では検出しますが、最初のsanoTTS再生デモには使いません。
Wi-Fi、Bluetooth、microSD、RTC、温湿度センサーも起動時にサービスを開始しません。

## Boot and playback state machine

```text
reset
  -> GPIO46 PA_EN LOWを最初に確定
  -> Flash / PSRAM / partition sanity check
  -> shared I2C probe
  -> BAT_ADCを観測（失敗してもTTS/PA制御には使わない）
  -> ST7305 init + READY画面
  -> USBシリアルまたはKEY入力待機（無音）
  -> explicit request（USBの1行、または起動後の新しいKEY押下と解放）
       -> model inference and up to 262,144-sample preroll (then blocking stream)
       -> ES8311/I2S configure
       -> short zero preroll
       -> PA_EN HIGH + volume ramp
       -> PCM playback + mouth updates
       -> zero tail drain
       -> PA_EN LOW + codec/I2S close
       -> BAT_ADCを再観測
       -> USBシリアルまたはKEY入力待機（無音）
```

モデル、codec、LCDのいずれかが失敗した場合、PA_ENをLOWのまま保って待機または停止します。
BAT_ADCの失敗は表示／ログ上の診断にとどめ、TTSやPAを許可／禁止しません。起動とリセットは
無音です。起動時から押されていたKEYは解放後の新しい押下まで無視し、新しく押したKEYも
デバウンス済みの解放で初めて固定文1回の明示要求になります。

## Exact board map

### Display

| Signal | GPIO | Notes |
|---|---:|---|
| LCD_RS / DC | 5 | 上流sanoTTS汎用I2Sと衝突 |
| LCD_TE | 6 | 上流sanoTTS汎用I2Sと衝突 |
| LCD_SCL / SCLK | 11 | SPI mode 0 |
| LCD_SDA / MOSI | 12 | MISOなし |
| LCD_CS | 40 | active-low |
| LCD_RESET | 41 | active-low |

パネルはST7305、300x400 portrait／400x300 landscape、1 bit（2階調）、
バックライトなしです。公式ESP-IDFドライバーは10 MHz SPIを使い、全画面バッファは
`400 * 300 / 8 = 15,000` bytesです。ST7305のメモリ配置は通常の行単位1bppとは異なるため、
公式の2x4 pixel packingと初期化シーケンスを踏襲します。RGB565 APIは使いません。

### Touch status

タッチコントローラーは搭載されていません。現行公式回路図ではLCD FPC pin 16～19の
`TP_RESET`、`TP_INT`、`TP_SDA`、`TP_SCL` はすべて明示的にNCです。
公式インターフェース画像に残る GPIO42／7／13／14 のTPラベルとは矛盾しますが、
回路図と公式ファームを優先し、touchなしを正常状態とします。I2C doctorもタッチアドレスを
要求しません。

### Shared I2C and audio

| Function | Address / signal | GPIO |
|---|---|---:|
| I2C SDA | shared bus | 13 |
| I2C SCL | shared bus | 14 |
| ES8311 DAC | `0x18` | — |
| ES7210 ADC | `0x40` | — |
| PCF85063 RTC | `0x51` | INT=15 |
| SHTC3 | `0x70` | — |
| I2S MCLK | codec shared | 16 |
| I2S BCLK / SCLK | codec shared | 9 |
| I2S LRCK / WS | codec shared | 45 |
| I2S DOUT | MCU -> ES8311 | 8 |
| I2S DIN | ES7210 -> MCU | 10 |
| PA_EN | NS4150B enable | 46 |

GPIO46はcodecの音量設定とは別の物理アンプenableです。リセット直後からLOWとし、
最大262,144 sample（約11.9秒）のPSRAMプリロールとDMAのzero prefill後、再生区間だけ
HIGHにします。短い発話は全PCMを生成してから再生するため、推論が実時間より遅くても
音声出力は途切れません。
付属スピーカーは基板上のアンプ出力コネクターへ
接続する着脱式8 Ω / 2 W品で、スピーカー自体が基板へ実装されているわけではありません。

### Storage, buttons, USB, and power

| Function | GPIO / connection |
|---|---|
| microSD SDMMC 1-bit | CLK=38、CMD=21、D0=39 |
| SDCS option | GPIO17経路は回路図でNC抵抗、使用しない |
| BOOT | GPIO0 active-low、download modeにも使用 |
| KEY | GPIO18 active-low、デモ操作 |
| PWR | 専用power-latch IC。MCU GPIOではない |
| Battery ADC | GPIO4 / ADC1_CH3、200 kΩ / 100 kΩ分圧、換算はx3 |
| Native USB | D-=GPIO19、D+=GPIO20 |
| UART0 | TX=GPIO43、RX=GPIO44、拡張ヘッダーへ露出 |

2x8拡張ヘッダーP1は回路図上、次の配列です。

| Pin | Signal | Pin | Signal |
|---:|---|---:|---|
| 1 | 3V3 | 2 | VBUS |
| 3 | GND | 4 | GND |
| 5 | GPIO0 | 6 | USB D- / GPIO19 |
| 7 | GPIO1 | 8 | USB D+ / GPIO20 |
| 9 | GPIO2 | 10 | UART0 TX / GPIO43 |
| 11 | GPIO3 | 12 | UART0 RX / GPIO44 |
| 13 | GPIO17 | 14 | I2C SDA / GPIO13 |
| 15 | GPIO18 | 16 | I2C SCL / GPIO14 |

電源系はUSB VBUSと任意の標準18650、ETA6098充電／power-path、TPS63020 3.3 V
buck-boostで構成されます。初回bring-upでは18650とRTC電池を外し、USBのみを使います。
RTCバックアップ端子へ接続できるのはML1220等の充電式セルだけで、CR1220は不可です。

### Battery telemetry and local KEY demo

BAT_ADCは回路図上のGPIO4 / ADC1_CH3へ接続された200 kΩ / 100 kΩ分圧点です。実装は
Waveshare公式例と同じADC1_CH3、12 dB、12 bit、curve-fitting校正、x3換算を使い、初回の
捨て読みに続く16 sampleを平均します。TTSプロファイルではsetup時と各発話終了後、probeでは
起動時と30秒ごとに観測します。

画面は校正後の推定値を `BAT x.xxV` として表示し、ADC失敗は `BAT ADC ERR`、
3.00～4.20 Vの実装上の期待範囲外は、低い値も隠さず `BAT CHECK x.xxV` と表示します。
`BAT --` は値を渡せない内部状態用で、正常に完了したADC変換には使いません。
ログの推定%はWaveshare公式例の3.00 V=0%、4.12 V=100%を線形換算した参考値にすぎません。
BAT_ADCだけでは、18650の装着有無、充電中かどうか、USB／18650のどちらが給電源かを
区別できません。従って残量保護、software cutoff、PA_ENのinterlockには使用しません。

KEY GPIO18はactive-low入力です。20 ms間隔の3 sampleで状態をデバウンスし、起動後に一度
解放されたKEYの、新しい押下に続く解放だけを1要求として受理します。要求される入力は常に
固定中間表現「きょ][おわよ][いて][んきです°ね」（表示文「今日は良い天気ですね。」）です。
USBホストがない時もconsole出力は最大5 msの待機で打ち切り、KEY pollingを止めません。
編集中のUSB行がある場合はKEY要求を無視し、任意の文章はUSBの完了行だけから受け取ります。
audio profileでは同じ固定低音量経路で1回再生し、silent profileでは同じ要求を無音合成します。

USB接続中のBAT_ADC表示は実機確認済みです。電池単独の持続時間と本ファームのKEY固定文は
未検証であり、公式工場プログラムの稼働時間をこのsanoTTSファームの値として扱いません。

## Profiles

| Profile | CLI | Purpose |
|---|---|---|
| probe | `--profile probe` | PAを常時OFFにしてFlash、PSRAM、ST7305、I2C、KEY、BAT_ADCを診断 |
| kana silent | `--profile kana --silent` | USBかな／KEY固定文、W8A8+PIE、PCM指標。speaker pathはbuild時無効 |
| kana | `--profile kana` | kana silentと同じ入力／推論にES8311再生を追加 |
| kanji silent | `--profile kanji --silent` | USB漢字変換／KEY固定文と推論を無音検証 |
| kanji | `--profile kanji` | USB漢字入力／KEY固定文とES8311再生。最後に試す実験プロファイル |

全プロファイルは16 MB固定、no-OTAのパーティションテーブルを使います。モデルと漢字辞書は
64 KiB境界へ配置し、RAMへ全コピーせずFlashからmmapします。プロファイルごとに生成
`sdkconfig` とbuild directoryを分離し、別プロファイルの設定を再利用しません。
既存の `RLCD42_PROFILE:*` markerはCLIのprofile照合用に変更しません。BAT_ADCとlocal KEYは
それぞれ `RLCD42_CAP:battery-adc1-ch3-x3-v1`、`RLCD42_CAP:key-local-demo-v1` という独立した
capability markerを持ち、kana／kanjiやsilent／audioのprofile選択とは混同しません。

## Host-side trust boundary

`tools/demo.py` がファーム書き込み前の安全境界です。

1. `ports` で候補ポートだけを列挙する。
2. `doctor --confirm-board ESP32-S3-RLCD-4.2` でESP32-S3、16 MB、MAC、security stateを確認する。
3. `backup --confirm-board ESP32-S3-RLCD-4.2` でraw 16 MiBを2回読み、hash一致と再接続MACを確認する。
4. `flash --profile ...` は最初に受理した同一MACの`recovery-baseline`がなければ拒否し、
   build後にもそのmanifestと実ファイルを再検証する。
5. `demo` はFlash上のprofile markerを読み、silent/audioとkana/kanjiが指定と完全一致するまで
   文章を送らない。
6. `restore` は隣接JSONのschema、board、MAC、role、size、2-read記録、SHA-256を再検証する。

Secure BootとFlash Encryptionはこのプロジェクトから有効化しません。接続個体ですでに
有効なら、custom flashとraw restoreを拒否します。

## Primary references

- [Waveshare product documentation](https://docs.waveshare.com/ESP32-S3-RLCD-4.2)
- [Official schematic](https://files.waveshare.com/wiki/ESP32-S3-RLCD-4.2/ESP32-S3-RLCD-4.2-schematic.pdf)
- [Official repository](https://github.com/waveshareteam/ESP32-S3-RLCD-4.2)
- [Official ESP-IDF Audio Test](https://github.com/waveshareteam/ESP32-S3-RLCD-4.2/tree/main/02_Example/ESP-IDF/07_Audio_Test)
- [Official ESP-IDF FactoryProgram](https://github.com/waveshareteam/ESP32-S3-RLCD-4.2/tree/main/02_Example/ESP-IDF/10_FactoryProgram)
- [Pinned LCD/I2C pin definitions](https://github.com/waveshareteam/ESP32-S3-RLCD-4.2/blob/eb1f63427d735a22b9c30e22fa63ebddae1834d3/02_Example/ESP-IDF/10_FactoryProgram/main/user_config.h)
- [Pinned codec/I2S board definitions](https://github.com/waveshareteam/ESP32-S3-RLCD-4.2/blob/eb1f63427d735a22b9c30e22fa63ebddae1834d3/02_Example/ESP-IDF/10_FactoryProgram/components/ExternLib/codec_board/board_cfg.txt)
- [Pinned ST7305 implementation](https://github.com/waveshareteam/ESP32-S3-RLCD-4.2/blob/eb1f63427d735a22b9c30e22fa63ebddae1834d3/02_Example/ESP-IDF/10_FactoryProgram/components/port_bsp/display_bsp.cpp)
- [Pinned BAT_ADC implementation](https://github.com/waveshareteam/ESP32-S3-RLCD-4.2/blob/eb1f63427d735a22b9c30e22fa63ebddae1834d3/02_Example/ESP-IDF/10_FactoryProgram/components/port_bsp/adc_bsp.cpp)
- [ST7305 datasheet](https://files.waveshare.com/wiki/common/ST_7305_V0_2.pdf)
- [ES8311 datasheet](https://files.waveshare.com/wiki/common/ES8311.DS.pdf)
