"""Generate inverse phoneme->kana mappings from pinned sanoTTS tables."""
import json
from benchmark import ROOT
from ctc import PHONES


def table():
    data=json.loads((ROOT/'third_party/sanoTTS-jp/csrc/g2p_table.json').read_text())
    inverse={}
    for kana, seq in data['mora'].items():
        if kana in ('ん','ー'): continue
        key=tuple(seq)
        rank=lambda s:(s[0] in 'ぁぃぅぇぉゃゅょゎ',len(s),s)
        if key not in inverse or rank(kana)<rank(inverse[key]): inverse[key]=kana
    # Open JTalk and sanoTTS have different spellings for these palatalized phones.
    aliases={('t','i'):('ty','i'),('d','i'):('dy','i')}
    result=[]
    for p in PHONES:
        row=[inverse.get(aliases.get((p,v),(p,v)),'') for v in 'aiueo']
        row.append({'N':'ん','cl':'っ','pau':'#'}.get(p,inverse.get((p,),'')))
        result.append(row)
    return result


if __name__=='__main__':
    lines=['// Generated from pinned sanoTTS g2p_table.json. Do not edit manually.',
           'static const char *const kana_map[41][6] = {']
    for row in table(): lines.append('    {'+','.join(json.dumps(s,ensure_ascii=False) for s in row)+'},')
    lines.append('};')
    (ROOT/'runtime/kana_table.h').write_text('\n'.join(lines)+'\n')
