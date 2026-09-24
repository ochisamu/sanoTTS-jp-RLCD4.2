# Shinonome / 東雲 16-dot Gothic

Origin: Yasuyuki Furukawa (古川泰之), maintained by /efont/,
The Electronic Font Open Laboratory. Version 0.9.11.
Original site: http://openlab.ring.gr.jp/efont/shinonome/
Pinned mirror: https://github.com/code4fukui/shinonome-font/tree/053b21e0a11ef5799c1ea3cefc374763add80617

See `Shinonome-LICENSE.txt` and `Shinonome-AUTHORS.txt` (unmodified originals).
The authors declare public-domain-like permission/non-exercise of rights, explicitly
allowing modification, conversion, embedding and redistribution, without warranty.
Do not mislabel the fonts as this lab's original MIT code.

Modifications: `tools/prepare_font.py` reads the original `16/kanjic/font_src.bit`
and the ASCII subset of `16/latin1/font_src.bit`; maps JIS to Unicode using Python's
EUC-JP codec; emits sorted constant C tables. No upstream script is executed.
6,879 JIS glyphs plus 95 ASCII glyphs, 6,974 total. Unsupported characters render
as an outlined square. Source SHA256 checks and generated manifest live in the
converter and `.cache/font/manifest.json`. Font tables are not model weights.

東雲の原文ライセンス・作者一覧をそのまま保存。字形は変更せず、文字コードと格納形式のみ変換。
顔は本プロジェクト独自の幾何学描画で、Stack-chanの画像・コード・商標ロゴを取り込んでいません。
