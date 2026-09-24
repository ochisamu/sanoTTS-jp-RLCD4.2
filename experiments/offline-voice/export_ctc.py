"""Export local CTC weights to a checked, aligned, packed INT8 file."""
import argparse
import hashlib
import json
import struct
import numpy as np
from safetensors.numpy import load_file
from benchmark import ROOT
from ctc import PHONES


def export(source, output, layers):
    tensors=load_file(str(source))
    names=sorted(tensors)
    blob=bytearray(32+96*len(names))
    struct.pack_into('<8sIIII',blob,0,b'RLCTC01\0',len(names),layers,len(PHONES),0)
    def append(data):
        blob.extend(bytes((-len(blob))%16))
        offset=len(blob); blob.extend(data); return offset
    for i,name in enumerate(names):
        value=tensors[name]
        if value.ndim>=2:
            matrix=value.reshape(value.shape[0],-1)
            rows,cols=matrix.shape; stride=(cols+15)//16*16
            scale=np.maximum(np.abs(matrix).max(axis=1),1e-8)/127
            quant=np.zeros((rows,stride),dtype=np.int8)
            quant[:,:cols]=np.rint(matrix/scale[:,None]).clip(-127,127).astype(np.int8)
            data=append(quant.tobytes()); scales=append(scale.astype('<f4').tobytes()); kind=1
        else:
            rows=value.size; cols=stride=1; kind=0; scales=0
            data=append(value.astype('<f4').tobytes())
        if len(name.encode())>=64:
            raise ValueError('Tensor name too long')
        struct.pack_into('<64sIIIIII',blob,32+i*96,name.encode(),rows,cols,stride,kind,data,scales)
    output.write_bytes(blob)
    output.with_suffix('.json').write_text(json.dumps({'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'sha256':hashlib.sha256(blob).hexdigest(),'bytes':len(blob),'layers':layers,'vocabulary':PHONES,
        'license':'Moonshine AI Community License; local research derivative',
        'quantization':'per-output-row symmetric int8 weights; float32 bias/norm'},indent=2))
    print('Exported',len(blob),'bytes',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--name',default='ctc6')
    parser.add_argument('--checkpoint',default='best')
    parser.add_argument('--layers',type=int,choices=(3,6),default=6)
    args=parser.parse_args()
    folder=ROOT/'.cache'/args.name
    export(folder/(args.checkpoint+'.safetensors'),folder/'model-int8.bin',args.layers)
