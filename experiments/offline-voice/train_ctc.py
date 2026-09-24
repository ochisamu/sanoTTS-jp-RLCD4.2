"""Bounded training runs with dev PER; no claims of MCU-ready inference."""
import argparse
import json
import random
import time
import numpy as np
import torch
from safetensors.torch import save_file, load_file
from benchmark import ROOT, edit_distance
from ctc import PhonemeCTC, PHONES, decode


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--steps',type=int,default=1200)
    parser.add_argument('--resume',action='store_true')
    parser.add_argument('--eval-count',type=int,default=64)
    parser.add_argument('--layers',type=int,choices=(3,6),default=3)
    parser.add_argument('--name',default='ctc')
    args=parser.parse_args()
    random.seed(42); np.random.seed(42); torch.manual_seed(42)
    torch.set_num_threads(4)
    keep=(0,2,4) if args.layers==3 else tuple(range(6))
    model=PhonemeCTC(keep=keep).cuda()
    checkpoint=ROOT/'.cache'/args.name
    checkpoint.mkdir(exist_ok=True)
    if args.resume:
        model.load_state_dict(load_file(str(checkpoint/'latest.safetensors')))
    optimizer=torch.optim.AdamW([{'params':model.encoder.parameters(),'lr':1e-4},
                                {'params':model.head.parameters(),'lr':1e-3}],weight_decay=0.01)
    loss_fn=torch.nn.CTCLoss(blank=0,zero_infinity=False)
    datasets={s:json.loads((ROOT/f'.cache/prepared/{s}/index.json').read_text()) for s in ('train','validation')}
    overlap={e['text_sha256'] for e in datasets['train']} & {e['text_sha256'] for e in datasets['validation']}
    if overlap:
        raise RuntimeError('Train/dev text overlap detected')
    valid=random.Random(43).sample(datasets['validation'],min(args.eval_count,len(datasets['validation'])))
    def load(split,entry):
        with np.load(ROOT/f'.cache/prepared/{split}'/entry['file'],allow_pickle=False) as f:
            return torch.from_numpy(f['audio']).unsqueeze(0).cuda(),torch.from_numpy(f['labels']).cuda()
    def evaluate():
        model.eval(); errors=total=0; predictions=[]
        with torch.inference_mode():
            for entry in valid:
                audio,label=load('validation',entry)
                with torch.autocast('cuda',dtype=torch.bfloat16):
                    logits=model(audio)
                pred=decode(logits[0].argmax(-1).tolist()); ref=label.tolist()
                errors+=edit_distance(ref,pred); total+=len(ref)
                predictions.append({'file':entry['file'],'reference':[PHONES[i] for i in ref],
                                    'prediction':[PHONES[i] for i in pred]})
        (checkpoint/'dev_predictions.json').write_text(json.dumps(predictions,ensure_ascii=False))
        model.train()
        return errors/max(1,total)
    report={'seed':42,'parameters':sum(p.numel() for p in model.parameters()),
        'train_utterances':len(datasets['train']),'dev_utterances':len(valid),
        'device':torch.cuda.get_device_name(),'resume_weights_only_optimizer_reset':args.resume,
        'warning':'Dev set, not independent final test. Labels are automatic phonemes. No ESP32 inference yet.',
        'events':[]}
    def event(value):
        report['events'].append(value)
        print(json.dumps(value),flush=True)
        (ROOT/'results'/f'{args.name}_training.json').write_text(json.dumps(report,indent=2))
    best_per=evaluate()
    event({'step':0,'dev_PER':best_per})
    start=time.perf_counter(); torch.cuda.reset_peak_memory_stats()
    order=list(range(len(datasets['train']))); random.shuffle(order); cursor=0
    average=0; optimizer.zero_grad(set_to_none=True)
    for step in range(1,args.steps+1):
        for micro in range(4):
            if cursor>=len(order):
                random.shuffle(order); cursor=0
            entry=datasets['train'][order[cursor]]; cursor+=1
            audio,label=load('train',entry)
            # Modest random gain; no padded groupnorm statistics (batch=1).
            audio=audio*random.uniform(0.7,1.3)
            with torch.autocast('cuda',dtype=torch.bfloat16):
                logits=model(audio)
            log_probs=logits.float().log_softmax(-1).transpose(0,1)
            loss=loss_fn(log_probs,label,torch.tensor([logits.shape[1]]),torch.tensor([len(label)]))
            if not torch.isfinite(loss):
                raise RuntimeError('Non-finite CTC loss')
            (loss/4).backward(); average+=float(loss.detach())/4
        torch.nn.utils.clip_grad_norm_(model.parameters(),1.0)
        optimizer.step(); optimizer.zero_grad(set_to_none=True)
        if step%25==0:
            event({'step':step,'loss':average/25,'elapsed_seconds':time.perf_counter()-start,
                   'peak_allocated_MiB':torch.cuda.max_memory_allocated()/2**20})
            average=0
        if step%200==0 or step==args.steps:
            per=evaluate()
            save_file({k:v.detach().cpu().contiguous() for k,v in model.state_dict().items()},str(checkpoint/'latest.safetensors'))
            if per<best_per:
                best_per=per
                save_file({k:v.detach().cpu().contiguous() for k,v in model.state_dict().items()},str(checkpoint/'best.safetensors'))
            event({'step':step,'dev_PER':per})
    (checkpoint/'config.json').write_text(json.dumps({'vocabulary':PHONES,'layers':list(keep),
        'base_revision':'02ca41b3d9e73db07df9a13f316f2b7497a368e2','source_license':'Moonshine AI Community License'}))


if __name__=='__main__':
    main()
