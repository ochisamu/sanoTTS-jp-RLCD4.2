"""Fetch only the Japanese training/development splits, never all languages."""
import hashlib
import json
from pathlib import Path
from benchmark import ROOT
from huggingface_hub import hf_hub_download

REV='70bb2e84b976b7e960aa89f1c648e09c59f894dd'
EXPECTED={'train':'74c0f2455b71cac7a9aaa4474f93df1d773d545d9f9ef56fc21dc30a8c42ea52',
          'validation':'4636065a2eb7d1bb07007d3193092eb1856cf101360831c61d6dfa611e579071'}

if __name__=='__main__':
    dest=ROOT/'.cache/fleurs'
    paths=[]
    for split, sha in EXPECTED.items():
        name=f'parquet-data/ja_jp/{split}-00000-of-00001.parquet'
        path=Path(hf_hub_download('google/fleurs', name, repo_type='dataset', revision=REV,
                                 token=False, local_dir=dest))
        digest=hashlib.file_digest(path.open('rb'),'sha256').hexdigest()
        if digest!=sha:
            raise RuntimeError('Dataset integrity check failed')
        paths.append({'file':name,'sha256':digest,'bytes':path.stat().st_size})
        print(split,'verified',flush=True)
    hf_hub_download('google/fleurs','README.md',repo_type='dataset',revision=REV,token=False,local_dir=dest)
    (dest/'manifest.json').write_text(json.dumps({'repo':'google/fleurs','revision':REV,'license':'CC-BY-4.0','files':paths},indent=2))
