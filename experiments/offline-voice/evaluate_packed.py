"""Measure dev PER of packed W8A8 portable inference, using the same 64 clips."""
import json
import argparse
import random
import subprocess
import numpy as np
from benchmark import ROOT, edit_distance
from ctc import PHONES, decode

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--qa',type=int,choices=(1,2,3,4,5),default=1);args=parser.parse_args()
    directory=ROOT/'.cache/ctc6'
    entries=json.loads((ROOT/'.cache/prepared/validation/index.json').read_text())
    entries=random.Random(43).sample(entries,64)
    errors=total=0
    for index,e in enumerate(entries):
        with np.load(ROOT/'.cache/prepared/validation'/e['file'],allow_pickle=False) as data:
            audio=data['audio']; ref=data['labels'].tolist()
        audio.astype('<f4').tofile(directory/'eval-input.f32')
        subprocess.run([str(ROOT/'.cache/ctc-native'),str(directory/'model-int8.bin'),
            str(directory/'eval-input.f32'),str(directory/'eval-logits.f32'),str(args.qa)],check=True,stdout=subprocess.DEVNULL)
        logits=np.fromfile(directory/'eval-logits.f32',dtype='<f4').reshape(-1,len(PHONES))
        if not np.isfinite(logits).all(): raise RuntimeError('Non-finite logits')
        pred=decode(logits.argmax(-1)); errors+=edit_distance(ref,pred); total+=len(ref)
        if (index+1)%16==0: print('dev',index+1,'PER',errors/total,flush=True)
    result={'dev_utterances':len(entries),'reference_phonemes':total,'edit_errors':errors,'PER':errors/total,
        'runtime':'portable C, packed int8 weights, per-patch int8 activations; CPU, not ESP32',
        'attention_quantization':args.qa,'warning':'Development subset; no independent final-test claim.'}
    name='packed_dev.json' if args.qa==1 else f'packed_dev_qa{args.qa}.json'
    (ROOT/'results'/name).write_text(json.dumps(result,indent=2))
    print(json.dumps(result),flush=True)
