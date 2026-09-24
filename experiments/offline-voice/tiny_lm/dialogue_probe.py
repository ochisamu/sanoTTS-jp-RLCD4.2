"""Packed C generation audit. Probes are development diagnostics, not test scores."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import struct
import subprocess
from dialogue_data import ROOT,Kana

PROBES=[
 '今日は仕事が長引いて、もうくたくただよ',
 '雨だから家の中で楽しめることを探している',
 '料理を始めたいけど何から作ればいいかな',
 '読みかけの本が面白くて眠れなかった',
 '週末は山と海のどっちに行こうかな',
 '最近運動不足なんだけど何をしたらいい',
 '旅行に持っていく物で忘れやすいのは何',
 '明日は友達の誕生日なんだ',
 '猫がいつも机の上に乗ってくるよ',
 '練習した曲を最後まで弾けるようになった',
 'コーヒーと紅茶ならどっちが好き',
 '初めての場所に行くから少し緊張する',
 '一人で映画を見るのも楽しいよね',
 '植物を育ててみたいんだけど難しいかな',
 '新しい靴を買ったけど少しきつい',
 '今日は何もする気になれないな',
 'ありがとう、話を聞いてくれて助かった',
 'あなたは実際にご飯を食べられるの',
 '今の天気を調べてくれる',
 'さっきの話をもう少し詳しく教えて',
]

def main():
    p=argparse.ArgumentParser();p.add_argument('--model',type=Path,required=True)
    p.add_argument('--data',type=Path,default=ROOT/'.cache/realchat')
    p.add_argument('--out',type=Path,required=True);p.add_argument('--count',type=int,default=24)
    p.add_argument('--split',choices=['dev','test'],default='dev');args=p.parse_args()
    header=struct.unpack('<8s10I',args.model.read_bytes()[:48]);dim,heads,ff=header[3:6]
    if (dim,heads,ff) not in [(192,6,512),(256,8,768)]:raise ValueError('unsupported shape')
    bpe=header[0]==b'KLMW8v2\0';exe=ROOT/f'.cache/klm-native-{dim}-{int(bpe)}'
    flags=['-DKLM_BPE=1'] if bpe else []
    subprocess.run(['cc','-O3','-std=c11','-Wall','-Wextra','-Werror',f'-DKLM_DIM={dim}',f'-DKLM_HEADS={heads}',f'-DKLM_FF={ff}',*flags,str(ROOT/'tiny_lm/klm.c'),str(ROOT/'tiny_lm/native.c'),'-lm','-o',str(exe)],check=True)
    convert=Kana();items=[]
    if args.split=='dev':
        for q in PROBES:
            items.append(dict(question=q,question_kana=convert(q),source='authored development probe'))
    pool=[json.loads(x) for x in (args.data/f'{args.split}.jsonl').read_text().splitlines()]
    items.extend(random.Random(60173).sample(pool,min(args.count,len(pool))))
    results=[]
    for r in items:
        run=subprocess.run([str(exe),str(args.model),r['question_kana']],text=True,capture_output=True)
        result={**r,'prediction':run.stdout.strip(),'terminated':run.returncode==0,'native_metrics':run.stderr.strip()}
        results.append(result)
        if r.get('source')=='authored development probe':print(r['question']+' -> '+result['prediction'],flush=True)
    report=dict(model_sha256=hashlib.sha256(args.model.read_bytes()).hexdigest(),split=args.split,cases=results,
        warning='Read generation quality, not exact-match score. Authored probes are dev. Test must not be used to choose checkpoint. Corpus refs remain local/ignored.')
    args.out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(cases=len(results),terminated=sum(r['terminated'] for r in results))),flush=True)
if __name__=='__main__':main()
