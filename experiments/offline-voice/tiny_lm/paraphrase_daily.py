"""Question-only teacher augmentation; reviewed answers never rewritten.

Reads train seeds only, never wording-dev or evaluation probes. Generated
paraphrases require explicit semantic inspection before prepare_daily_aug.py is run.
"""
import argparse
import json
import time
import torch
from transformers import AutoTokenizer,AutoModelForCausalLM
from dialogue_data import ROOT

SYSTEM='''日本語の発言の意味を変えず、自然な話し言葉で言い換えてください。
質問なら質問のまま、出来事の報告なら報告のままにします。主体、肯定・否定、時制、対象を変えず、情報を足さないでください。
言い方や文の構造を変えた例を6個作り、JSONの文字列配列だけを出力してください。各例は5〜30文字程度。元の文への返答ではありません。
例：入力「本を読み終わった」→["一冊最後まで読んだよ","本を全部読み切った","ようやく読書が終わったよ","読んでいた本を読み切ったよ","読書を終えたところだよ","今さっき本を読み終えた"]'''

def main():
    p=argparse.ArgumentParser();p.add_argument('--batch',type=int,default=12);args=p.parse_args()
    root=ROOT/'.cache/daily-paraphrase';root.mkdir(exist_ok=True)
    families={}
    for s in (ROOT/'.cache/daily-kana/train.jsonl').read_text().splitlines():
        r=json.loads(s)
        f=families.setdefault(r['group'],dict(group=r['group'],questions=[],answer=r['answer']))
        if r['question'] not in f['questions']:f['questions'].append(r['question'])
    path=root/'teacher.jsonl';done=set()
    if path.exists():done={json.loads(s)['group'] for s in path.read_text().splitlines()}
    pending=[v for k,v in families.items() if k not in done]
    if not pending:return
    torch.set_num_threads(4);torch.manual_seed(60426)
    tok=AutoTokenizer.from_pretrained(ROOT/'.cache/dialogue/teacher',local_files_only=True,trust_remote_code=False,padding_side='left')
    model=AutoModelForCausalLM.from_pretrained(ROOT/'.cache/dialogue/teacher',local_files_only=True,trust_remote_code=False,torch_dtype=torch.bfloat16,attn_implementation='sdpa').cuda().eval()
    start=time.monotonic()
    with path.open('a') as f,torch.inference_mode():
        for off in range(0,len(pending),args.batch):
            batch=pending[off:off+args.batch]
            prompts=[tok.apply_chat_template([dict(role='system',content=SYSTEM),dict(role='user',content='同じ意味の元の発言：'+json.dumps(r['questions'][:2],ensure_ascii=False))],tokenize=False,add_generation_prompt=True) for r in batch]
            x=tok(prompts,return_tensors='pt',padding=True).to('cuda')
            out=model.generate(**x,max_new_tokens=260,do_sample=True,temperature=.6,top_p=.9,pad_token_id=tok.pad_token_id)
            for r,ids in zip(batch,out[:,x['input_ids'].shape[1]:]):
                text=tok.decode(ids,skip_special_tokens=True);row=dict(group=r['group'],source_questions=r['questions'],answer=r['answer'])
                try:
                    if tok.eos_token_id not in ids.tolist():raise ValueError('truncated')
                    result=json.loads(text[text.find('['):text.rfind(']')+1])
                    if not isinstance(result,list) or not 3<=len(result)<=10 or not all(isinstance(s,str) and 3<=len(s)<=60 for s in result):raise ValueError('schema')
                    row['questions']=result
                except ValueError as e:row.update(error=str(e),raw=text)
                f.write(json.dumps(row,ensure_ascii=False)+'\n')
            f.flush();print(json.dumps(dict(done=off+len(batch),total=len(pending),seconds=round(time.monotonic()-start,1))),flush=True)

if __name__=='__main__':main()
