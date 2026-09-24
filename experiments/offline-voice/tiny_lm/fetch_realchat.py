"""Fetch masked public dialogue text only; do not load speaker/personality data."""
import hashlib
import io
import json
from pathlib import Path
import tarfile
import requests
ROOT=Path(__file__).resolve().parents[1]
REV='28d0b6b3865b29cabc26c230a2db37cdf315e937'
def main():
    root=ROOT/'.cache/realchat';root.mkdir(exist_ok=True)
    url=f'https://codeload.github.com/nu-dialogue/real-persona-chat/tar.gz/{REV}'
    r=requests.get(url,timeout=120);r.raise_for_status();blob=r.content
    rows=[];license_text=None
    # Never extract paths or execute the HF loading script. Read JSON members only.
    with tarfile.open(fileobj=io.BytesIO(blob),mode='r:gz') as tar:
        for member in tar:
            if not member.isfile():continue
            if member.name.endswith('/LICENSE'):license_text=tar.extractfile(member).read().decode()
            if '/real_persona_chat/dialogues/' not in member.name or not member.name.endswith('.json'):continue
            obj=json.load(tar.extractfile(member))
            # Discard participant IDs, demographics, personality, timestamps and scores.
            rows.append(dict(dialogue_id=obj['dialogue_id'],utterances=[m['text'] for m in obj['utterances']]))
    if not license_text or not rows:raise ValueError('Missing license or data')
    (root/'LICENSE').write_text(license_text)
    (root/'dialogues.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in sorted(rows,key=lambda x:x['dialogue_id'])))
    manifest=dict(source='nu-dialogue/real-persona-chat',revision=REV,url=url,
        archive_sha256=hashlib.sha256(blob).hexdigest(),license='CC-BY-SA-4.0',dialogues=len(rows),
        authors='Sanae Yamashita, Koji Inoue, Ao Guo, Shota Mochizuki, Tatsuya Kawahara, Ryuichiro Higashinaka',
        restrictions='Do not identify participants or impersonate individual speakers. No speaker metadata retained. Local research; publication requires attribution and share-alike review.')
    (root/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(manifest,flush=True)
if __name__=='__main__':main()
