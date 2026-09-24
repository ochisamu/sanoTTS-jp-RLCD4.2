"""Apply an explicit assistant-reviewed question-only augmentation selection.

Selection is tied to the cached pilot's SHA, never silently reused on new text.
The answer strings come only from reviewed authored seeds. Dev is unchanged.
"""
import argparse
from collections import Counter
import hashlib
import json
import shutil
import numpy as np
from tokenizers import Tokenizer
from dialogue_data import ROOT,Kana
from prepare_bpe import dialogue_row

# Zero-based indices after manually inspecting all 114 generated family rows.
SELECT={
 'indoor':[0,1,5],'cooking':[0,1,2,3,5],'sweets':[0,1,4,5],
 'spill':[0,1,2,3,5],'shopping':[1,2,3,4,5],'cleaning':[0,1,2,3,5],
 'tidy':[0,2,5],'lost_key':[1,3],'found':[1,4,5],'shoes':[0,1,4,5],
 'commute':[0,2,3,4,5],'train_wait':[0,2,3],'walk':[0,1,3],
 'travel':[0,2,3,4],'sea':[0,1,3,4,5],'mountain':[0,1,2,3,4],
 'dog':[0,1,2,3,5],'rainbow':[0,2,3,4],'music':[0,1,2,3],'song':[1,5],
 'instrument':[0,1,2,3,5],'instrument_done':[0,1,4,5],
 'film':[0,1,2,4,5],'book_done':[0,1,2,3,5],'game':[0,1,2,3],
 'craft':[0,1],'study_done':[0,1,2,3,5],'holiday':[1,2,4,5],
 'friend':[0,1,3,5],'challenge':[0,1,2],'practice':[0,3,5],
 'sleep_done':[0,1,3,4,5],'wake':[0,1,3,4],'robot_eat':[1],
 'robot_move':[1,3,5],'robot_home':[0,1,2,3,5],
 'original_tired':[0,1,4,5],'original_thirsty':[0,2],'original_angry':[0,1,2,3,4],
}
PREFIXES=['','ねえ。','あのね。','そういえば。','ちょっときいてほしいんだけど。','ひとつはなしたいことがあるんだけど。','いまちょっといいかな。','はなしをきいてもらえるとうれしいな。']
SUFFIXES=['','。','。はなしをきいてくれる']

def main():
    p=argparse.ArgumentParser();p.add_argument('--reviewed-sha256',required=True);args=p.parse_args()
    source=ROOT/'.cache/daily-paraphrase/teacher.jsonl';digest=hashlib.sha256(source.read_bytes()).hexdigest()
    if digest!=args.reviewed_sha256:raise ValueError('Review applies to a different teacher artifact')
    base=ROOT/'.cache/daily-kana';dev=[json.loads(s) for s in (base/'dev.jsonl').read_text().splitlines()]
    held={r['question_kana'] for r in dev};rows=[];seen=set();families={};reject=Counter();convert=Kana()
    for s in (base/'train.jsonl').read_text().splitlines():
        r=json.loads(s)
        families.setdefault(r['group'],r)
        q=convert(r['question'])
        if q in seen:continue
        seen.add(q);rows.append({**r,'question_kana':q})
    accepted=[]
    for s in source.read_text().splitlines():
        r=json.loads(s)
        if 'questions' not in r:reject['invalid teacher schema']+=1;continue
        for i,q in enumerate(r['questions']):
            if i not in SELECT.get(r['group'],range(len(r['questions']))):reject['manual semantic/grammar rejection']+=1;continue
            try:kana=convert(q)
            except (ValueError,KeyError):reject['reading']+=1;continue
            if kana in held:reject['exact dev overlap']+=1;continue
            if kana in seen:reject['duplicate']+=1;continue
            seen.add(kana);item={**families[r['group']],'question':q,'question_kana':kana,
                'id':hashlib.sha256((r['group']+'|'+q).encode()).hexdigest(),'source':'manually reviewed teacher paraphrase'}
            rows.append(item);accepted.append(item)
    augmented=[];seen=set()
    for r in rows:
        for prefix in PREFIXES:
            for suffix in SUFFIXES:
                q=prefix+r['question_kana']+suffix
                if q in held or q in seen or len(q)>80 or len(q)+len(r['answer_kana'])+3>128:continue
                seen.add(q);augmented.append({**r,'question_kana':q})
    kroot=ROOT/'.cache/daily-aug-kana';broot=ROOT/'.cache/daily-aug-bpe'
    for root in (kroot,broot):
        if (root/'manifest.json').exists():raise FileExistsError('Do not overwrite prepared experiment')
        root.mkdir(exist_ok=True)
    tokpath=ROOT/'.cache/bpe-dialogue/tokenizer.json';tok=Tokenizer.from_file(str(tokpath));shutil.copyfile(tokpath,broot/'tokenizer.json')
    for split,items in [('train',augmented),('dev',dev)]:
        text=''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in items)
        (kroot/f'{split}.jsonl').write_text(text);(broot/f'{split}.jsonl').write_text(text)
        pairs=[dialogue_row(tok,r['question_kana'],r['answer_kana']) for r in items]
        np.save(broot/f'dialogue-{split}.npy',np.array([r for r,l in pairs],dtype=np.uint16))
        np.save(broot/f'labels-{split}.npy',np.array([l for r,l in pairs],dtype=np.int16))
    (kroot/'reviewed-paraphrases.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in accepted))
    report=dict(semantic_families=len(families),base_questions=len(rows),reviewed_teacher_additions=len(accepted),
        augmented_rows=len(augmented),dev_rows=len(dev),rejected=dict(reject),teacher_artifact_sha256=digest,
        warning='No additional topics or answers from teacher. Longer prefix/suffix augmentation is not independent semantic diversity. Dev remains known-intent wording dev, not open-domain/test.')
    for root in (kroot,broot):(root/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report),flush=True)

if __name__=='__main__':main()
