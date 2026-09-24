"""Evaluate packed C runtime, independently from the floating-point generator."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from data import CASES, corpus
ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser();p.add_argument('--model',type=Path,default=ROOT/'.cache/tiny-lm/model.bin')
    p.add_argument('--out',type=Path,default=ROOT/'results/tiny_lm_packed.json');args=p.parse_args()
    subprocess.run(['cc','-O3','-std=c11','-Wall','-Wextra','-Werror',str(ROOT/'tiny_lm/klm.c'),str(ROOT/'tiny_lm/native.c'),'-lm','-o',str(ROOT/'.cache/klm-native')],check=True)
    def evaluate(items):
        result=[]
        for e in items:
            run=subprocess.run([str(ROOT/'.cache/klm-native'),str(args.model),e['question']],capture_output=True,text=True)
            answer=run.stdout.strip()
            result.append({**e,'prediction':answer,'terminated':run.returncode==0,
                           'exact_acceptable':run.returncode==0 and answer in e['answers']})
        return dict(count=len(result),exact_acceptable=sum(e['exact_acceptable'] for e in result),
                    terminated=sum(e['terminated'] for e in result),predictions=result)
    canonical=[dict(intent=i,question=q.split('|')[0],answers=a.split('|')) for i,q,_,a in CASES]
    _,dev=corpus()
    report=dict(model_sha256=hashlib.sha256(args.model.read_bytes()).hexdigest(),
        warning='Synthetic narrow-domain smoke test, not general Japanese conversation. Dev questions have held-out wordings but known intents/answers; dev is not a final test.',
        canonical=evaluate(canonical),dev=evaluate(dev))
    args.out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:{a:b for a,b in v.items() if a!='predictions'} for k,v in report.items() if isinstance(v,dict)},ensure_ascii=False))

if __name__=='__main__':main()
