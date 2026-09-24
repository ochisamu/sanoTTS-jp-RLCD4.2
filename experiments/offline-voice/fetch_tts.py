"""Fetch sanoTTS model externally; code's MIT license does not cover weights."""
import argparse
import hashlib
import urllib.request
from benchmark import ROOT

URL='https://github.com/ayutaz/sanoTTS-jp/releases/download/v1.0.0/saanotts-jp-v4-int8.bin'
SHA='a1eb6b0812e2ad2a228836088a3e34160cb66731492fb957a5891605db2fa1b6'
if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--accept-model-license',action='store_true')
    args=parser.parse_args()
    if not args.accept_model_license:
        parser.error('Read third_party/sanoTTS-jp/LICENSE-MODEL.md and pass --accept-model-license')
    with urllib.request.urlopen(URL,timeout=60) as response:
        data=response.read(654033)
    if len(data)!=654032 or hashlib.sha256(data).hexdigest()!=SHA:
        raise RuntimeError('TTS model hash/size mismatch')
    path=ROOT/'.cache/tts-v4.bin'
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(data)
    print('Verified sanoTTS v4 int8: 654032 bytes')
