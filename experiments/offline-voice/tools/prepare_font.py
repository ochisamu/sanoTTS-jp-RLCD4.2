"""Generate Flash-only Shinonome 16px tables; no upstream scripts are executed."""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
REV = '053b21e0a11ef5799c1ea3cefc374763add80617'
SOURCES = {
    '16/kanjic/font_src.bit': '38ed485b3565b9c71147a459a9d0f8057714948ca6eaa2e6a3d74c95868d6467',
    '16/latin1/font_src.bit': 'dbc6362567edb4e2de7041ad03864f848b1cfbe7c966aba89bb34d0068bd896d',
    'LICENSE': 'a38a9a330458c11317ec5028df7cd4c7b44210446300e20020f942390d5d5dd2',
    'AUTHORS': '4319ec2ed0db417718b8680dff310285d69c16374afa9a4480917164edb422ae',
}

def glyphs(text, jis):
    for block in text.split('STARTCHAR ')[1:]:
        lines = [line.split('#',1)[0].rstrip() for line in block.splitlines()]
        value = int(next(x.split()[1] for x in lines if x.startswith('ENCODING ')))
        width = int(next(x.split()[1] for x in lines if x.startswith('DWIDTH ')))
        if jis:
            code = ord(bytes([(value >> 8) | 128, (value & 255) | 128]).decode('euc_jp'))
        else:
            if not 32 <= value <= 126: continue
            code = value
        bitmap = lines[lines.index('BITMAP') + 1:lines.index('ENDCHAR')]
        if len(bitmap) != 16 or width not in (8, 16): raise ValueError('Unexpected glyph')
        if any(len(row) != width or set(row) - {'.', '@'} for row in bitmap):
            raise ValueError('Invalid pixels')
        rows = [int(row.replace('.', '0').replace('@', '1'), 2) << (16-width) for row in bitmap]
        yield code, width, rows

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--download', action='store_true')
    parser.add_argument('--source', type=Path, help='Optional pinned upstream checkout')
    args = parser.parse_args(); cache = ROOT / '.cache/font'; cache.mkdir(parents=True, exist_ok=True)
    data = {}
    for name, sha in SOURCES.items():
        path = cache / name
        if args.source:
            raw = (args.source/name).read_bytes()
        elif args.download:
            with urllib.request.urlopen(f'https://raw.githubusercontent.com/code4fukui/shinonome-font/{REV}/{name}', timeout=30) as response:
                raw = response.read(4_000_001)
        else:
            raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != sha: raise ValueError(f'Hash mismatch: {name}')
        path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw); data[name] = raw
    table = {}
    for name, jis in [('16/kanjic/font_src.bit', True), ('16/latin1/font_src.bit', False)]:
        for code, width, rows in glyphs(data[name].decode('utf-8'), jis):
            if code in table: raise ValueError('Duplicate Unicode glyph')
            table[code] = (width, rows)
    out = ['/* Generated from Shinonome 0.9.11; see licenses/Shinonome-LICENSE.txt. */',
           '#include <stdint.h>', 'typedef struct {uint16_t code; uint8_t width; uint16_t rows[16];} jp_glyph;',
           'static const jp_glyph jp_font[] = {']
    for code, (width, rows) in sorted(table.items()):
        out.append('{0x%04x,%d,{%s}},' % (code, width, ','.join('0x%04x'%x for x in rows)))
    out.append('};\n')
    header = ('\n'.join(out)).encode()
    (cache/'shinonome16.h').write_bytes(header)
    (cache/'manifest.json').write_text(json.dumps({'revision':REV, 'sources':SOURCES,
        'glyphs':len(table), 'header_sha256':hashlib.sha256(header).hexdigest()}, indent=2)+'\n')
    print(f'{len(table)} glyphs; table approximately {len(table)*36} Flash bytes; no PSRAM font copy')

if __name__ == '__main__': main()
