"""Human Japanese conversational pairs; deterministic dialogue-disjoint split."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import time
import numpy as np
from dialogue_data import ROOT,Kana,BLOCK
from data import encode

def main():
    root=ROOT/'.cache/realchat';convert=Kana();rows={s:[] for s in ('train','dev','test')};counts=Counter();seen=set();start=time.monotonic()
    language={'train':[],'dev':[]}
    for index,line in enumerate((root/'dialogues.jsonl').read_text().splitlines()):
        conv=json.loads(line);key=hashlib.sha256(('realchat:'+str(conv['dialogue_id'])).encode()).hexdigest()
        bucket=int(key[:8],16)%100;split='train' if bucket<90 else 'dev' if bucket<95 else 'test'
        texts=conv['utterances'];kanas=[]
        for text in texts:
            try:
                if not 3<=len(text)<=100 or re.search(r'[●■＊*]|MASK|非公開',text):raise ValueError('masked or long')
                kana=convert(text)
                if split!='test':
                    ids=encode(kana)
                    for off in range(0,len(ids),126):
                        chunk=ids[off:off+126]
                        if len(chunk)<6:continue
                        r=[1]+chunk+[3];language[split].append(r+[0]*(128-len(r)))
                kanas.append(kana)
            except (ValueError,KeyError):kanas.append(None);counts['reading_or_mask_rejected']+=1
        for turn in range(len(texts)-1):
            q,a=kanas[turn:turn+2]
            if not q or not a or not 4<=len(q)<=80 or not 4<=len(a)<=40 or len(q)+len(a)+3>128:continue
            # Keep one-turn inputs in v1: previous context is not secretly supplied.
            # Context-dependent responses remain a documented source of noise.
            if q in seen:counts['duplicate_question']+=1;continue
            seen.add(q)
            rows[split].append(dict(id=key+f':{turn}',group=key,split=split,
                question=texts[turn],answer=texts[turn+1],question_kana=q,answer_kana=a))
        if index%2000==0:print(json.dumps(dict(dialogues=index,seconds=round(time.monotonic()-start),pairs=sum(map(len,rows.values())))),flush=True)
    for split,data in rows.items():(root/f'{split}.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in data))
    for split,data in language.items():np.save(root/f'language-{split}.npy',np.array(data,dtype=np.uint8))
    report=dict(**counts,pairs={s:len(r) for s,r in rows.items()},language_rows={s:len(r) for s,r in language.items()},seconds=time.monotonic()-start,
        warning='Dialogue-disjoint, NOT speaker/topic-disjoint. No speaker attributes used. One-turn adjacent-pair extraction can lose context. Human replies are not assistant factual ground truth.',license='CC-BY-SA-4.0')
    (root/'prepared.json').write_text(json.dumps(report,indent=2)+'\n');print(report,flush=True)
if __name__=='__main__':main()
