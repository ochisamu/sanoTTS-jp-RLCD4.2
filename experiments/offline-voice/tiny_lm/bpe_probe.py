"""Host-only BPE generation audit; developer probes are not a final test."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import torch
from safetensors.torch import load_file
from tokenizers import Tokenizer
import train as core
from dialogue_data import Kana,ROOT
from dialogue_probe import PROBES

@torch.inference_mode()
def generate(model,tok,q,temperature=0,penalty=1.0):
    ids=[1]+tok.encode(q).ids+[2];out=[];terminated=False
    if len(ids)>80 or 4 in ids:raise ValueError('Invalid input')
    for _ in range(min(40,core.T-len(ids))):
        scores=model(torch.tensor([ids],device='cuda'))[0,-1].float()
        scores[:3]=-float('inf');scores[4]=-float('inf')
        for i in set(out):scores[i]=scores[i]/penalty if scores[i]>0 else scores[i]*penalty
        if temperature:
            values,indices=torch.topk(scores,20);index=torch.multinomial(torch.softmax(values/temperature,dim=-1),1)
            token=int(indices[index])
        else:token=int(scores.argmax())
        if token==3:terminated=True;break
        ids.append(token);out.append(token)
    answer=''.join(tok.id_to_token(i) for i in out)
    return dict(prediction=answer,terminated=terminated,tokens=len(out),characters=len(answer))

def main():
    p=argparse.ArgumentParser();p.add_argument('--checkpoint',type=Path,required=True)
    p.add_argument('--tokenizer',type=Path,default=ROOT/'.cache/bpe-dialogue/tokenizer.json')
    p.add_argument('--data',type=Path,default=ROOT/'.cache/realchat')
    p.add_argument('--out',type=Path,required=True);p.add_argument('--count',type=int,default=12)
    p.add_argument('--temperature',type=float,default=0);p.add_argument('--penalty',type=float,default=1)
    args=p.parse_args();tok=Tokenizer.from_file(str(args.tokenizer))
    core.D=256;core.H=8;core.FF=768;core.V=tok.get_vocab_size();core.T=96
    torch.set_num_threads(4);torch.manual_seed(5060)
    model=core.LM().cuda().eval();model.load_state_dict(load_file(str(args.checkpoint)))
    convert=Kana();items=[dict(question=q,question_kana=convert(q),source='authored dev probe') for q in PROBES]
    pool=[json.loads(s) for s in (args.data/'dev.jsonl').read_text().splitlines()]
    items.extend(random.Random(60173).sample(pool,min(args.count,len(pool))))
    results=[]
    for r in items:
        result={**r,**generate(model,tok,r['question_kana'],args.temperature,args.penalty)};results.append(result)
        print(r['question']+' -> '+result['prediction'],flush=True)
    report=dict(checkpoint_sha256=hashlib.sha256(args.checkpoint.read_bytes()).hexdigest(),
        tokenizer_sha256=hashlib.sha256(args.tokenizer.read_bytes()).hexdigest(),temperature=args.temperature,
        repetition_penalty=args.penalty,cases=results,warning='Host float model, development only, not packed/device or independent test. No exact-match quality metric.')
    args.out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')

if __name__=='__main__':main()
