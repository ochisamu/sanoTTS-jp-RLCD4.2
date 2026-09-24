"""Controlled wording-dev comparison; exact match is NOT semantic accuracy."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import torch
from safetensors.torch import load_file
from tokenizers import Tokenizer
import train as core
from bpe_probe import generate

def clean(s):return re.sub('[。、！？]','',s)

def main():
    p=argparse.ArgumentParser();g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--model',type=Path);g.add_argument('--checkpoint',type=Path)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--data',type=Path,default=core.ROOT/'.cache/daily-kana')
    args=p.parse_args();root=args.data
    if args.model:
        header=struct.unpack('<8s10I',args.model.read_bytes()[:48]);d,h,f=header[3:6]
        bpe=header[0]==b'KLMW8v2\0';exe=core.ROOT/f'.cache/klm-native-{d}-{int(bpe)}-l{header[2]}'
        flags=[f'-DKLM_LAYERS={header[2]}']+(['-DKLM_BPE=1'] if bpe else [])
        subprocess.run(['cc','-O3','-std=c11','-Wall','-Wextra','-Werror',f'-DKLM_DIM={d}',f'-DKLM_HEADS={h}',f'-DKLM_FF={f}',*flags,str(core.ROOT/'tiny_lm/klm.c'),str(core.ROOT/'tiny_lm/native.c'),'-lm','-o',str(exe)],check=True)
        def predict(q):
            run=subprocess.run([str(exe),str(args.model),q],capture_output=True,text=True)
            return dict(prediction=run.stdout.strip(),terminated=run.returncode==0)
        artifact=args.model;runtime='native C W8A8'
    else:
        tok=Tokenizer.from_file(str(core.ROOT/'.cache/daily-bpe/tokenizer.json'))
        core.D=256;core.H=8;core.FF=768;core.V=tok.get_vocab_size();core.T=96
        torch.set_num_threads(4);torch.manual_seed(20260924)
        model=core.LM().cuda().eval();model.load_state_dict(load_file(str(args.checkpoint)))
        def predict(q):return generate(model,tok,q)
        artifact=args.checkpoint;runtime='host FP32 BPE, not device'
    rows=[];seen=set()
    for line in (root/'train.jsonl').read_text().splitlines():
        r=json.loads(line)
        if r['group'] in seen:continue
        seen.add(r['group']);rows.append({**r,'evaluation_set':'train_canonical'})
    rows.extend({**json.loads(s),'evaluation_set':'wording_dev'} for s in (root/'dev.jsonl').read_text().splitlines())
    results=[]
    for r in rows:
        result={**r,**predict(r['question_kana'])}
        result['exact_without_punctuation']=clean(result['prediction'])==clean(r['answer_kana'])
        results.append(result)
    summary={}
    for split in ('train_canonical','wording_dev'):
        subset=[r for r in results if r['evaluation_set']==split]
        summary[split]=dict(total=len(subset),exact=sum(r['exact_without_punctuation'] for r in subset),terminated=sum(r['terminated'] for r in subset))
    report=dict(artifact_sha256=hashlib.sha256(artifact.read_bytes()).hexdigest(),runtime=runtime,summary=summary,cases=results,
        warning='Known topics/answers, held-out question wordings. Dev used for comparison, not an independent test. Exact match undercounts valid paraphrases and does not measure broad dialogue.')
    args.out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps(summary),flush=True)
    for r in [r for r in results if r['evaluation_set']=='wording_dev' and not r['exact_without_punctuation']][:24]:print(r['question']+' -> '+r['prediction']+' [target '+r['answer_kana']+']',flush=True)

if __name__=='__main__':main()
