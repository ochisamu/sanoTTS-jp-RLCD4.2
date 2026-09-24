"""Create local phoneme labels. Source audio/text are never added to Git."""
import hashlib
import io
import json
from pathlib import Path
import numpy as np
import pyarrow.parquet as pq
import soundfile as sf
from benchmark import ROOT
from ctc import PHONES, phones, frames


def main():
    vocab={p:i for i,p in enumerate(PHONES)}
    summary={}
    for split in ('train','validation'):
        source=ROOT/f'.cache/fleurs/parquet-data/ja_jp/{split}-00000-of-00001.parquet'
        dest=ROOT/f'.cache/prepared/{split}'
        dest.mkdir(parents=True,exist_ok=True)
        entries=[]; skipped={}; count=0
        for batch in pq.ParquetFile(source).iter_batches(batch_size=16):
            for row in batch.to_pylist():
                index=count; count+=1
                audio,sr=sf.read(io.BytesIO(row['audio']['bytes']),dtype='float32')
                if sr!=16000 or audio.ndim!=1:
                    raise ValueError('Unexpected audio format')
                if not 1<=len(audio)/sr<=18:
                    skipped['duration']=skipped.get('duration',0)+1; continue
                text=row['raw_transcription']
                label=phones(text)
                unknown=set(label)-set(vocab)
                if unknown:
                    raise ValueError(f'Unknown phonemes: {unknown}')
                needed=len(label)+sum(a==b for a,b in zip(label,label[1:]))
                if not label or needed>frames(len(audio)):
                    skipped['ctc_length']=skipped.get('ctc_length',0)+1; continue
                filename=f'{index:05d}.npz'
                np.savez(dest/filename,audio=audio,labels=np.array([vocab[p] for p in label],dtype=np.int64))
                entries.append({'file':filename,'samples':len(audio),'label_length':len(label),
                    'text_sha256':hashlib.sha256(text.encode()).hexdigest()})
                if len(entries)%250==0:
                    print(split,len(entries),'prepared',flush=True)
        (dest/'index.json').write_text(json.dumps(entries))
        summary[split]={'rows_total':count,'kept':len(entries),'skipped':skipped,
                        'hours':sum(e['samples'] for e in entries)/16000/3600}
    summary['labels']='pyopenjtalk 0.4.1 automatic phonemes, not manually verified'
    summary['vocabulary']=PHONES
    (ROOT/'results/data_preparation.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary),flush=True)


if __name__=='__main__':
    main()
