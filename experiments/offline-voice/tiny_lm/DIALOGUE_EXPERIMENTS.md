# Broader Japanese dialogue / 日本語対話の拡張実験

## Status / 状態

This is a **research log, not a claim of general Japanese conversation**.
Final outcome of the training run: **quality gate failed; device unchanged at that point**.
Subsequently, the user explicitly requested an experimental device installation.
The selected BPE candidate is now installed; see [BPE_DEVICE.md](BPE_DEVICE.md).
This does not change the dialogue-quality verdict.
The selected semantic-distillation candidate reached 85/137 exact wording-dev
matches (62.0%). A one-time 40-question challenge review by the coding assistant
found 21 passes, 4 partial answers and 15 failures; this is NOT independent human
evaluation or statistical conversation accuracy. Daily-only cases were 12/17
passes, but unknown requests and negation contrasts were unreliable. See
[the complete local result](../results/dialogue_expansion_20260924.json).
The previous 26-family model and the new BPE candidate are distinct.
No teacher model, downloaded dataset, student weights or device recordings belong
in Git. Everything under `.cache/` stays local and ignored.

元の26系統の小さな学習例から、実際の日本語事前学習と対話学習へ拡張しました。
ただし、大量のデータでlossが下がっても自然に会話できるとは限りません。
人間同士の雑談をそのまま学習させた候補は、無関係な相づち・反復・人間としての
生活経験の捏造が残り、採用していません。

The daily-dialogue branch uses 114 semantic families, 286 authored training
questions and 137 wording-dev questions. A manually reviewed teacher pilot adds
336 paraphrases, giving **622 distinct training questions**, expanded to 14,928
rows by prefixes/suffixes. This is NOT 14,928 distinct meanings. Answers remain
authored, reviewed short replies. Inference generates tokens; it does not consult
this data file, a rule table or a nearest-neighbour database. Nevertheless,
response memorization is strong, so it is not equivalent to a general LLM.

## Assets and terms / 資産と利用条件

See [the notices](../licenses/dialogue-data-NOTICE.md) for pinned revisions,
authors and external terms. Downloaders use public files without credentials,
allow-listed asset types, safetensors and `trust_remote_code=False`.

- OASST Japanese: language pretraining; 186,717 training chunks, 9,867,375
  kana content tokens after filtering. Family split, not topic-disjoint.
- RealPersonaChat: 265,899 adjacent-turn training pairs. All speaker metadata
  and profiles discarded. Dialogue-disjoint splits, not speaker/topic-disjoint.
  Context-dependent replies are a known source of noise.
- BPE: 1,024 tokens, maximum 12 kana per token, punctuation isolated.
  Trained only on training text, about 1.90 kana characters/token in that corpus.
- Teacher QA pilots are **not** automatically training data. Qwen and Sarashina
  pilots showed factual/persona/instruction-following errors. Only explicitly
  reviewed question paraphrases enter the daily branch; teacher-generated
  answers from those pilots do not.
- E5 semantic targets teach input representations during training only. They
  do not supply a retrieval database or run on the ESP32.

OASST/Qwen are declared Apache-2.0; RealPersonaChat is CC BY-SA 4.0. Treat its
prepared derivatives accordingly. This project does not assert that a student
trained from that corpus can be distributed under MIT. Do not release weights
without checking the applicable terms. Japanese teacher and E5 notices are
separate. Original authored daily seeds and lab code are MIT.

## Reproduction / 再実行

Linux/WSL, Python 3.12, C compiler, CUDA GPU. Tested on RTX 5060 Ti 16GB with
PyTorch 2.10.0+cu128. Use a dedicated environment; do not alter another project's
environment. Teacher generation is local, not an API and not the device runtime.

```sh
python3 -m venv .venv-dialogue
.venv-dialogue/bin/pip install torch==2.10.0 --index-url https://download.pytorch.org/whl/cu128
.venv-dialogue/bin/pip install -r tiny_lm/requirements-dialogue.txt
# Activate the environment for the following commands.
. .venv-dialogue/bin/activate

python tiny_lm/fetch_dialogue.py
python tiny_lm/prepare_language.py
python tiny_lm/fetch_realchat.py
python tiny_lm/prepare_realchat.py
python tiny_lm/prepare_bpe.py

python tiny_lm/dialogue_train.py --stage language --steps 10000 --dim 256 --out .cache/dialogue-language-256
python tiny_lm/dialogue_train.py --stage language --bpe --data .cache/bpe-dialogue --steps 18000 --dim 256 --out .cache/bpe-language-256
python tiny_lm/prepare_daily.py
python tiny_lm/paraphrase_daily.py
```

**Stop and inspect all generated paraphrases.** `prepare_daily_aug.py` contains
the manually reviewed selection for the original pilot. The reviewed artifact's
SHA256 was `f8d1191966e83dc0451be57a4d222d5cad92cfd790a338b066eadba077668053`.
Reusing that selection on different generated text is invalid. Checkpoint/model
versions, batch sizes, seeds, resumptions and hardware can change teacher output;
bit-identical regeneration is not guaranteed. Inspect and update the selection
for a new pilot rather than bypassing review. A SHA argument alone does not prove
that review took place.
Review in this run was by the coding assistant, not an external human evaluator.

