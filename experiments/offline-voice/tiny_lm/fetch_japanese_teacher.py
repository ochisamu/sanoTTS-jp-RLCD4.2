"""Pinned Japanese teacher, local training use only; never downloaded code."""
import hashlib
import json
import os
from pathlib import Path
os.environ.setdefault('HF_HUB_DISABLE_XET','1')
from huggingface_hub import snapshot_download
ROOT=Path(__file__).resolve().parents[1]
REPO='sbintuitions/sarashina2.2-3b-instruct-v0.1'
REVISION='4f3626fb1b64b3e97c908e67f27b2d627ba2a999'

def main():
    dest=ROOT/'.cache/japanese-teacher'
    snapshot_download(REPO,revision=REVISION,token=False,local_dir=dest,
        allow_patterns=['*.safetensors','*.json','*.model','README.md','LICENSE'],max_workers=2)
    files=[]
    for p in sorted(dest.iterdir()):
        if not p.is_file() or p.name=='manifest.json':continue
        h=hashlib.sha256()
        with p.open('rb') as f:
            for chunk in iter(lambda:f.read(8*1024*1024),b''):h.update(chunk)
        files.append(dict(name=p.name,bytes=p.stat().st_size,sha256=h.hexdigest()))
    (dest/'manifest.json').write_text(json.dumps(dict(repo=REPO,revision=REVISION,license='MIT',files=files),indent=2)+'\n')
    print('Japanese teacher downloaded and hashed',flush=True)

if __name__=='__main__':main()
