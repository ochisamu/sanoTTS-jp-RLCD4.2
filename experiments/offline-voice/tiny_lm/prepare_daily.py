"""Reviewed-seed adaptation; no generated teacher replies are included."""
import json
import hashlib
from collections import Counter
import numpy as np
from tokenizers import Tokenizer
from dialogue_data import ROOT,Kana
from daily_dialogue import CASES
from data import CASES as OLD
from prepare_bpe import dialogue_row,T

def main():
    convert=Kana();train=[];dev=[];seen={};conflicts=[]
    families=list(CASES)
    for name,questions,held,answers in OLD:
        if name in ('unknown','like'):continue
        families.append(('original_'+name,questions,held,answers.split('|')[0]))
    for name,questions,held,answer in families:
        a=convert(answer)
        if len(a)>44:raise ValueError((name,'answer too long',a))
        for split,items in [('train',questions.split('|')),('dev',held.split('|'))]:
            for q in items:
                normalized=convert(q)
                if normalized in seen:
                    conflicts.append(dict(question=q,existing=seen[normalized],skipped=name));continue
                seen[normalized]=name
                r=dict(id=hashlib.sha256((name+'|'+q).encode()).hexdigest(),group=name,split=split,
                    question=q,question_kana=normalized,answer=answer,answer_kana=a)
                (train if split=='train' else dev).append(r)
    base=len(train);augmented=[]
    for r in train:
        for prefix in ('','ねえ。','あのね。'):
            for suffix in ('','。'):
                q=prefix+r['question_kana']+suffix
                if len(q)+len(r['answer_kana'])+3>128:continue
                augmented.append({**r,'question_kana':q,'id':r['id']+':'+str(len(augmented))})
    assert not {r['question_kana'] for r in augmented}&{r['question_kana'] for r in dev}
    kana_root=ROOT/'.cache/daily-kana';bpe_root=ROOT/'.cache/daily-bpe'
    kana_root.mkdir(exist_ok=True);bpe_root.mkdir(exist_ok=True)
    tok_path=ROOT/'.cache/bpe-dialogue/tokenizer.json'
    tok=Tokenizer.from_file(str(tok_path));tok.save(str(bpe_root/'tokenizer.json'))
    for split,items in [('train',augmented),('dev',dev)]:
        raw=''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in items)
        (kana_root/f'{split}.jsonl').write_text(raw);(bpe_root/f'{split}.jsonl').write_text(raw)
        pairs=[dialogue_row(tok,r['question_kana'],r['answer_kana']) for r in items]
        np.save(bpe_root/f'dialogue-{split}.npy',np.array([r for r,l in pairs],dtype=np.uint16))
        np.save(bpe_root/f'labels-{split}.npy',np.array([l for r,l in pairs],dtype=np.int16))
    report=dict(semantic_families=len(families),base_train_questions=base,augmented_train_rows=len(augmented),
        dev_questions=len(dev),skipped_duplicate_questions=conflicts,source='Original reviewed seeds, MIT',
        source_sha256=hashlib.sha256((ROOT/'tiny_lm/daily_dialogue.py').read_bytes()).hexdigest(),
        warning='Dev holds out wordings, NOT intents/answers. Broader than 26 original families, not open-domain dialogue. Teacher pilots excluded. Pretrained checkpoints retain their corpus terms.')
    (kana_root/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    (bpe_root/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
