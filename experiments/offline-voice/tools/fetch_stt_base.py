"""Fetch only the pinned STT base, not the unlicensed example-audio dataset."""
import argparse
import hashlib
import json
from pathlib import Path
from huggingface_hub import hf_hub_download
ROOT=Path(__file__).resolve().parents[1]
REPO='moonshine-ai/moonshine-tiny-ja'
REV='02ca41b3d9e73db07df9a13f316f2b7497a368e2'
def main():
    p=argparse.ArgumentParser();p.add_argument('--accept-community-license',action='store_true');args=p.parse_args()
    if not args.accept_community_license:p.error('Read licenses/Moonshine-Community-LICENSE.txt and the upstream AUP first')
    out=ROOT/'.cache/model';manifest=[]
    for name in ('config.json','model.safetensors','LICENSE.txt','README.md'):
        path=Path(hf_hub_download(REPO,name,revision=REV,token=False,local_dir=out))
        manifest.append({'name':name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size})
    (out/'source.json').write_text(json.dumps({'repo':REPO,'revision':REV,'files':manifest},indent=2)+'\n')
if __name__=='__main__':main()
