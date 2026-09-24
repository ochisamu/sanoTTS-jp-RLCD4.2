"""Collect verbatim compiled-source notice preambles, not code or model weights.

Run against a build's compile_commands.json. Inventory is deliberately inclusive:
some compiled objects are later discarded by the linker. Paths are portable.
"""
import argparse,json,re
from pathlib import Path
def main():
    p=argparse.ArgumentParser();p.add_argument('--build',type=Path,required=True)
    p.add_argument('--idf',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();root=Path(__file__).resolve().parents[1];blocks={}
    files=[Path(x['file']) for x in json.loads((args.build/'compile_commands.json').read_text())]
    files.append(args.idf/'components/xtensa/include/xtensa/hal.h')
    for file in sorted(set(files)):
        if not file.is_file():continue
        if file.is_relative_to(root):name=str(file.relative_to(root))
        elif file.is_relative_to(args.idf):name='ESP-IDF/'+str(file.relative_to(args.idf))
        else:name='external/'+file.name
        text=file.read_text(errors='replace')[:16000]
        for m in re.finditer(r'/\*[\s\S]*?\*/',text):
            block=m.group()
            if re.search(r'copyright|SPDX-License-Identifier|Permission is hereby',block,re.I):
                blocks.setdefault(block,set()).add(name)
    body=['Compiled-source notice preambles (inclusive; not all compiled objects link).',
          'Original wording preserved. See DEPENDENCIES.md for selected license options.',
          'This is not a license for neural weights or generated voice.','']
    for block,names in sorted(blocks.items(),key=lambda pair:sorted(pair[1])):
        body.extend(['Files: '+', '.join(sorted(names)),block,''])
    result='\n'.join(body)
    if re.search(r'/(?:home|Users)/[A-Za-z0-9_.-]+/',result):raise ValueError('Private build path in notices')
    args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(result)
    print(f'{len(blocks)} distinct notice preambles')
if __name__=='__main__':main()
