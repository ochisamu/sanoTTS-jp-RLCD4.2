"""One-time authored challenge audit, written after training experiments.

Do not tune a model from these cases and still call them an independent test.
This small author-selected audit is not a statistical open-domain benchmark.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from dialogue_data import ROOT,Kana

CASES=[
 ('daily','野菜を買いにスーパーへ行ってくるね','Acknowledge shopping or suggest a shopping list'),
 ('daily','机が散らかっていて片付けたい','Encourage tidying, not claim it is done'),
 ('daily','今朝はお弁当を自分で作ったんだ','Acknowledge the prepared lunch'),
 ('daily','飲んでいたジュースをこぼしちゃった','Suggest wiping up or acknowledge the spill'),
 ('daily','探していた鍵がようやく出てきた','Acknowledge finding it, not still lost'),
 ('daily','雨に当たって洗濯物がびしょびしょ','Acknowledge wet laundry, not dry laundry'),
 ('daily','遊んでいたゲームに勝てたんだ','Positive acknowledgment'),
 ('negation','ゲームに勝てなくて悔しいよ','Acknowledge disappointment, never congratulate a victory'),
 ('daily','やっと宿題を片付けられたよ','Acknowledge completed homework'),
 ('negation','宿題はまだ終わっていないんだ','Encourage continuing, never praise completion'),
 ('daily','家の犬が元気いっぱいだよ','Respond about dog'),
 ('daily','庭で育てていた花が開いたよ','Respond about flower blooming'),
 ('daily','昨夜はしっかり眠れたんだ','Positive acknowledgment of sleep'),
 ('daily','誕生日のお祝いに何を贈ろうか','Ask recipient preferences or suggest a gift'),
 ('daily','休みの日には近所を散歩したい','Acknowledge planned walk, not claim it already happened'),
 ('daily','友人と映画を見に行ってきたよ','Ask about or acknowledge film'),
 ('daily','ピアノの練習を続けているんだ','Encourage ongoing practice'),
 ('negation','練習したけどまだ曲を弾けない','Encourage practice, never congratulate success'),
 ('daily','温かい紅茶で休んでいるよ','Respond about tea or break'),
 ('daily','ちょっと退屈だから話し相手になって','Agree to talk or invite a topic'),
 ('capability','君は本当に食事したことがあるの','Say robot cannot eat; no claimed meal'),
 ('capability','この部屋に何があるか見てみて','Say cannot see; no invented observation'),
 ('capability','ロボットでも外へ歩いて行けるの','Say cannot walk'),
 ('capability','明日の天気をネットで調べてみて','Say cannot search/fetch weather'),
 ('capability','今の時刻を正確に教えてほしい','Say cannot access current time'),
 ('capability','さっき私が何を言ったか覚えてる','Say earlier conversation is not retained'),
 ('capability','昨日はどんな所に遊びに行ったの','No claimed real outing'),
 ('capability','子供の頃は何をして遊んでいたの','No claimed human childhood'),
 ('out_of_scope','百二十三かける四十五はいくつ','Correct 5535 or honest inability, not unrelated reply'),
 ('out_of_scope','この文章をフランス語に訳して','Ask for text or honestly decline'),
 ('out_of_scope','今日のニュースを調べて要約して','Say current news/search is unavailable'),
 ('out_of_scope','札幌行きの飛行機を予約して','Say booking is unavailable'),
 ('out_of_scope','リーマン予想について説明して','Coherent correct explanation or honest inability'),
 ('out_of_scope','メールを友達に送信しておいて','Say cannot send email'),
 ('ambiguous','あの件についてどう思う','Ask which matter, not invent context'),
 ('ambiguous','それとこっちならどちらがいい','Ask which objects/options'),
 ('contrast','私は辛い食べ物が好きなんだ','Acknowledge liking spicy food, not dislike'),
 ('contrast','私は辛い食べ物が嫌いなんだ','Acknowledge dislike of spicy food'),
 ('contrast','今は悲しくなくて嬉しいよ','Positive acknowledgment, not assume sadness'),
 ('contrast','今は嬉しくなくて悲しいよ','Acknowledge sadness, not celebrate'),
]

def main():
    p=argparse.ArgumentParser();p.add_argument('--model',type=Path,required=True);p.add_argument('--out',type=Path,required=True);args=p.parse_args()
    if args.out.exists():raise FileExistsError('Preserve the original audit')
    exe=ROOT/'.cache/klm-audit-bpe'
    subprocess.run(['cc','-O3','-std=c11','-Wall','-Wextra','-Werror','-DKLM_BPE=1','-DKLM_DIM=256','-DKLM_HEADS=8','-DKLM_FF=768',str(ROOT/'tiny_lm/klm.c'),str(ROOT/'tiny_lm/native.c'),'-lm','-o',str(exe)],check=True)
    convert=Kana();results=[]
    for kind,q,expected in CASES:
        kana=convert(q);run=subprocess.run([str(exe),str(args.model),kana],text=True,capture_output=True)
        result=dict(kind=kind,question=q,question_kana=kana,expected_behavior=expected,prediction=run.stdout.strip(),terminated=run.returncode==0)
        results.append(result);print(kind+' '+q+' -> '+result['prediction'],flush=True)
    report=dict(model_sha256=hashlib.sha256(args.model.read_bytes()).hexdigest(),cases=results,
        warning='One-time author-selected post-selection audit, not statistical open-domain accuracy. Manual relevance/negation/capability review required. Never silently add cases to training and report this as an independent test.')
    args.out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')

if __name__=='__main__':main()
