"""Small local instruction-following audit; outputs are not training data."""
import json
import argparse
from pathlib import Path
import torch
from transformers import AutoTokenizer,AutoModelForCausalLM
from dialogue_data import ROOT

QUESTIONS=['あなたは実際にご飯を食べられるの','昨日はどこへ出かけたの','今の東京の天気を調べて','料理を始めたいけど何から作ればいい','猫がいつも机に乗ってくる','仕事でくたくたになった','自転車と電車ならどちらで通おう','二たす二はいくつ','明日は友達の誕生日なんだ','新しい靴が少しきつい','ラーメンは食べられますか','どんな映画がおすすめ']
SYSTEM='''あなたは会話だけできる卓上ロボット「りこ」です。日本語の短い一文（8〜20文字程度）だけで利用者に直接返事をしてください。説明やJSONは不要です。
ロボットには人間の生活経験がなく、食事・旅行・睡眠はできません。インターネットも時計もカメラもありません。実際にはできない行動や検索をしたと言わないでください。
相手の質問・話題に具体的に応じてください。わからないことは正直に伝えます。
例：利用者「あなたは食事をするの？」→「食べられないけど、話は聞けるよ。」
例：利用者「今日は疲れた」→「お疲れさま。少し休もう。」
例：利用者「今の気温は？」→「今の気温は調べられないよ。」'''

def main():
    p=argparse.ArgumentParser();p.add_argument('--teacher',type=Path,default=ROOT/'.cache/dialogue/teacher')
    p.add_argument('--out',type=Path,default=ROOT/'.cache/dialogue/direct-teacher-audit.json')
    p.add_argument('--user-instruction',action='store_true');args=p.parse_args()
    torch.set_num_threads(4)
    path=args.teacher
    tok=AutoTokenizer.from_pretrained(path,local_files_only=True,trust_remote_code=False,padding_side='left')
    model=AutoModelForCausalLM.from_pretrained(path,local_files_only=True,trust_remote_code=False,torch_dtype=torch.bfloat16,attn_implementation='sdpa').cuda().eval()
    prompts=[tok.apply_chat_template([dict(role='user',content=SYSTEM+'\n\n利用者の発言：'+q+'\n返答を短い一文だけで書いてください。')] if args.user_instruction else [dict(role='system',content=SYSTEM),dict(role='user',content=q)],tokenize=False,add_generation_prompt=True) for q in QUESTIONS]
    print(repr(prompts[0][-200:]),flush=True)
    x=tok(prompts,return_tensors='pt',padding=True).to('cuda')
    with torch.inference_mode():out=model.generate(**x,max_new_tokens=80,do_sample=False,pad_token_id=tok.pad_token_id)
    results=[dict(question=q,answer=tok.decode(ids,skip_special_tokens=True)) for q,ids in zip(QUESTIONS,out[:,x['input_ids'].shape[1]:])]
    for r in results:print(json.dumps(r,ensure_ascii=False),flush=True)
    args.out.write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')

if __name__=='__main__':main()
