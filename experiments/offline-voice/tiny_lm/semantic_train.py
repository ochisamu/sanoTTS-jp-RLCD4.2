"""Distill semantic question representations into the same tiny causal LM.

The projection is training-only. No nearest-neighbour index or classifier is
exported. Preserves kana language modelling with a small auxiliary LM loss.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import time
import numpy as np
import torch
from torch.nn import functional as F
from safetensors.torch import load_file,save_file
import train as core

def main():
    p=argparse.ArgumentParser();p.add_argument('--steps',type=int,default=8000);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--resume',type=Path,default=core.ROOT/'.cache/bpe-language-256/best.safetensors');args=p.parse_args()
    args.out.mkdir(exist_ok=True)
    if (args.out/'report.json').exists():raise FileExistsError('Existing experiment')
    core.D=256;core.H=8;core.FF=768;core.V=1024;core.T=96
    torch.set_num_threads(4);torch.manual_seed(8642)
    model=core.LM(.1).cuda();model.load_state_dict(load_file(str(args.resume)))
    projection=torch.nn.Linear(256,384,bias=False).cuda();root=core.ROOT/'.cache/semantic'
    data={};mean=torch.tensor(np.load(root/'train-vectors.npy').astype(np.float32).mean(0),device='cuda')
    for split in ('train','dev'):
        x=torch.tensor(np.load(root/f'{split}-ids.npy'),device='cuda',dtype=torch.long)
        target=F.normalize(torch.tensor(np.load(root/f'{split}-vectors.npy'),device='cuda',dtype=torch.float32)-mean,dim=-1)
        sep=(x==2).long().argmax(1);labels=x[:,1:].clone();labels[labels==0]=-100
        data[split]=(x,target,sep,labels)
    params=list(model.parameters())+list(projection.parameters());opt=torch.optim.AdamW(params,lr=.0003,weight_decay=.02)
    def losses(x,target,sep,labels):
        with torch.autocast('cuda',dtype=torch.bfloat16):logits,h=model(x,return_hidden=True);projected=projection(h[torch.arange(len(x),device='cuda'),sep])
        emb=F.normalize(projected.float(),dim=-1)
        cosine=(1-(emb*target).sum(-1)).mean()
        contrast=F.cross_entropy(emb@target.T/.1,torch.arange(len(x),device='cuda'))
        lm=F.cross_entropy(logits[:,:-1].float().flatten(0,1),labels.flatten())
        return cosine+.2*contrast+.1*lm,cosine,contrast,lm
    best=float('inf');events=[];start=time.monotonic()
    def checkpoint(step):
        nonlocal best
        model.eval();projection.eval();values=[]
        with torch.inference_mode():
            for off in range(0,len(data['dev'][0]),128):
                batch=[a[off:off+128] for a in data['dev']]
                values.append([float(v) for v in losses(*batch)])
        avg=np.mean(values,axis=0).tolist();event=dict(step=step,dev_objective=avg[0],dev_cosine_loss=avg[1],dev_contrastive=avg[2],dev_lm_nll=avg[3],seconds=time.monotonic()-start)
        if avg[0]<best:
            best=avg[0];event['best']=True
            save_file({k:v.detach().cpu().contiguous() for k,v in model.state_dict().items()},str(args.out/'best.safetensors'))
            save_file({'weight':projection.weight.detach().cpu().contiguous(),'teacher_mean':mean.cpu()},str(args.out/'projection.safetensors'))
        events.append(event);print(json.dumps(event),flush=True);model.train();projection.train()
    checkpoint(0);x,target,sep,labels=data['train']
    for step in range(1,args.steps+1):
        rate=.0003*min(1,step/200)*(.1+.9*.5*(1+math.cos(math.pi*step/args.steps)))
        for g in opt.param_groups:g['lr']=rate
        idx=torch.randint(len(x),(128,),device='cuda');opt.zero_grad(set_to_none=True)
        loss,cosine,contrast,lm=losses(x[idx],target[idx],sep[idx],labels[idx])
        if not torch.isfinite(loss):raise ValueError('Nonfinite loss')
        loss.backward();torch.nn.utils.clip_grad_norm_(params,1);opt.step()
        if step%1000==0:print(json.dumps(dict(step=step,objective=float(loss.detach()),cosine_loss=float(cosine.detach()),lm_nll=float(lm.detach()),seconds=time.monotonic()-start)),flush=True)
        if step%2000==0 or step==args.steps:checkpoint(step)
    report=dict(steps=args.steps,seed=8642,events=events,source_checkpoint=str(args.resume),
        source_sha256=hashlib.sha256(args.resume.read_bytes()).hexdigest(),target_manifest_sha256=hashlib.sha256((root/'manifest.json').read_bytes()).hexdigest(),
        warning='Teacher representation distillation, not response quality. Projection used only for training and never exported; no test data or runtime retrieval.')
    (args.out/'report.json').write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__':main()
