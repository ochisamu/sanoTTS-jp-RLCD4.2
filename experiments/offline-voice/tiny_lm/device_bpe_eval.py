"""Explicit device generation regression; public authored questions only."""
import argparse
import json
from pathlib import Path
import random
import re
import time
import serial

def main():
    p=argparse.ArgumentParser();p.add_argument('--port',default='COM4')
    p.add_argument('--reference',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--count',type=int,default=32);args=p.parse_args()
    if args.out.exists():raise FileExistsError(args.out)
    ref=json.loads(args.reference.read_text(encoding='utf-8'))
    cases=random.Random(942).sample(ref['cases'],min(args.count,len(ref['cases'])))
    port=serial.Serial();port.port=args.port;port.baudrate=115200;port.timeout=.3;port.write_timeout=3;port.dtr=False;port.rts=False
    results=[];faults=[]
    with port:
        port.reset_input_buffer();port.write(b'ID\n');deadline=time.monotonic()+8
        while time.monotonic()<deadline:
            line=port.readline().decode('utf-8',errors='replace')
            if line.startswith('RLCD42_MIC_PROBE:v1') and 'ASKSAY' in line:break
        else:raise RuntimeError('Expected device not identified')
        for r in cases:
            q=r['question_kana'];port.write(('ASK '+q+'\n').encode('utf-8'));lines=[];deadline=time.monotonic()+25
            while time.monotonic()<deadline:
                line=port.readline().decode('utf-8',errors='replace').strip()
                if line:lines.append(line)
                if 'Guru Meditation' in line or 'stack overflow' in line:raise RuntimeError(line)
                if line.startswith('LM_DONE:'):break
            else:raise TimeoutError(q)
            answer=next((s[9:] for s in lines if s.startswith('LM_REPLY:')),None);metrics={}
            for line in lines:
                if line.startswith(('LM_METRICS:','LM_DONE:')):metrics.update({k:int(v) for k,v in re.findall(r'([a-z_]+)=(\d+)',line)})
            match=answer==r['prediction'];leak=metrics.get('psram_before')!=metrics.get('psram_after')
            result=dict(question=q,expected=r['prediction'],answer=answer,matches_native=match,metrics=metrics);results.append(result)
            if not match or leak or metrics.get('ok')!=1:faults.append(q)
            print(json.dumps(result,ensure_ascii=False),flush=True)
        # Explicit errors must return the memory they allocated too.
        for q in ('漢字','あ'*81):
            port.write(('ASK '+q+'\n').encode('utf-8'));lines=[];deadline=time.monotonic()+15
            while time.monotonic()<deadline:
                s=port.readline().decode('utf-8',errors='replace').strip();lines.append(s)
                if s.startswith('LM_DONE:'):break
            if not any(s.startswith('ERROR:LM_INPUT_USE_KANA_MAX80') for s in lines):faults.append('input validation')
    report=dict(model_sha256_expected=ref['artifact_sha256'],cases=results,faults=faults,
        warning='Device/native parity and memory test, not dialogue accuracy or microphone validation.')
    args.out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(cases=len(results),matches=sum(r['matches_native'] for r in results),faults=faults)),flush=True)
    if faults:raise RuntimeError('Device regression failed')

if __name__=='__main__':main()
