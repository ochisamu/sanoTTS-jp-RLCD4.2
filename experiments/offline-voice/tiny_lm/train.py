"""Small causal decoder, supervised response-only loss, original kana corpus.

No downloaded code/checkpoints. FP32 training, row-wise W8 export, W8A8 C runner.
"""
import argparse
import hashlib
import json
from pathlib import Path
import random
import struct
import time
import numpy as np
import torch
from torch import nn
from torch.nn import functional as F
from safetensors.torch import save_file
from data import VOCAB, CHARS, encode, decode, corpus

ROOT=Path(__file__).resolve().parents[1]
L,D,H,FF,V,T=4,192,6,512,128,128

class Norm(nn.Module):
    def __init__(self):
        super().__init__(); self.weight=nn.Parameter(torch.ones(D))
    def forward(self,x):
        return x*torch.rsqrt(x.square().mean(-1,keepdim=True)+1e-5)*self.weight

class Block(nn.Module):
    def __init__(self,dropout=0):
        super().__init__()
        self.dropout=dropout
        self.n1=Norm();self.qkv=nn.Linear(D,3*D,bias=False);self.o=nn.Linear(D,D,bias=False)
        self.n2=Norm();self.up=nn.Linear(D,FF,bias=False);self.down=nn.Linear(FF,D,bias=False)
    def forward(self,x):
        b,t,_=x.shape
        q,k,v=self.qkv(self.n1(x)).reshape(b,t,3,H,D//H).permute(2,0,3,1,4).unbind(0)
        a=F.scaled_dot_product_attention(q,k,v,is_causal=True,dropout_p=self.dropout if self.training else 0)
        x=x+F.dropout(self.o(a.transpose(1,2).reshape(b,t,D)),self.dropout,self.training)
        return x+F.dropout(self.down(F.relu(self.up(self.n2(x)))),self.dropout,self.training)

class LM(nn.Module):
    def __init__(self,dropout=0):
        super().__init__()
        self.dropout=dropout
        self.emb=nn.Embedding(V,D);self.pos=nn.Embedding(T,D)
        self.blocks=nn.ModuleList([Block(dropout) for _ in range(L)]);self.norm=Norm()
        self.apply(self.init)
    @staticmethod
    def init(m):
        if isinstance(m,(nn.Linear,nn.Embedding)): nn.init.normal_(m.weight,std=.02)
    def forward(self,x,return_hidden=False):
        x=F.dropout(self.emb(x)+self.pos(torch.arange(x.shape[1],device=x.device)),self.dropout,self.training)
        for block in self.blocks:x=block(x)
        h=self.norm(x);logits=F.linear(h,self.emb.weight)
        return (logits,h) if return_hidden else logits

@torch.no_grad()
def generate(model,q):
    ids=[1]+encode(q)+[2];out=[]
    for _ in range(min(40,T-len(ids))):
        logits=model(torch.tensor([ids],device='cuda'))[0,-1].float()
        logits[:3]=-float('inf');logits[4]=-float('inf');logits[5+len(CHARS):]=-float('inf')
        token=int(logits.argmax())
        if token==3:break
        ids.append(token);out.append(token)
    return decode(out)

def export(model,path):
    """Fixed versioned format. All arrays and matrix rows 16-byte aligned."""
    blob=bytearray(48)
    def append(raw):
        blob.extend(b'\0'*((-len(blob))%16));blob.extend(raw)
    def vector(x):append(x.detach().cpu().numpy().astype('<f4').tobytes())
    def matrix(x):
        x=x.detach().cpu().numpy()
        scale=np.maximum(np.abs(x).max(1),1e-8)/127
        q=np.clip(np.rint(x/scale[:,None]),-127,127).astype('int8')
        append(q.tobytes());append(scale.astype('<f4').tobytes())
    append(np.array([ord(c) if len(c)==1 else 0 for c in VOCAB],dtype='<u4').tobytes())
    matrix(model.emb.weight);vector(model.pos.weight)
    for b in model.blocks:
        vector(b.n1.weight);matrix(b.qkv.weight);matrix(b.o.weight)
        vector(b.n2.weight);matrix(b.up.weight);matrix(b.down.weight)
    vector(model.norm.weight)
    checksum=2166136261
    for b in blob[48:]:checksum=((checksum^b)*16777619)&0xffffffff
    struct.pack_into('<8s10I',blob,0,b'KLMW8v1\0',len(blob),L,D,H,FF,V,T,checksum,0,0)
    path.write_bytes(blob)
    return dict(bytes=len(blob),sha256=hashlib.sha256(blob).hexdigest())

def main():
    p=argparse.ArgumentParser();p.add_argument('--steps',type=int,default=1200)
    p.add_argument('--dropout',type=float,default=0)
    p.add_argument('--out',type=Path,default=ROOT/'.cache/tiny-lm');args=p.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    random.seed(20260924);np.random.seed(20260924);torch.manual_seed(20260924)
    torch.set_num_threads(4)
    model=LM(args.dropout).cuda();opt=torch.optim.AdamW(model.parameters(),lr=.001,weight_decay=.01)
    train,valid=corpus();rows=[];targets=[]
    for e in train:
        prompt=[1]+encode(e['question'])+[2]; answer=encode(e['answer'])+[3]
        full=prompt+answer
        assert len(full)<=T
        rows.append(full[:-1]);targets.append([-100]*(len(prompt)-1)+answer)
    length=max(map(len,rows))
    x=torch.tensor([r+[0]*(length-len(r)) for r in rows],device='cuda')
    y=torch.tensor([r+[-100]*(length-len(r)) for r in targets],device='cuda')
    report={'seed':20260924,'dropout':args.dropout,'config':dict(layers=L,dim=D,heads=H,ff=FF,vocab=V,context=T),
            'parameters':sum(p.numel() for p in model.parameters()),'train_rows':len(train),
            'held_out_questions':len(valid),'device':torch.cuda.get_device_name(),
            'warning':'Original synthetic narrow-domain corpus. Held-out phrasings, same intents and answers. Not open-domain evaluation. Dev is used for development.', 'events':[]}
    start=time.monotonic();torch.cuda.reset_peak_memory_stats()
    for step in range(1,args.steps+1):
        ix=torch.randint(len(rows),(64,),device='cuda');opt.zero_grad(set_to_none=True)
        logits=model(x[ix]);loss=F.cross_entropy(logits.flatten(0,1),y[ix].flatten())
        if not torch.isfinite(loss):raise ValueError('Nonfinite loss')
        loss.backward();nn.utils.clip_grad_norm_(model.parameters(),1);opt.step()
        if step%100==0 or step==args.steps:
            event=dict(step=step,loss=float(loss.detach()),seconds=time.monotonic()-start)
            report['events'].append(event);print(json.dumps(event),flush=True)
    model.eval();predictions=[]
    for e in valid:
        answer=generate(model,e['question'])
        predictions.append({**e,'prediction':answer,'exact_acceptable':answer in e['answers']})
    report['dev_exact_acceptable']=sum(e['exact_acceptable'] for e in predictions)/len(predictions)
    report['predictions']=predictions
    report['peak_cuda_MiB']=torch.cuda.max_memory_allocated()/2**20
    report['seconds']=time.monotonic()-start
    report['packed']=export(model,args.out/'model.bin')
    save_file({k:v.detach().cpu().contiguous() for k,v in model.state_dict().items()},str(args.out/'model.safetensors'))
    (args.out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('predictions','events')},ensure_ascii=False),flush=True)

if __name__=='__main__':main()
