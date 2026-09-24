"""Train-only kana BPE and arrays for a host-only feasibility experiment.

Does not read final test, export a firmware model or alter the device.
Corpus terms remain applicable: see licenses/dialogue-data-NOTICE.md.
"""
import hashlib
import json
from pathlib import Path
import numpy as np
from tokenizers import Tokenizer, Regex
from tokenizers.models import BPE
from tokenizers.trainers import BpeTrainer
from tokenizers.pre_tokenizers import Split
from data import CHARS, decode

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'.cache/bpe-dialogue'
T=96

def dialogue_row(tok,question,answer):
    q=[1]+tok.encode(question).ids+[2];a=tok.encode(answer).ids+[3]
    if len(q+a)>T:raise ValueError('Too long')
    if 4 in q+a:raise ValueError('Unknown token')
    return q+a+[0]*(T-len(q+a)),[-100]*(len(q)-1)+a+[-100]*(T-len(q+a))

def text_rows(split):
    for source in ('dialogue','realchat'):
        raw=np.load(ROOT/f'.cache/{source}/language-{split}.npy')
        for row in raw:yield decode(row)

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    if (OUT/'manifest.json').exists():raise FileExistsError('Prepared data already exists')
    tok=Tokenizer(BPE(unk_token='<unk>'))
    tok.pre_tokenizer=Split(Regex('[。、！？]'),behavior='isolated')
    tok.train_from_iterator(text_rows('train'),BpeTrainer(vocab_size=1024,min_frequency=12,
        initial_alphabet=list(CHARS),special_tokens=['<pad>','<bos>','<sep>','<eos>','<unk>'],max_token_length=12))
    assert [tok.token_to_id(s) for s in ['<pad>','<bos>','<sep>','<eos>','<unk>']]==list(range(5))
    tok.save(str(OUT/'tokenizer.json'))
    counts={};hashes={};characters=0;tokens=0
    def pack(rows):
        return np.array([r+[0]*(T-len(r)) for r in rows],dtype=np.uint16)
    for split in ('train','dev'):
        rows=[]
        for s in text_rows(split):
            ids=tok.encode(s).ids
            assert 4 not in ids
            if split=='train':characters+=len(s);tokens+=len(ids)
            for off in range(0,len(ids),T-2):rows.append([1]+ids[off:off+T-2]+[3])
        path=OUT/f'language-{split}.npy';np.save(path,pack(rows));counts[path.name]=len(rows)
        rows=[];labels=[]
        source=ROOT/f'.cache/realchat/{split}.jsonl'
        hashes[str(source.relative_to(ROOT))]=hashlib.sha256(source.read_bytes()).hexdigest()
        for line in source.read_text().splitlines():
            r=json.loads(line)
            try:row,label=dialogue_row(tok,r['question_kana'],r['answer_kana'])
            except ValueError:continue
            rows.append(row);labels.append(label)
        path=OUT/f'dialogue-{split}.npy';np.save(path,pack(rows));counts[path.name]=len(rows)
        np.save(OUT/f'labels-{split}.npy',np.array(labels,dtype=np.int16))
    report=dict(vocab=tok.get_vocab_size(),context=T,counts=counts,source_hashes=hashes,
        train_characters=characters,train_tokens=tokens,chars_per_token=characters/tokens,
        tokenizer_sha256=hashlib.sha256((OUT/'tokenizer.json').read_bytes()).hexdigest(),
        warning='Host-only BPE experiment; final test not read. Human conversation is context dependent. CC-BY-SA-4.0 applies to RealPersonaChat derivatives.')
    (OUT/'manifest.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)

if __name__=='__main__':main()
