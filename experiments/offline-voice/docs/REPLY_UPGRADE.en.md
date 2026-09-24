# Kanji captions, SLM adaptation and local knowledge

[日本語](REPLY_UPGRADE.md) · [Overview](../README.en.md)

## Runtime

Recognized kana → local knowledge lookup → a stored, authored answer on a match,
otherwise neural SLM generation → separate display text and reading → sanoTTS.
Only BOOT/CHAT/ASK/ASKSAY change; KEY echo is unchanged. No network, PC inference,
always-on recording or conversation history is added.

There are 16 fact cards and 48 question aliases: small arithmetic examples, units,
and this firmware's capabilities. Lookup matches whole phrases after removing
punctuation and selected conversational prefixes. It deliberately avoids fuzzy
number matching. This is not a general calculator, semantic search or generative
RAG; it is a hybrid of lookup and generation. Unknown questions still reach the
SLM, so abstention is not guaranteed. Logs distinguish `REPLY_SOURCE:SLM` from
`REPLY_SOURCE:LOCAL_KNOWLEDGE:<id>`.

149 known whole-answer readings map to authored display forms. Unmapped or
ambiguous readings remain kana; no general kana-to-kanji conversion is claimed.
STT captions remain kana. TTS always receives the reading, never kanji.
`DISPLAY_REPLY` logs the caption and `LM_REPLY` the reading. The latter name is
retained for compatibility even on the lookup path; it does not imply inference.
The large face, English status, temporary captions and current DSP are retained.

## Training and evaluation

38 original families / 114 new independent questions cover negation, ambiguity,
unknown information and short facts. Replay plus prefix augmentation and repeated
loss weighting produce 17,664 rows, not 17,664 independent questions. No user
audio or conversation is used. Original MIT seeds live in `improvement_data.py`
and `knowledge_data.py`. Parent checkpoint/corpus conditions, including the
RealPersonaChat distribution review, still apply; weights remain withheld.

The four-layer adaptation starts from the previous checkpoint, with 6,000 steps
on RTX5060Ti (~121 seconds; ~716MiB training memory). Best dev NLL selects step
2,000. Quantized size stays at 3,074,496 bytes / 2.91M parameters.

| Held-out wording exact match | Parent | Adapted four-layer |
| --- | --- | --- |
| Existing families | 85/137 | 88/137 |
| Added families | 2/38 | 27/38 |
| Total | 87/175 | 115/175 |

These are W8A8 native-C SLM-only results, without knowledge lookup, ignoring
punctuation. This is known-family development data, not general conversation
accuracy or an independent final test. Exact match misses valid paraphrases;
genuine negation and factual errors also remain. Do not rely on this experiment
for medical, legal, financial or other consequential decisions.

Selected SHA256: `0c9037b28e675339719cc496e8cd3d180712ed0838292170de241d6b1687b53c`.

A five-layer candidate trained from the same parent/data for 6,000 steps scored
113/175 (existing 83/137, added 30/38), at 3,740,096 bytes. The appended block
starts as an identity residual with zero output projections. It is not selected:
the larger size did not improve the aggregate development score. This single
experiment does not prove that scaling cannot help. Five-layer evaluation was
host W8A8 only, not device latency; the device partition layout is unchanged.

On device, 32/32 answers matched the reference. The 31 neural cases took
999–1719ms excluding recognition/TTS; one case used knowledge lookup. All 16
fact cards separately passed reading/display log checks, and both knowledge and
neural speech paths completed. Audible/physical screen quality needs user feedback.

## Reproduction

Prepare the parent checkpoint, `.cache/daily-aug-bpe/` and training dependencies
using [the existing training commands](../tiny_lm/DIALOGUE_EXPERIMENTS.md), after
reviewing each source's terms. Run in the prepared training environment:

```sh
python tiny_lm/prepare_improvement.py
python tools/prepare_reply_assets.py
python tiny_lm/dialogue_train.py --stage dialogue --steps 6000 --dim 256 --bpe --resume .cache/daily-semantic-bpe-256/best.safetensors --data .cache/improvement-bpe --out .cache/improvement-model-256 --lr 0.00015
python tiny_lm/export_bpe.py --checkpoint .cache/improvement-model-256/best.safetensors --tokenizer .cache/improvement-bpe/tokenizer.json --out .cache/improvement-model-256/model.bin
python tiny_lm/evaluate_daily.py --model .cache/improvement-model-256/model.bin --data .cache/improvement-bpe --out .cache/improvement-model-256/eval.json
python -m unittest discover -s tests -p test_reply_support.py -v
```

The [five-layer comparison commands](REPLY_UPGRADE.md#再実行) are also recorded;
they explicitly require a larger export budget and must not be flashed to the
current layout. The preparation/training tools refuse to overwrite completed
experiments. Use distinct output directories for new experiments.

`python tools/prepare_reply_assets.py` can regenerate the Flash tables directly
from authored source seeds without model weights or downloaded training corpora;
the host reading-converter dependencies are still needed. Generated files stay
under `.cache/reply-assets/`, outside Git. Follow the [build guide](REPRODUCE.en.md).
Update only app `0x10000` and SLM `0xc10000` on an existing matching layout.
Do not change STT/TTS, bootloader or partitions. A five-layer comparison is a
separate experiment that exceeds the current 3MiB model partition; do not flash
it using the existing layout.

Try “一週間は何日”, “一足す一は”, or “宿題はまだ終わってない”. Live STT can
misrecognize these; examples are not an accuracy benchmark.
