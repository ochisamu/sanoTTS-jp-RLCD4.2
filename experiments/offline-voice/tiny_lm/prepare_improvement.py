"""Build replay + original contrastive SFT, captions and local knowledge assets.

Generated tables/weights stay outside Git. Retains all parent corpus terms.
"""
import hashlib,json,shutil
from pathlib import Path
import numpy as np
from tokenizers import Tokenizer
from dialogue_data import ROOT,Kana
from prepare_bpe import dialogue_row
from improvement_data import CASES
from knowledge_data import CARDS

def main():
    out=ROOT/'.cache/improvement-bpe';out.mkdir(exist_ok=True)
    if (out/'manifest.json').exists():raise FileExistsError('Prepared experiment already exists')
    convert=Kana();base=ROOT/'.cache/daily-aug-bpe'
    train=[json.loads(s) for s in (base/'train.jsonl').read_text().splitlines()]
    dev=[json.loads(s) for s in (base/'dev.jsonl').read_text().splitlines()]
    old_dev={r['question_kana'] for r in dev};seen={r['question_kana']:r['answer_kana'] for r in train}
    extra=[];knowledge=[]
    families=list(CASES)+[(r['id'],r['questions'],r['dev'],r['answer']) for r in CARDS]
    for name,questions,held,answer in families:
        a=convert(answer)
        for split,items in [('train',questions.split('|')),('dev',held.split('|'))]:
            for q in items:
                k=convert(q)
                row=dict(group='v2_'+name,question=q,question_kana=k,answer=answer,answer_kana=a,source='Original assistant-authored v2 seeds, MIT')
                if split=='dev':
                    if k in seen:raise ValueError(('train/dev overlap',q))
                    dev.append(row);continue
                if k in old_dev:raise ValueError(('old dev overlap',q))
                if k in seen and seen[k]!=a:raise ValueError(('conflicting training answer',q))
                extra.append(row)
        if name in {r['id'] for r in CARDS}:
            knowledge.append(dict(id=name,aliases=[convert(q) for q in questions.split('|')],display=answer,reading=a))
    # Balance new families against the existing 24 prefix/suffix variants. Exact
    # repetition weights the loss; it is NOT counted as new independent examples.
    held={r['question_kana'] for r in dev}
    for r in extra:
        for prefix in ('','ねえ。','あのね。','ちょっときいて。'):
            k=prefix+r['question_kana']
            if k in held:raise ValueError('Augmented dev overlap')
            train.extend([{**r,'question_kana':k}]*6)
    tokpath=base/'tokenizer.json';tok=Tokenizer.from_file(str(tokpath));shutil.copyfile(tokpath,out/'tokenizer.json')
    for split,rows in [('train',train),('dev',dev)]:
        (out/f'{split}.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))
        pairs=[dialogue_row(tok,r['question_kana'],r['answer_kana']) for r in rows]
        np.save(out/f'dialogue-{split}.npy',np.array([p[0] for p in pairs],dtype=np.uint16))
        np.save(out/f'labels-{split}.npy',np.array([p[1] for p in pairs],dtype=np.int16))
    (out/'knowledge.json').write_text(json.dumps(knowledge,ensure_ascii=False,indent=2)+'\n')
    # Exact whole-answer mapping only. Ambiguous readings keep kana.
    captions={};conflicts=set()
    for r in train:
        k=r['answer_kana'].replace('。','').replace('、','')
        if k in captions and captions[k]!=r['answer']:conflicts.add(k)
        captions[k]=r['answer']
    for k in conflicts:captions.pop(k)
    (out/'captions.json').write_text(json.dumps(captions,ensure_ascii=False,indent=2)+'\n')
    report=dict(train_rows=len(train),dev_rows=len(dev),new_independent_train_questions=len(extra),new_families=len(families),knowledge_cards=len(knowledge),caption_answers=len(captions),ambiguous_captions=len(conflicts),
        sources={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [base/'train.jsonl',base/'dev.jsonl',ROOT/'tiny_lm/improvement_data.py',ROOT/'tiny_lm/knowledge_data.py',tokpath]},
        warning='Development wordings within known families, not unseen-topic accuracy. Replayed parent model/corpus license restrictions still apply. No user audio or transcripts used.')
    (out/'manifest.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)
if __name__=='__main__':main()