```sh
python tiny_lm/prepare_daily_aug.py --reviewed-sha256 VERIFIED_REVIEWED_HASH
python tiny_lm/dialogue_train.py --stage dialogue --bpe --data .cache/daily-aug-bpe --steps 4000 --dim 256 --resume .cache/bpe-language-256/best.safetensors --out .cache/daily-aug-bpe-256 --lr .00025
python tiny_lm/dialogue_train.py --stage dialogue --bpe --data .cache/daily-aug-bpe --steps 4000 --dim 256 --resume .cache/bpe-language-256/best.safetensors --out .cache/daily-aux-bpe-256 --lr .0002 --intent-aux 1
python tiny_lm/export_bpe.py --checkpoint .cache/daily-aug-bpe-256/best.safetensors --out .cache/daily-aug-bpe-256/model.bin
python tiny_lm/evaluate_daily.py --model .cache/daily-aug-bpe-256/model.bin --out .cache/daily-aug-bpe-256/wording-dev-packed.json
KLM_TEST_MODEL=.cache/daily-aug-bpe-256/model.bin python -m unittest discover -s tiny_lm -p 'test_*.py' -v
```

Output directories must be separate for comparisons. Language and dialogue
stages warm-start model weights but reset the optimizer. Checkpoint selection is
by dev response NLL, not final test. Augmentation/dev splits and data hashes are
recorded locally. BPE training scripts do not automatically export or flash.

Optional semantic distillation:

```sh
python tiny_lm/semantic_teacher.py
python tiny_lm/semantic_train.py --steps 8000 --out .cache/semantic-bpe-256
python tiny_lm/dialogue_train.py --stage dialogue --bpe --data .cache/daily-aug-bpe --steps 5000 --dim 256 --resume .cache/semantic-bpe-256/best.safetensors --out .cache/daily-semantic-bpe-256 --lr .00015 --intent-aux 1 --semantic-projection .cache/semantic-bpe-256/projection.safetensors --semantic-weight .5
python tiny_lm/export_bpe.py --checkpoint .cache/daily-semantic-bpe-256/best.safetensors --out .cache/daily-semantic-bpe-256/model.bin
python tiny_lm/evaluate_daily.py --model .cache/daily-semantic-bpe-256/model.bin --out .cache/daily-semantic-bpe-256/wording-dev-packed.json
# Run this only after candidate selection; do not tune from it and call it test.
python tiny_lm/audit_dialogue.py --model .cache/daily-semantic-bpe-256/model.bin --out .cache/daily-semantic-bpe-256/final-audit.json
```

The 60,000 training questions and 2,000 development questions come from the
existing human-dialogue split, not user recordings or final test. E5 uses the
documented `query: ` prefix, masked mean pooling and normalized 384D vectors.
The student learns centered semantic targets plus a small language-modelling
loss. Projection weights are training-only and excluded from device exports.

## Comparisons / 比較の読み方

All rows below use the same **137 wording-dev questions with known topics and
answers**, not independent open-domain accuracy. Exact match ignores punctuation;
it can reject a valid alternative answer and accept an overly generic reference.
The old model also uses a different kana convention, so its exact-match result
must not be advertised as a fair percentage improvement in dialogue accuracy.

| Candidate | Runtime evaluated | Exact / 137 |
| --- | --- | ---: |
| Daily seeds, character model | native C W8A8 | 41 |
| Daily seeds, BPE model | host float | 56 |
| Reviewed paraphrases + length augmentation, character | native C W8A8 | 69 |
| Reviewed paraphrases + length augmentation, BPE | native C W8A8 | 75 |
| BPE + training-only intent auxiliary loss | native C W8A8 | 83 |
| BPE + semantic distillation + auxiliary input losses | native C W8A8 | 85 |

The packed BPE candidate is 3,074,496 bytes (about 2.93MiB), 2,910,464 parameters,
four layers, D256/H8/FF768, context 96 tokens. It fits a **proposed** 3MiB slot but
NOT the installed 2MiB LM slot. Size checks and native numerical tests alone do
not mean it was deployed or that dialogue quality is sufficient. The existing
firmware/partition layout must not be changed solely because an export fits.

Observed unresolved failures include wrong topics, ignored negation, tense
confusion, overly generic replies and some truncated/empty outputs on long
questions. No automatic voice-chat mode has been enabled by these host tests.
Existing STT latency is a separate unresolved limitation; LM improvements do not
remove it. Multi-turn conversational memory is not implemented.

One pronunciation defect was traced to preprocessing, not just generation:
Open JTalk reads the old all-hiragana answer `いっしょにはなそう` as
`いっしょにわなそお`, while `一緒に話そう` produces the intended pronunciation.
The frozen candidate/report retain this defect for honest reproducibility.
Before a new training run, use unambiguous source orthography plus explicit
reading-regression tests, and separately add contrastive negation/tense examples
and reviewed unsupported-request responses. Do not train on the 40 audit cases
and continue reporting them as independent validation.

## Runtime format / 推論形式

`KLMW8v1` stays the default character runtime for legacy firmware. `KLMW8v2`
is selected only with `KLM_BPE=1`, `KLM_DIM=256`, `KLM_HEADS=8`, `KLM_FF=768`.
It embeds a validated kana vocabulary and ranked merge triples, then the same
row-wise INT8 matrices/scales and float vectors. CRC-like FNV checksum, dimensions,
token alphabet, merge topology, concatenations, finite scales and file bounds
are checked before use. There is no dynamic code in the model artifact.

Tests compare tokenization with the Python tokenizer and projections/attention
with an independent PyTorch W8A8 reference. Hardware PIE parity, memory lifecycle,
real latency and audio need a separate device run before adoption. BPE tokens are
not characters: output token limits and UTF-8 buffer limits must both be enforced.
