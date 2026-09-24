"""Fixed public synthetic questions only. No microphone, TTS, or device writes."""
import argparse
import json
from pathlib import Path
import re
import time
import serial

ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser();p.add_argument('--port',default='COM4')
    p.add_argument('--reference',type=Path,default=ROOT/'results/tiny_lm_dropout_packed.json')
    p.add_argument('--out',type=Path,default=ROOT/'results/tiny_lm_device.json');args=p.parse_args()
    if args.out.exists():raise FileExistsError(args.out)
    ref=json.loads(args.reference.read_text(encoding='utf-8'))
    port=serial.Serial();port.port=args.port;port.baudrate=115200;port.timeout=.5;port.write_timeout=3;port.dtr=False;port.rts=False
    results=[];faults=[]
    with port:
        port.reset_input_buffer();port.write(b'ID\n');deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            line=port.readline().decode('utf-8',errors='replace')
            if line.startswith('RLCD42_MIC_PROBE:v1') and 'ASKSAY' in line:break
        else:raise RuntimeError('Expected LM firmware not detected')
        for split in ('canonical','dev'):
            for entry in ref[split]['predictions']:
                port.write(('ASK '+entry['question']+'\n').encode());lines=[];deadline=time.monotonic()+15
                while time.monotonic()<deadline:
                    line=port.readline().decode('utf-8',errors='replace').strip()
                    if line:lines.append(line)
                    if 'Guru Meditation' in line or 'stack overflow' in line:raise RuntimeError(line)
                    if line.startswith('LM_DONE:'):break
                else:raise TimeoutError('No LM_DONE')
                answer=next((s[len('LM_REPLY:'):] for s in lines if s.startswith('LM_REPLY:')),None)
                metrics={}
                for line in lines:
                    if line.startswith(('LM_METRICS:','LM_DONE:')):
                        metrics.update({k:int(v) for k,v in re.findall(r'([a-z_]+)=(\d+)',line)})
                match=answer==entry['prediction']
                leak=metrics.get('psram_before')!=metrics.get('psram_after')
                results.append(dict(split=split,question=entry['question'],answer=answer,
                    matches_native=match,exact_acceptable=answer in entry['answers'],metrics=metrics))
                if not match or leak or metrics.get('ok')!=1:faults.append(entry['question'])
                if len(results)%10==0:print(f'completed={len(results)} parity_or_memory_faults={len(faults)}',flush=True)
        # Reject unsupported input and overlong framing, then recover on valid input.
        for command,expected in [('ASK 漢字','ERROR:LM_INPUT_USE_KANA_MAX80'),('X'*410,'ERROR:LONG_COMMAND'),('LMBENCH','LM_DONE:ok=1')]:
            port.write((command+'\n').encode());deadline=time.monotonic()+10;found=False
            while time.monotonic()<deadline:
                line=port.readline().decode('utf-8',errors='replace').strip()
                if line.startswith(expected):found=True;break
            if not found:faults.append('protocol:'+expected)
    report=dict(model_sha256_expected=ref['model_sha256'],device='ESP32-S3 RLCD4.2 N16R8',
        warning='Development corpus, not independent test. Exact text parity with native packed C runtime; no open-domain or live speech quality claim.',
        cases=results,faults=faults)
    args.out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'cases':len(results),'native_matches':sum(r['matches_native'] for r in results),'faults':faults}),flush=True)
    if faults:raise RuntimeError('Device evaluation failed')

if __name__=='__main__':main()
