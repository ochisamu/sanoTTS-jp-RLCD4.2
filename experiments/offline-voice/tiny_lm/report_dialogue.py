"""Summarize this fixed experiment without bundling external corpora/weights."""
import argparse
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SELECTED_SHA='985505b6abfe3504ccadd6b535a48a87e8a48ebb61183af0e9d8305cf5ef26e7'
PASS={0,1,2,5,6,7,8,10,11,12,15,16,17,18,20,23,24,25,26,37,39}
PARTIAL={9,14,19,32}
NOTES={
 9:'Acknowledges effort and suggests rest; does not explicitly claim completion, but does not address unfinished homework.',
 14:'Suggests the walk already proposed; redundant but broadly on topic.',
 19:'Relevant response, but はなそう became わなそう. Reproduced in Kana conversion of the original all-hiragana training answer; unambiguous kanji input reads correctly. This is a preparation defect, not solely a model-generation failure.',
 32:'Asks for clarification rather than explaining the unknown term; not a clear statement of inability.',
}

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);args=p.parse_args()
    if args.out.exists():raise FileExistsError('Preserve experiment report')
    root=ROOT/'.cache/daily-semantic-bpe-256'
    audit=json.loads((root/'final-audit.json').read_text())
    if audit['model_sha256']!=SELECTED_SHA or len(audit['cases'])!=40:raise ValueError('Ratings apply only to the reviewed frozen candidate')
    for i,r in enumerate(audit['cases']):
        r['assistant_rating']='pass' if i in PASS else 'partial' if i in PARTIAL else 'fail'
        if i in NOTES:r['review_note']=NOTES[i]
    comparisons=[]
    for folder,name in [('daily-char-256','wording-dev.json'),('daily-aug-char-256','wording-dev.json'),('daily-aug-bpe-256','wording-dev-packed.json'),('daily-aux-bpe-256','wording-dev-packed.json'),('daily-semantic-bpe-256','wording-dev-packed.json')]:
        r=json.loads((ROOT/'.cache'/folder/name).read_text())
        comparisons.append(dict(candidate=folder,artifact_sha256=r['artifact_sha256'],runtime=r['runtime'],summary=r['summary']))
    report=dict(date='2026-09-24',status='research_improved_but_broad_dialogue_gate_failed',
        device_changed=False,published=False,pushed=False,model=json.loads((root/'model.manifest.json').read_text()),
        coverage=json.loads((ROOT/'.cache/daily-aug-bpe/manifest.json').read_text()),comparisons=comparisons,
        challenge_summary=dict(pass_count=len(PASS),partial_count=len(PARTIAL),fail_count=40-len(PASS)-len(PARTIAL),
            daily_pass=12,daily_total=17,reviewer='Coding assistant qualitative assessment, not independent human/expert rating'),
        challenge_cases=audit['cases'],tests=dict(lm_and_pipeline_passed=16),
        decision='Do not flash or enable automatic voice chat. Keep current device firmware and models unchanged.',
        limitations=['Known-topic wording dev, used for selection, is not open-domain accuracy.',
            'Forty author-selected post-selection challenges are not a representative statistical test.',
            'Negation, tense, unsupported requests and unknown-topic fallback remain unreliable.',
            'No multi-turn memory; existing STT latency remains unchanged.',
            'BPE model native checks passed; hardware parity/latency for this candidate not measured.',
            'Runtime generates tokens but largely memorizes authored responses; no general LLM claim.',
            'Weights and corpora remain ignored external/local assets. RealPersonaChat derivative terms require review before any release.'])
    args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(out=str(args.out),status=report['status'],audit=report['challenge_summary'])),flush=True)

if __name__=='__main__':main()
