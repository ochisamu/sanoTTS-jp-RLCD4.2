"""Broader language pretraining + short-response sequence-level distillation.

Never reads test.jsonl. Checkpoint selection uses dev teacher-forced NLL; final
generation quality is separately audited, not inferred from training loss.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import time
import numpy as np
import torch
from torch.nn import functional as F
from safetensors.torch import save_file,load_file
import train as core
from data import encode

def main():
    p=argparse.ArgumentParser();p.add_argument('--stage',choices=['language','dialogue'],required=True)
    p.add_argument('--steps',type=int,default=12000);p.add_argument('--dim',type=int,choices=[192,256],default=192)
    p.add_argument('--layers',type=int,choices=[4,5],default=4)
    p.add_argument('--expand-last',action='store_true',help='Append an initially identity residual block to a four-layer parent')
    p.add_argument('--resume',type=Path);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--batch',type=int,default=128);p.add_argument('--lr',type=float,default=.0007)
    p.add_argument('--data',type=Path,default=core.ROOT/'.cache/dialogue')
    p.add_argument('--bpe',action='store_true',help='Host-only BPE experiment; no device binary export')
    p.add_argument('--intent-aux',type=float,default=0,help='Training-only input-semantic auxiliary loss weight; no runtime classifier')
    p.add_argument('--semantic-projection',type=Path,help='Training-only E5 projection checkpoint')
    p.add_argument('--semantic-weight',type=float,default=.5)
    args=p.parse_args();root=args.data;args.out.mkdir(parents=True,exist_ok=True)
    if (args.out/'report.json').exists():raise FileExistsError('Use a new output directory')
    if args.dim==256:core.D=256;core.H=8;core.FF=768
    core.L=args.layers
    if args.layers!=4 and not args.bpe:raise ValueError('Five layers are BPE-only experimental')
    if args.bpe:
        from tokenizers import Tokenizer
        tokenizer=Tokenizer.from_file(str(root/'tokenizer.json'))
        core.V=tokenizer.get_vocab_size();core.T=96
    torch.set_num_threads(4);torch.manual_seed(20260924);random.seed(20260924);np.random.seed(20260924)
    model=core.LM(.1).cuda()
    if args.resume:
        state=load_file(str(args.resume))
        if args.expand_last:
            if args.layers!=5 or 'blocks.4.n1.weight' in state:raise ValueError('Expansion requires four-layer source and five-layer target')
            for key,value in list(state.items()):
                if key.startswith('blocks.3.'):
                    newkey=key.replace('blocks.3.','blocks.4.',1)
                    state[newkey]=torch.zeros_like(value) if key.endswith(('o.weight','down.weight')) else value.clone()
        model.load_state_dict(state)
    elif args.expand_last:raise ValueError('Expansion requires --resume')
    data={};hashes={}
    for split in ('train','dev'):
        if args.stage=='language':
            path=root/f'language-{split}.npy';raw=torch.tensor(np.load(path),device='cuda',dtype=torch.long)
            x=raw[:,:-1];y=raw[:,1:].clone();y[y==0]=-100
        elif args.bpe:
            path=root/f'dialogue-{split}.npy'
            x=torch.tensor(np.load(path)[:,:-1],device='cuda',dtype=torch.long)
            y=torch.tensor(np.load(root/f'labels-{split}.npy'),device='cuda',dtype=torch.long)
        else:
            path=root/f'{split}.jsonl';rows=[];targets=[]
            for line in path.read_text().splitlines():
                r=json.loads(line);q=[1]+encode(r['question_kana'])+[2];a=encode(r['answer_kana'])+[3]
                ids=q+a
                assert len(ids)<=128 and 4 not in ids
                rows.append(ids[:-1]+[0]*(128-len(ids)))
                targets.append([-100]*(len(q)-1)+a+[-100]*(128-len(ids)))
            x=torch.tensor(rows,device='cuda');y=torch.tensor(targets,device='cuda')
        if len(x)<8:raise ValueError('Too few examples')
        data[split]=(x,y);hashes[split]=hashlib.sha256(path.read_bytes()).hexdigest()
    auxiliary=None;intent_ids={};sep_positions={}
    if args.intent_aux:
        if args.stage!='dialogue':raise ValueError('Auxiliary requires dialogue stage')
        groups={}
        for split in ('train','dev'):
            values=[json.loads(s)['group'] for s in (root/f'{split}.jsonl').read_text().splitlines()]
            if split=='train':groups={v:i for i,v in enumerate(sorted(set(values)))}
            intent_ids[split]=torch.tensor([groups[v] for v in values],device='cuda')
            if len(values)!=len(data[split][0]):raise ValueError('Metadata/array row mismatch')
            sep_positions[split]=(data[split][0]==2).long().argmax(dim=1)
        auxiliary=torch.nn.Linear(core.D,len(groups)).cuda()
    semantic=None;semantic_targets=None
    if args.semantic_projection:
        if not args.bpe or args.stage!='dialogue':raise ValueError('Semantic targets require BPE dialogue stage')
        state=load_file(str(args.semantic_projection));semantic=torch.nn.Linear(core.D,384,bias=False).cuda()
        semantic.weight.data.copy_(state['weight'].cuda());teacher_mean=state['teacher_mean'].cuda()
        semantic_targets=F.normalize(torch.tensor(np.load(core.ROOT/'.cache/semantic/daily-train-vectors.npy'),device='cuda',dtype=torch.float32)-teacher_mean,dim=-1)
        if len(semantic_targets)!=len(data['train'][0]):raise ValueError('Semantic row mismatch')
        if 'train' not in sep_positions:sep_positions['train']=(data['train'][0]==2).long().argmax(1)
    params=list(model.parameters())+(list(auxiliary.parameters()) if auxiliary is not None else [])+(list(semantic.parameters()) if semantic is not None else [])
    opt=torch.optim.AdamW(params,lr=args.lr,weight_decay=.05)
    start=time.monotonic();best=float('inf');events=[];torch.cuda.reset_peak_memory_stats()
    def evaluate():
        model.eval();total=0;tokens=0;x,y=data['dev']
        with torch.inference_mode():
            for off in range(0,min(len(x),2048),128):
                xb=x[off:off+128];yb=y[off:off+128]
                with torch.autocast('cuda',dtype=torch.bfloat16):logits=model(xb)
                loss=F.cross_entropy(logits.float().flatten(0,1),yb.flatten(),reduction='sum')
                total+=float(loss);tokens+=int((yb!=-100).sum())
        model.train();return total/tokens
    def checkpoint(step):
        nonlocal best
        val=evaluate();event=dict(step=step,dev_nll=val,seconds=time.monotonic()-start)
        if val<best:
            best=val
            save_file({k:v.detach().cpu().contiguous() for k,v in model.state_dict().items()},str(args.out/'best.safetensors'))
            if semantic is not None:save_file({'weight':semantic.weight.detach().cpu().contiguous(),'teacher_mean':teacher_mean.cpu()},str(args.out/'projection.safetensors'))
            event['best']=True
        events.append(event);print(json.dumps(event),flush=True)
    checkpoint(0)
    x,y=data['train']
    for step in range(1,args.steps+1):
        rate=args.lr*min(1,step/200)*(.1+.9*.5*(1+math.cos(math.pi*step/args.steps)))
        for g in opt.param_groups:g['lr']=rate
        idx=torch.randint(len(x),(args.batch,),device='cuda');opt.zero_grad(set_to_none=True)
        with torch.autocast('cuda',dtype=torch.bfloat16):
            if auxiliary is None and semantic is None:logits=model(x[idx])
            else:
                logits,hidden=model(x[idx],return_hidden=True)
                question_hidden=hidden[torch.arange(args.batch,device='cuda'),sep_positions['train'][idx]]
                if auxiliary is not None:aux_logits=auxiliary(question_hidden)
                if semantic is not None:semantic_logits=semantic(question_hidden)
        loss=F.cross_entropy(logits.float().flatten(0,1),y[idx].flatten())
        language_loss=loss.detach()
        if auxiliary is not None:loss=loss+args.intent_aux*F.cross_entropy(aux_logits.float(),intent_ids['train'][idx])
        if semantic is not None:loss=loss+args.semantic_weight*(1-(F.normalize(semantic_logits.float(),dim=-1)*semantic_targets[idx]).sum(-1)).mean()
        if not torch.isfinite(loss):raise ValueError('Nonfinite training loss')
        loss.backward();torch.nn.utils.clip_grad_norm_(params,1);opt.step()
        if step%500==0:
            e=dict(step=step,train_nll=float(language_loss),train_objective=float(loss.detach()),seconds=time.monotonic()-start)
            events.append(e);print(json.dumps(e),flush=True)
        if step%2000==0 or step==args.steps:checkpoint(step)
    model.load_state_dict(load_file(str(args.out/'best.safetensors')));model.eval()
    packed=core.export(model,args.out/'model.bin') if not args.bpe else None
    report=dict(stage=args.stage,steps=args.steps,seed=20260924,dim=core.D,ff=core.FF,heads=core.H,layers=core.L,
        parameters=sum(p.numel() for p in model.parameters()),data_hashes=hashes,rows={s:len(d[0]) for s,d in data.items()},
        source_resume=str(args.resume) if args.resume else None,best_dev_nll=best,
        gpu_peak_MiB=torch.cuda.max_memory_allocated()/2**20,seconds=time.monotonic()-start,packed=packed,events=events,
        data_directory=str(root),optimizer_resumed=False,vocab=core.V,context=core.T,bpe=args.bpe,intent_aux_weight=args.intent_aux,expanded_last=args.expand_last,
        semantic_projection=str(args.semantic_projection) if args.semantic_projection else None,semantic_weight=args.semantic_weight if semantic is not None else 0,
        warning='Source corpus specified by data_directory; may be human dialogue, language text or teacher-derived text. Loss improvement is not conversation quality. Final test excluded. No automatic device deployment.')
    (args.out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='events'}),flush=True)
if __name__=='__main__':main()
