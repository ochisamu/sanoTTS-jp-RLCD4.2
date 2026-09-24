"""Pretrained Moonshine encoder + new phoneme CTC head; research only."""
import torch
from torch import nn
from transformers import MoonshineForConditionalGeneration
from benchmark import ROOT

PHONES=['<blank>']+'a i u e o N cl pau k ky kw g gy gw s sh z j t ty ch ts d dy n ny h hy f b by p py m my y r ry w v'.split()


def phones(text):
    import pyopenjtalk
    return [p.lower() if p in ('A','I','U','E','O') else p for p in pyopenjtalk.g2p(text).split()]


def frames(length):
    return (((length-127)//64+1-7)//3+1-3)//2+1


class PhonemeCTC(nn.Module):
    def __init__(self, keep=(0,2,4)):
        super().__init__()
        base=MoonshineForConditionalGeneration.from_pretrained(ROOT/'.cache/model',local_files_only=True)
        self.encoder=base.model.encoder
        self.encoder.layers=nn.ModuleList([self.encoder.layers[i] for i in keep])
        self.encoder.config.encoder_num_hidden_layers=len(keep)
        self.head=nn.Linear(288,len(PHONES))

    def forward(self,audio):
        return self.head(self.encoder(input_values=audio).last_hidden_state)


def decode(ids):
    result=[]
    last=-1
    for token in ids:
        token=int(token)
        if token and token!=last:
            result.append(token)
        last=token
    return result
