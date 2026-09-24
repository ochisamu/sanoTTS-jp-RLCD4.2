"""Pinned public assets for local-only dialogue distillation. No remote code."""
import hashlib
import json
import os
from pathlib import Path
os.environ.setdefault('HF_HUB_DISABLE_XET','1')
from huggingface_hub import snapshot_download
ROOT=Path(__file__).resolve().parents[1]
ASSETS=[('model','Qwen/Qwen3-4B-Instruct-2507','cdbee75f17c01a7cc42f958dc650907174af0554','teacher'),
        ('dataset','llm-jp/oasst1-21k-ja','f05b5816a8c1ce8c1f5ae3cd87ae5a7b6409fea5','oasst')]
def main():
    root=ROOT/'.cache/dialogue';root.mkdir(exist_ok=True);manifest=[]
    for kind,name,revision,folder in ASSETS:
        print('fetch',name,revision,flush=True)
        dest=root/folder
        snapshot_download(name,repo_type=kind,revision=revision,token=False,local_dir=dest,
            allow_patterns=['*.safetensors','*.json','*.jsonl','*.txt','*.md','LICENSE','merges.txt'],max_workers=3)
        files=[]
        for p in sorted(dest.iterdir()):
            if not p.is_file():continue
            h=hashlib.sha256()
            with p.open('rb') as f:
                for chunk in iter(lambda:f.read(8*1024*1024),b''):h.update(chunk)
            files.append(dict(name=p.name,bytes=p.stat().st_size,sha256=h.hexdigest()))
        manifest.append(dict(repo=name,revision=revision,kind=kind,declared_license='Apache-2.0',files=files))
        (root/'assets.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('assets ready',flush=True)
if __name__=='__main__':main()
