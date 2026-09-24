"""Version-2 kana BPE W8A8 artifact. No automatic flashing."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import numpy as np
from safetensors.torch import load_file
from tokenizers import Tokenizer
import train as core

STRIDE=40

def export(model,tokenizer,path,max_bytes=0x300000):
    spec=json.loads(tokenizer.to_str());vocab=spec['model']['vocab'];merges=spec['model']['merges']
    assert tokenizer.get_vocab_size()==1024 and len(merges)==918
    table=bytearray(1024*STRIDE)
    for i in range(5,1024):
        token=tokenizer.id_to_token(i).encode()
        if not 1<=len(token)<=36:raise ValueError('Token too long')
        table[i*STRIDE]=len(token);table[i*STRIDE+1:i*STRIDE+1+len(token)]=token
    pairs=[]
    for rank,(left,right) in enumerate(merges):
        out=vocab[left+right]
        if out!=106+rank or vocab[left]>=out or vocab[right]>=out:raise ValueError('Unsupported merge ordering')
        pairs.append((vocab[left],vocab[right],out))
    blob=bytearray(48)
    def append(raw):blob.extend(b'\0'*((-len(blob))%16));blob.extend(raw)
    def vector(x):append(x.detach().cpu().numpy().astype('<f4').tobytes())
    def matrix(x):
        x=x.detach().cpu().numpy();scale=np.maximum(np.abs(x).max(1),1e-8)/127
        append(np.clip(np.rint(x/scale[:,None]),-127,127).astype('i1').tobytes());append(scale.astype('<f4').tobytes())
    append(table);append(np.array(pairs,dtype='<u2').tobytes())
    matrix(model.emb.weight);vector(model.pos.weight)
    for b in model.blocks:
        vector(b.n1.weight);matrix(b.qkv.weight);matrix(b.o.weight)
        vector(b.n2.weight);matrix(b.up.weight);matrix(b.down.weight)
    vector(model.norm.weight)
    checksum=2166136261
    for b in blob[48:]:checksum=((checksum^b)*16777619)&0xffffffff
    struct.pack_into('<8s10I',blob,0,b'KLMW8v2\0',len(blob),len(model.blocks),256,8,768,1024,96,checksum,len(merges),STRIDE)
    if len(blob)>max_bytes:raise ValueError('Exceeds explicit model partition budget')
    path.write_bytes(blob)
    return dict(bytes=len(blob),sha256=hashlib.sha256(blob).hexdigest(),merges=len(merges),token_stride=STRIDE)

def main():
    p=argparse.ArgumentParser();p.add_argument('--checkpoint',type=Path,required=True)
    p.add_argument('--tokenizer',type=Path,default=core.ROOT/'.cache/bpe-dialogue/tokenizer.json')
    p.add_argument('--layers',type=int,choices=[4,5],default=4)
    p.add_argument('--max-bytes',type=lambda x:int(x,0),default=0x300000)
    p.add_argument('--out',type=Path,required=True);args=p.parse_args()
    core.D=256;core.H=8;core.FF=768;core.V=1024;core.T=96
    core.L=args.layers
    model=core.LM().eval();model.load_state_dict(load_file(str(args.checkpoint)))
    result=export(model,Tokenizer.from_file(str(args.tokenizer)),args.out,args.max_bytes)
    result.update(checkpoint_sha256=hashlib.sha256(args.checkpoint.read_bytes()).hexdigest(),tokenizer_sha256=hashlib.sha256(args.tokenizer.read_bytes()).hexdigest())
    args.out.with_suffix('.manifest.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':main()
