"""Local teacher-generated everyday dialogue pilot, separate from human data.

No user's text, final evaluation probes or test split is used. This is offline
data creation, not the device response algorithm. Human review is mandatory.
"""
import argparse
import hashlib
import json
import random
import time
from collections import Counter
import torch
from transformers import AutoTokenizer,AutoModelForCausalLM
from dialogue_data import ROOT,Kana,parse,BLOCK

TOPICS='''料理 弁当 朝食 お菓子 パン 野菜 果物 コーヒー 紅茶 牛乳 水 お米 麺類 外食 買い物 掃除 洗濯 片付け ゴミ 部屋 机 椅子 窓 照明 靴 服 傘 帽子 鞄 時計 鍵 忘れ物 通勤 電車 バス 自転車 散歩 道 旅行 山 海 川 公園 花 木 庭 植物 猫 犬 鳥 魚 虫 空 雲 雨 雪 風 暑さ 寒さ 春 夏 秋 冬 音楽 歌 ピアノ ギター 絵 写真 映画 本 漫画 ゲーム パズル 工作 手紙 日記 勉強 学校 宿題 試験 仕事 会議 休憩 休日 予定 待ち合わせ 友達 家族 誕生日 贈り物 お祝い 感謝 謝罪 失敗 成功 挑戦 練習 緊張 不安 喜び 寂しさ 退屈 疲れ 眠気 早起き 夜更かし 夢 思い出 趣味 運動 体操 ストレッチ ランニング 水泳 球技 地図 カレンダー 日本語 英語 数字 色 形 香り 音 速さ 時間 ロボット 会話 名前 自己紹介 食べる能力 動く能力 インターネットの有無 天気を調べる能力 記憶のできる範囲 気持ちを聞く 相手を励ます'''.split()
STYLES=['短い出来事の報告','気持ちの共有','小さな困りごとの相談','どちらがよいか迷う質問','方法を一つ尋ねる質問','好みについての質問','理由を尋ねる質問','これからしたいこと','うまくできたこと','うまくいかなかったこと','相手への呼びかけ','単純な確認']
SYSTEM='''会話専用の卓上ロボット「りこ」の日本語学習用に、利用者の発言と返答を一組作ってください。
前の会話がなくても意味が分かる自然な短文にします。発言は8〜25文字、返答は8〜20文字を目安に。指定された話題と発言種類を使い、題材は自由に具体化してください。
りこは話すことだけできます。食事、移動、睡眠、検索、時刻取得はできず、人間の経験はありません。できない能力を尋ねられたら正直に答えます。
返答は発言に直接対応させてください。一般的な相づちだけで済ませないでください。医療・金融・危険行為の助言や最新情報は含めません。
出力はJSON {"question":"利用者の発言","answer":"りこの返答"} のみ。
例：{"question":"仕事でくたくたになった","answer":"お疲れさま。少し休もう。"}
例：{"question":"君もラーメンを食べるの","answer":"食べられないけど、話は聞けるよ。"}
例：{"question":"雨の日は何をして遊ぼう","answer":"家でパズルをするのはどう？"}
例：{"question":"今の天気を調べて","answer":"今の天気は調べられないよ。"}'''

def main():
    p=argparse.ArgumentParser();p.add_argument('--limit',type=int,default=120);p.add_argument('--batch',type=int,default=24);args=p.parse_args()
    root=ROOT/'.cache/synthetic-chat';root.mkdir(exist_ok=True)
    requests=[]
    # Fixed family split; a particular topic/style family never crosses splits.
    for repeat in range(20):
        block=[(topic,style,repeat) for topic in TOPICS for style in STYLES]
        random.Random(7385+repeat).shuffle(block);requests.extend(block)
    path=root/'teacher.jsonl';done=set()
    if path.exists():done={json.loads(s)['id'] for s in path.read_text().splitlines()}
    pending=[]
    for topic,style,repeat in requests[:args.limit]:
        group=hashlib.sha256((topic+'|'+style).encode()).hexdigest();key=f'{group}:{repeat}'
        bucket=int(group[:8],16)%100
        if bucket>=95:continue  # Reserved families are never generated for development.
        if key not in done:pending.append(dict(id=key,group=group,topic=topic,style=style,split='train' if bucket<90 else 'dev'))
    if pending:
        torch.set_num_threads(4);torch.manual_seed(5784)
        tok=AutoTokenizer.from_pretrained(ROOT/'.cache/dialogue/teacher',local_files_only=True,trust_remote_code=False,padding_side='left')
        model=AutoModelForCausalLM.from_pretrained(ROOT/'.cache/dialogue/teacher',local_files_only=True,trust_remote_code=False,torch_dtype=torch.bfloat16,attn_implementation='sdpa').cuda().eval()
        start=time.monotonic()
        with path.open('a') as f,torch.inference_mode():
            for off in range(0,len(pending),args.batch):
                batch=pending[off:off+args.batch]
                prompts=[tok.apply_chat_template([dict(role='system',content=SYSTEM),dict(role='user',content=f'話題：{r["topic"]}\n発言種類：{r["style"]}\n別の具体的な場面を考え、一組作ってください。')],tokenize=False,add_generation_prompt=True) for r in batch]
                x=tok(prompts,return_tensors='pt',padding=True).to('cuda')
                if x['input_ids'].shape[1]>900:raise ValueError('Unexpected prompt length')
                out=model.generate(**x,max_new_tokens=100,do_sample=True,temperature=.85,top_p=.92,pad_token_id=tok.pad_token_id)
                for r,ids in zip(batch,out[:,x['input_ids'].shape[1]:]):
                    text=tok.decode(ids,skip_special_tokens=True)
                    try:
                        if tok.eos_token_id not in ids.tolist():raise ValueError('truncated')
                        r.update(parse(text))
                    except ValueError as e:r.update(error=str(e),raw=text)
                    f.write(json.dumps(r,ensure_ascii=False)+'\n')
                f.flush()
                if off%(args.batch*4)==0:print(json.dumps(dict(done=off+len(batch),total=len(pending),seconds=round(time.monotonic()-start,1))),flush=True)
        del model;torch.cuda.empty_cache()
    convert=Kana();accepted=[];reject=Counter();seen=set()
    for line in path.read_text().splitlines():
        r=json.loads(line)
        try:
            if 'error' in r:raise ValueError(r['error'])
            if BLOCK.search(r['question']+r['answer']):raise ValueError('content filter')
            q=convert(r['question']);a=convert(r['answer'])
            if not 4<=len(q)<=80 or not 3<=len(a)<=44 or len(q)+len(a)+3>128:raise ValueError('kana length')
            if q in seen:raise ValueError('duplicate question')
            seen.add(q);accepted.append({**r,'question_kana':q,'answer_kana':a})
        except (ValueError,KeyError) as e:reject[str(e)]+=1
    for split in ('train','dev'):
        (root/f'{split}.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in accepted if r['split']==split))
    summary=dict(accepted=len(accepted),splits=dict(Counter(r['split'] for r in accepted)),rejected=dict(reject),topics=len(TOPICS),teacher_revision='cdbee75f17c01a7cc42f958dc650907174af0554',warning='Synthetic, not human verified. No automatic training or deployment. Topic/style families split, not entirely unseen topics. Teacher Apache-2.0; locally generated from authored instructions, no human corpus included.')
    (root/'manifest.json').write_text(json.dumps(summary,indent=2)+'\n');print(summary,flush=True)

if __name__=='__main__':main()
