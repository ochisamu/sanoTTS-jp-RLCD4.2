"""Original, deliberately small offline fact cards. MIT; no scraped text.

Fields: id, train aliases (|), held-out development wording, display answer.
Math/definitions are stable; device facts describe this repository, not products
in general. No current news, personal data or medical/legal/financial advice.
"""
ROWS = '''
add_one\t一足す一は|一と一を足して|一足す一を計算して\t一に一を足すといくつ\t二だよ。
add_two\t二足す三は|二と三を足して|二足す三を計算して\t二に三を足すといくつ\t五だよ。
multiply\t三掛ける四は|三と四を掛けて|三掛ける四を計算して\t三掛ける四の答えは\t十二だよ。
week\t一週間は何日|一週間の日数は|一週間は何日間\t一週間って何日あるの\t一週間は七日だよ。
hour\t一時間は何分|一時間を分にすると|一時間は何分間\t一時間って何分あるの\t一時間は六十分だよ。
minute\t一分は何秒|一分間は何秒|一分を秒にすると\t一分って何秒あるの\t一分は六十秒だよ。
meter\t一メートルは何センチ|一メートルをセンチにすると|一メートルは何センチメートル\t一メートルって何センチなの\t一メートルは百センチだよ。
kilo\t一キログラムは何グラム|一キロは何グラム|一キログラムをグラムにすると\t一キログラムって何グラムなの\t一キログラムは千グラムだよ。
triangle\t三角形の角はいくつ|三角形には角が何個ある|三角形は何個の角がある\t三角形って角がいくつあるの\t三角形の角は三つだよ。
square\t四角形の角はいくつ|四角形には角が何個ある|四角形は何個の角がある\t四角形って角がいくつあるの\t四角形の角は四つだよ。
echo_button\tおうむ返しはどうするの|おうむ返しのボタンは|復唱するにはどうする\tどうやっておうむ返しするの\tキーボタンを押して離してね。
reply_button\t会話のボタンは|回答させるにはどうする|返事するボタンはどれ\tどうすれば回答してくれるの\tブートボタンを押して離してね。
offline\tネットなしで使える|オフラインで動くの|通信しなくても使える\tネットにつながなくても話せるの\t認識も返答も音声も端末で動くよ。
recording\tいつ録音するの|ずっと録音しているの|常に聞いているの\t話していない時も録音するの\tボタンを押した後だけ録音するよ。
memory\t前の会話は覚えてる|会話を記憶できる|会話履歴はあるの\t前に話した内容を覚えているの\t前の会話を覚える機能はないよ。
knowledge\t何でも知っているの|知らないことはある|知識は無限なの\tどんな質問にも答えられるの\t知識は少なくて間違うこともあるよ。
'''
CARDS=[dict(zip(('id','questions','dev','answer'),line.split('\t'))) for line in ROWS.strip().splitlines()]
