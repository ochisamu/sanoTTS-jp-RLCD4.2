"""Package only named model-free build artifacts and notices; never flash reads."""
import argparse,hashlib,json,re,shutil,subprocess,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser();p.add_argument('--build',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);args=p.parse_args()
    if args.out.exists():raise FileExistsError(args.out)
    args.out.mkdir(parents=True)
    files={'rlcd42-offline-voice-app.bin':args.build/'rlcd42_stt_mic_probe.bin',
        'bootloader.bin':args.build/'bootloader/bootloader.bin',
        'partition-table.bin':args.build/'partition_table/partition-table.bin'}
    if files['rlcd42-offline-voice-app.bin'].stat().st_size>0x200000:raise ValueError('App too large')
    for name,source in files.items():
        blob=source.read_bytes()
        if re.search(rb'/(?:home|Users)/[A-Za-z0-9_.-]+/',blob):raise ValueError('Private build path in binary')
        shutil.copyfile(source,args.out/name)
    shutil.copytree(ROOT/'licenses',args.out/'licenses')
    shutil.copyfile(ROOT/'LICENSE',args.out/'LICENSE')
    shutil.copyfile(ROOT/'docs/FIRMWARE_RELEASE.md',args.out/'README.md')
    revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    manifest=dict(source_commit=revision,version='offline-voice-v0.1.0',board='ESP32-S3-RLCD-4.2 N16R8',
        idf='v5.5.4',toolchain='xtensa-esp-elf GCC 14.2.0 esp-14.2.0_20260121',
        model_weights_included=False,flash_backup_included=False,
        note='Not turnkey. Only app/bootloader/partition binaries. See README before writing.')
    (args.out/'build-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    paths=sorted(p for p in args.out.rglob('*') if p.is_file())
    (args.out/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+str(p.relative_to(args.out))+'\n' for p in paths))
    dest=args.out.with_suffix('.zip')
    if dest.exists():raise FileExistsError(dest)
    with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED) as z:
        for file in sorted(args.out.rglob('*')):
            if file.is_file():z.write(file,str(file.relative_to(args.out)))
    print(dest)
if __name__=='__main__':main()
