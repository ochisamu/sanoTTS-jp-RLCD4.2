"""Check first-party Git candidates; never upload, stage, or print secret values."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[1]
REQUIRED=('README.md','README.en.md','docs/TRAINING.md','docs/TRAINING.en.md',
 'docs/REPRODUCE.md','docs/REPRODUCE.en.md','licenses/README.md','licenses/README.en.md',
 'licenses/VOICE_TERMS.md','licenses/sanoTTS-jp-NOTICE.txt','licenses/sanoTTS-jp-Apache-2.0.txt',
 'licenses/NOTICE-Moonshine.txt','licenses/Moonshine-Community-LICENSE.txt',
 'licenses/Shinonome-LICENSE.txt','licenses/Shinonome-AUTHORS.txt','licenses/Shinonome-NOTICE.md')
FORBIDDEN={'.bin','.f32','.wav','.pcm','.pt','.safetensors','.onnx','.parquet','.npz','.npy','.elf','.map','.log'}
SECRET=[re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
        re.compile(r'\bgh[pousr]_[A-Za-z0-9]{30,}\b'),re.compile(r'\bhf_[A-Za-z0-9]{30,}\b')]

def main():
    names=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z'],cwd=ROOT).decode().split('\0')
    names=sorted(set(x for x in names if x));issues=[];manifest=[]
    for name in REQUIRED:
        if not (ROOT/name).is_file():issues.append({'file':name,'reason':'missing required notice/document'})
    for name in names:
        if name.startswith('third_party/'):continue # separately pinned submodule, not an audited vendored tree
        path=ROOT/name
        if path.is_symlink():issues.append({'file':name,'reason':'symlink requires review'});continue
        if not path.is_file():continue
        if '.cache' in path.parts or path.suffix.lower() in FORBIDDEN or path.name.startswith('.env'):
            issues.append({'file':name,'reason':'private/generated asset candidate'});continue
        raw=path.read_bytes();text=raw.decode('utf-8',errors='replace')
        if any(rx.search(text) for rx in SECRET):issues.append({'file':name,'reason':'possible credential; inspect locally'})
        if re.search(r'/(?:home|Users)/[A-Za-z0-9_.-]+/',text):issues.append({'file':name,'reason':'machine-specific absolute path'})
        manifest.append({'path':name,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
    upstream=(ROOT/'third_party/sanoTTS-jp/LICENSE-MODEL.md').read_text()
    required=upstream.split('#### (A)',1)[1].split('```',2)[1].split('\n蒸留に使用したテキストコーパス:')[0].strip()
    if required not in (ROOT/'licenses/sanoTTS-jp-NOTICE.txt').read_text():
        issues.append({'file':'licenses/sanoTTS-jp-NOTICE.txt','reason':'v4 attribution differs from pinned upstream'})
    submodule=subprocess.check_output(['git','-C','third_party/sanoTTS-jp','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    if submodule!='f427b1e6bf743965c9b033d43fdf84b56f8f7543':issues.append({'file':'.gitmodules','reason':'unexpected TTS revision'})
    has_history=subprocess.run(['git','rev-parse','--verify','HEAD'],cwd=ROOT,capture_output=True).returncode==0
    report={'files':manifest,'issues':issues,'history_present':has_history,'submodule_revision':submodule,
        'scope':'First-party working/index candidates only; submodule contents and any existing history require separate audit.',
        'legal_clearance':False,'weights_release':'HOLD'}
    dest=ROOT/'.cache/release/source-check.json';dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'candidate_files':len(manifest),'issues':issues,'history_present':has_history,
        'weights_release':'HOLD','legal_clearance':False},ensure_ascii=False,indent=2))
    return bool(issues)
if __name__=='__main__':raise SystemExit(main())
