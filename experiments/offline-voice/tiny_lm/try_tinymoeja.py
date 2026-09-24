"""PC-only probe of a pinned public Japanese micro model. No device writes.

Weights and logs stay in .cache; remote Python code is never executed.
This is a continuation model, not a chat-tuned assistant.
"""
import argparse,hashlib,json,time,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
REPO='shibatch/tinymoeja2m'
REVISION='6811831904748f6bcf067eb57f0ad803add6e5f9'
CACHE=ROOT/'.cache/tinymoeja2m'
sys.path.insert(0,str(ROOT/'.cache/tinymoeja-deps'))
PROMPTS=[
    'むかしむかし、',
    'トムとリリーは',
    '今日は雨が降っています。',
    '質問：こんにちは。\n回答：',
    '質問：一週間は何日ですか。\n回答：',
    '質問：宿題はまだ終わっていません。\n回答：',
    '質問：簡単な料理を教えてください。\n回答：',
    'しつもん：いっしゅうかんわなんにち。\nこたえ：',
]
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--fetch',action='store_true',help='Download pinned model/data files only')
    p.add_argument('--prompt',action='append');p.add_argument('--smoke',action='store_true')
    p.add_argument('--interactive',action='store_true');p.add_argument('--out',type=Path)
    p.add_argument('--tokens',type=int,default=80);p.add_argument('--temperature',type=float,default=0)
    p.add_argument('--device',choices=['cpu','cuda'],default='cpu');args=p.parse_args()
    if not 1<=args.tokens<=256 or not 0<=args.temperature<=2:p.error('tokens: 1..256; temperature: 0..2')
    if args.out and args.out.exists():raise FileExistsError(args.out)
    if args.fetch:
        from huggingface_hub import snapshot_download
        snapshot_download(REPO,revision=REVISION,local_dir=CACHE,
            allow_patterns=['README.md','hf/config.json','hf/generation_config.json','hf/model.safetensors',
                'hf/tokenizer.model','hf/tokenizer_config.json','hf/special_tokens_map.json'])
        files={str(x.relative_to(CACHE)):hashlib.sha256(x.read_bytes()).hexdigest()
               for x in sorted((CACHE/'hf').iterdir()) if x.is_file()}
        (CACHE/'source.json').write_text(json.dumps(dict(repo=REPO,revision=REVISION,files=files),indent=2)+'\n')
    if not (args.prompt or args.smoke or args.interactive):
        if args.fetch:print('Pinned files downloaded. Use --smoke or --interactive.');return
        p.error('Choose --fetch, --smoke, --prompt or --interactive')
    import sentencepiece as spm
    import torch
    from transformers import MixtralForCausalLM,MixtralConfig
    from safetensors.torch import load_file
    torch.set_num_threads(2);torch.manual_seed(42)
    if args.device=='cuda' and not torch.cuda.is_available():raise RuntimeError('CUDA unavailable')
    sp=spm.SentencePieceProcessor(model_file=str(CACHE/'hf/tokenizer.model'))
    raw=json.loads((CACHE/'hf/config.json').read_text())
    # The upstream v5 config records null head_dim and nested rope_parameters;
    # express the same dimensions/theta for the existing Transformers 4 runtime.
    raw['head_dim']=raw['hidden_size']//raw['num_attention_heads']
    raw['rope_theta']=raw.pop('rope_parameters')['rope_theta']
    config=MixtralConfig(**raw);config._attn_implementation='eager'
    model=MixtralForCausalLM(config)
    model.load_state_dict(load_file(str(CACHE/'hf/model.safetensors')),strict=True)
    model=model.to(args.device).eval()
    params=sum(x.numel() for x in model.parameters())
    print(f'{REPO} / {params:,} parameters / {args.device}. PC ONLY; not chat-tuned.',flush=True)
    results=[]
    def run(prompt):
        ids=[1]+sp.encode(prompt)
        if len(ids)>256:raise ValueError('Prompt exceeds this probe limit of 256 tokens')
        x=torch.tensor([ids],device=args.device);kwargs={}
        if args.temperature:kwargs.update(temperature=args.temperature,top_p=.9)
        start=time.perf_counter()
        with torch.inference_mode():
            generated=model.generate(x,attention_mask=torch.ones_like(x),max_new_tokens=args.tokens,
                do_sample=args.temperature>0,pad_token_id=2,bos_token_id=1,eos_token_id=2,**kwargs)
        new=generated[0,len(ids):].tolist();elapsed=time.perf_counter()-start
        text=sp.decode(new);row=dict(prompt=prompt,continuation=text,tokens=len(new),
            eos=bool(new and new[-1]==2),seconds=elapsed,tokens_per_second=len(new)/elapsed)
        results.append(row);print('\nINPUT: '+prompt+'\nOUTPUT: '+text,flush=True)
        print(f'[{len(new)} tokens, {elapsed:.2f}s; PC timing, not ESP32]',flush=True)
    for prompt in (PROMPTS if args.smoke else [])+(args.prompt or []):run(prompt)
    if args.interactive:
        print('Enter a Japanese prompt; /quit exits. /ask <text> adds a question/answer prefix.',flush=True)
        while True:
            try:prompt=input('ja> ')
            except (EOFError,KeyboardInterrupt):break
            if prompt.strip()=='/quit':break
            if not prompt.strip():continue
            if prompt.startswith('/ask '):prompt='質問：'+prompt[5:]+'\n回答：'
            try:run(prompt)
            except ValueError as e:print(e,flush=True)
    if args.out:
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_text(json.dumps(dict(repo=REPO,revision=REVISION,parameters=params,
            device=args.device,temperature=args.temperature,seed=42,cases=results,
            warning='Host FP32 exploration, not dialogue accuracy, ESP32 performance, or a device deployment.'),ensure_ascii=False,indent=2)+'\n')
if __name__=='__main__':main()
