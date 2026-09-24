"""PC-only diagnostic of locally captured RLCD microphone audio."""
import argparse
import json
import numpy as np
import soundfile as sf
import torch
from transformers import AutoProcessor, MoonshineForConditionalGeneration
from benchmark import ROOT


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('wav')
    args=parser.parse_args()
    audio,sr=sf.read(args.wav,dtype='float32',always_2d=True)
    if sr!=16000:
        raise ValueError('Expected 16kHz audio')
    centered=audio-audio.mean(axis=0)
    rms=np.sqrt(np.mean(centered**2,axis=0))
    channel=int(np.argmax(rms))
    mono=centered[:,channel]
    gain=min(20.0,0.05/max(float(rms[channel]),1e-6),0.9/max(float(np.abs(mono).max()),1e-6))
    processor=AutoProcessor.from_pretrained(ROOT/'.cache/model',local_files_only=True)
    model=MoonshineForConditionalGeneration.from_pretrained(ROOT/'.cache/model',local_files_only=True).cuda().eval()
    inputs=processor(mono*gain,sampling_rate=sr,return_tensors='pt').to('cuda')
    with torch.inference_mode():
        ids=model.generate(**inputs,max_new_tokens=100,do_sample=False)
    print(json.dumps({'diagnostic':'PC inference, NOT ESP32 STT','rms':rms.tolist(),'selected_channel':channel,
        'diagnostic_gain':gain,'text':processor.batch_decode(ids,skip_special_tokens=True)[0]},ensure_ascii=False))
