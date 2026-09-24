"""Compare portable C outputs with the quantized-weight PyTorch reference."""
import argparse
import json
import subprocess
import struct
import time
import numpy as np
import torch
from safetensors.torch import load_file
from benchmark import ROOT
from ctc import PhonemeCTC, PHONES, decode


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--name',default='ctc')
    parser.add_argument('--layers',type=int,default=3)
    parser.add_argument('--checkpoint',default='latest')
    args=parser.parse_args()
    directory=ROOT/'.cache'/args.name
    index=json.loads((ROOT/'.cache/prepared/validation/index.json').read_text())
    entry=min(index,key=lambda e:abs(e['samples']-64000))
    data=np.load(ROOT/'.cache/prepared/validation'/entry['file'],allow_pickle=False)
    audio=data['audio']; audio.astype('<f4').tofile(directory/'probe.f32')
    (directory/'probe.bin').write_bytes(struct.pack('<I',len(audio))+audio.astype('<f4').tobytes())
    model=PhonemeCTC(keep=(0,2,4) if args.layers==3 else tuple(range(6))).eval()
    model.load_state_dict(load_file(str(directory/(args.checkpoint+'.safetensors'))))
    with torch.no_grad():
        for p in model.parameters():
            if p.ndim>=2:
                scale=p.abs().amax(dim=tuple(range(1,p.ndim)),keepdim=True).clamp_min(1e-8)/127
                p.copy_((p/scale).round().clamp(-127,127)*scale)
        reference=model(torch.from_numpy(audio).unsqueeze(0))[0].numpy()
    report={'sample':entry['file'],'seconds':len(audio)/16000,'variants':[]}
    for qa in (0,1):
        start=time.perf_counter()
        subprocess.run([str(ROOT/'.cache/ctc-native'),str(directory/'model-int8.bin'),str(directory/'probe.f32'),
                        str(directory/f'logits-{qa}.f32'),str(qa)],check=True)
        result=np.fromfile(directory/f'logits-{qa}.f32',dtype='<f4').reshape(-1,len(PHONES))
        if result.shape!=reference.shape or not np.isfinite(result).all():
            raise AssertionError('Runtime output invalid')
        diff=np.abs(result-reference)
        item={'quantized_activations':bool(qa),'max_logit_error':float(diff.max()),'mean_logit_error':float(diff.mean()),
              'frame_argmax_agreement':float(np.mean(result.argmax(-1)==reference.argmax(-1))),
              'ctc_sequence_agrees':decode(result.argmax(-1))==decode(reference.argmax(-1)),
              'native_seconds':time.perf_counter()-start}
        if qa==0 and (diff.max()>0.01 or not item['ctc_sequence_agrees']):
            raise AssertionError(item)
        report['variants'].append(item)
    (ROOT/'results'/f'{args.name}_runtime.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report),flush=True)
