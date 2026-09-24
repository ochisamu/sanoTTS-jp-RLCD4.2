"""Cache local E5 semantic targets for training only. No runtime retrieval.

RealPersonaChat training/development splits only, never final test. All raw
text and vectors stay ignored. Corpus terms remain CC BY-SA 4.0.
"""
import hashlib
import json
import os
from pathlib import Path
import random
import time
import numpy as np
import torch
from torch.nn import functional as F
from transformers import AutoTokenizer,AutoModel
from tokenizers import Tokenizer
os.environ.setdefault('HF_HUB_DISABLE_XET','1')
from huggingface_hub import snapshot_download
ROOT=Path(__file__).resolve().parents[1]
REPO='intfloat/multilingual-e5-small'
REVISION='614241f622f53c4eeff9890bdc4f31cfecc418b3'

def main():
    root=ROOT/'.cache/semantic';root.mkdir(exist_ok=True);dest=root/'teacher'
    snapshot_download(REPO,revision=REVISION,token=False,local_dir=dest,
        allow_patterns=['model.safetensors','config.json','tokenizer.json','tokenizer_config.json','special_tokens_map.json','README.md'],max_workers=2)
    torch.set_num_threads(4)
    tok=AutoTokenizer.from_pretrained(dest,local_files_only=True,trust_remote_code=False)
    teacher=AutoModel.from_pretrained(dest,local_files_only=True,trust_remote_code=False,torch_dtype=torch.bfloat16,attn_implementation='sdpa').cuda().eval()
    student=Tokenizer.from_file(str(ROOT/'.cache/bpe-dialogue/tokenizer.json'))
    summaries={};start=time.monotonic()
    def embeddings(texts):
        result=[]
        with torch.inference_mode():
            for off in range(0,len(texts),128):
                x=tok(['query: '+s for s in texts[off:off+128]],return_tensors='pt',padding=True,truncation=True,max_length=128).to('cuda')
                h=teacher(**x).last_hidden_state.float();mask=x['attention_mask'].unsqueeze(-1)
                v=F.normalize((h*mask).sum(1)/mask.sum(1),dim=-1)
                result.append(v.cpu().numpy().astype(np.float16))
                if off%12800==0:print(json.dumps(dict(encoded=off+len(v),total=len(texts),seconds=round(time.monotonic()-start,1))),flush=True)
        return np.concatenate(result)
    for split,limit in [('train',60000),('dev',2000)]:
        rows=[json.loads(s) for s in (ROOT/f'.cache/realchat/{split}.jsonl').read_text().splitlines()]
        random.Random(8642).shuffle(rows);rows=rows[:limit]
        ids=[[1]+student.encode(r['question_kana']).ids+[2] for r in rows]
        assert all(4 not in seq and len(seq)<=96 for seq in ids)
        np.save(root/f'{split}-ids.npy',np.array([seq+[0]*(96-len(seq)) for seq in ids],dtype=np.uint16))
        np.save(root/f'{split}-vectors.npy',embeddings([r['question'] for r in rows]))
        summaries[split]=dict(rows=len(rows),ids_sha256=hashlib.sha256((root/f'{split}-ids.npy').read_bytes()).hexdigest())
    for split in ('train','dev'):
        rows=[json.loads(s) for s in (ROOT/f'.cache/daily-aug-bpe/{split}.jsonl').read_text().splitlines()]
        texts=list(dict.fromkeys(r['question'] for r in rows));mapping={s:i for i,s in enumerate(texts)}
        vectors=embeddings(texts)
        np.save(root/f'daily-{split}-vectors.npy',vectors[[mapping[r['question']] for r in rows]])
    files=[]
    for p in sorted(root.glob('*.npy')):
        files.append(dict(name=p.name,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size))
    (root/'manifest.json').write_text(json.dumps(dict(teacher=REPO,revision=REVISION,declared_teacher_license='MIT',splits=summaries,files=files,
        warning='Teacher and targets are training-only. No test read. Human corpus derivatives remain CC-BY-SA-4.0. query prefix, masked mean pooling, normalized 384D vectors. Tokenizer truncates teacher input at 128 tokens.'),indent=2)+'\n')
    print('semantic targets ready',flush=True)

if __name__=='__main__':main()
