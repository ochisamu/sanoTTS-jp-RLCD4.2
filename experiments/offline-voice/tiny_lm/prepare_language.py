"""Kana next-token pretraining from pinned OASST training source families only."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import time
import numpy as np
from dialogue_data import ROOT, Kana, group_key, BLOCK
from data import encode

def main():
    root=ROOT/'.cache/dialogue';convert=Kana();rows={'train':[],'dev':[]};seen=set();counts=Counter();start=time.monotonic()
    for index,line in enumerate((root/'oasst/oasst1-21k-ja.jsonl').read_text().splitlines()):
        conv=json.loads(line)['conversations'];group=group_key(conv);bucket=int(group[:8],16)%100
        if bucket>=95:continue # do not prepare final-test language data
        split='train' if bucket<90 else 'dev'
        for message in conv:
            # Keep short natural-language spans, not code blocks, URLs or tables.
            for sentence in re.split(r'[。！？\n]',message['value']):
                sentence=sentence.strip()
                if not 6<=len(sentence)<=180 or BLOCK.search(sentence):continue
                key=hashlib.sha256(sentence.encode()).hexdigest()
                if key in seen:continue
                seen.add(key)
                try:ids=encode(convert(sentence))
                except (ValueError,KeyError):counts['conversion_rejected']+=1;continue
                # Fixed 128 positions, no inter-sentence continuation assumption.
                for off in range(0,len(ids),126):
                    chunk=ids[off:off+126]
                    if len(chunk)<6:continue
                    row=[1]+chunk+[3];rows[split].append(row+[0]*(128-len(row)))
                    counts[split+'_tokens']+=len(chunk)
        if index%2000==0:print(json.dumps(dict(source_rows=index,seconds=round(time.monotonic()-start),**counts)),flush=True)
    for split,data in rows.items():np.save(root/f'language-{split}.npy',np.array(data,dtype=np.uint8))
    report=dict(**counts,rows={s:len(v) for s,v in rows.items()},seconds=time.monotonic()-start,
                source='llm-jp/oasst1-21k-ja',revision='f05b5816a8c1ce8c1f5ae3cd87ae5a7b6409fea5',
                warning='Automatic readings. Source-family split; no final-test text. Deduplicated text spans. Not a Japanese fluency benchmark.')
    (root/'language-summary.json').write_text(json.dumps(report,indent=2)+'\n');print(report,flush=True)
if __name__=='__main__':main()
