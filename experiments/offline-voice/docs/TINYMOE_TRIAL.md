# tinymoeja2m のPC試用 / PC-only trial

RLCDのファーム・重みは変更しません。これはPC上のFP32検証です。
No device writes: these are host FP32 results, not ESP32 speed or chat accuracy.

- Upstream: https://huggingface.co/shibatch/tinymoeja2m
- Pinned revision: `6811831904748f6bcf067eb57f0ad803add6e5f9`
- Loaded parameters: 2,009,472; all checkpoint keys loaded with strict checking.
- Model card declares MIT. Japanese translated TinyStories is separately marked
  CDLA-Sharing-1.0; this trial does not grant blanket redistribution clearance.
- Downloaded weights, upstream README, SHA256 manifest and optional logs remain
  under ignored `.cache/tinymoeja2m/`. No remote Python code is executed.

Use the existing training Python environment with PyTorch, Transformers 4.57.6,
huggingface-hub 0.36.2, safetensors and SentencePiece 0.2.1 installed. Missing
SentencePiece can be installed separately in `.cache/tinymoeja-deps/` to avoid
changing another environment. The loader maps the upstream v5 RoPE/head-dimension
configuration to the same explicit values in v4; it does not alter weights.

```sh
python tiny_lm/try_tinymoeja.py --fetch
python tiny_lm/try_tinymoeja.py --interactive
# One prompt / 単発:
python tiny_lm/try_tinymoeja.py --prompt 'むかしむかし、'
# Reproducible probe / 再現用:
python tiny_lm/try_tinymoeja.py --smoke --out .cache/tinymoeja2m/smoke-greedy.json
```

`/quit` exits; `/ask 一週間は何日？` adds a question/answer prefix but does NOT
make the model instruction-tuned. Default greedy decoding; `--temperature 0.7`
enables sampling. `--tokens 80` limits the continuation. No logs are saved unless
`--out` is explicitly supplied; no prompts are uploaded.

初回8プロンプトの試行では日本語の物語は生成できましたが、質問には物語で返答し、
繰り返しも見られました。「一週間は何日ですか」に七日とは答えませんでした。
かな入力にも適切には回答しませんでした。今の対話モデルの代替として未採用です。
これは少数の開発用試行で、汎用的な正答率ではありません。

The initial eight prompts produced Japanese story continuations, but questions
also elicited story text rather than direct answers, with repetition. Kana-only
input did not answer correctly either. This is an exploratory sample, not a
benchmark; the checkpoint has not replaced the current device model.
