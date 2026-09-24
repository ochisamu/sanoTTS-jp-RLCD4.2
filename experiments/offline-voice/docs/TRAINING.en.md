# Training provenance, architecture and evaluation

[日本語](TRAINING.md) · [Home](../README.en.md)

Current firmware adds 38 adaptation families and a separate local-knowledge path.
See [the upgrade report](REPLY_UPGRADE.en.md) for the new checkpoint SHA, scores
and caption mapping. LM measurements and SHA below describe the parent model.

Weights and downloaded corpora are not bundled. The deployed BPE candidate uses
the following lineage; training-only teachers do not run on the microcontroller.

| Asset | Role | Pinned revision / terms |
| --- | --- | --- |
| [Moonshine Tiny Japanese](https://huggingface.co/moonshine-ai/moonshine-tiny-ja) | STT encoder initialization; six layers, decoder replaced with 41-symbol phoneme CTC | `02ca41b3d9e73db07df9a13f316f2b7497a368e2` / Community License |
| [Google FLEURS](https://huggingface.co/datasets/google/fleurs) | Japanese training split, about 6.69 hours / 2,164 utterances, automatic phoneme labels | `70bb2e84b976b7e960aa89f1c648e09c59f894dd` / CC BY 4.0 |
| [LLM-jp OASST1 Japanese](https://huggingface.co/datasets/llm-jp/oasst1-21k-ja) | Kana language pretraining | `f05b5816a8c1ce8c1f5ae3cd87ae5a7b6409fea5` / Apache-2.0 |
| [RealPersonaChat](https://github.com/nu-dialogue/real-persona-chat) | BPE/dialogue/semantic-distillation text | `28d0b6b3865b29cabc26c230a2db37cdf315e937` / CC BY-SA 4.0 |
| [Qwen3-4B-Instruct-2507](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507) | Local PC teacher generating candidate paraphrases of authored questions | `cdbee75f17c01a7cc42f958dc650907174af0554` / Apache-2.0 |
| [multilingual-e5-small](https://huggingface.co/intfloat/multilingual-e5-small) | Local PC input-representation distillation | `614241f622f53c4eeff9890bdc4f31cfecc418b3` / MIT |
| [sanoTTS-jp](https://github.com/ayutaz/sanoTTS-jp) | Externally downloaded v4 INT8 TTS, not retrained here | Code `f427b1e6bf743965c9b033d43fdf84b56f8f7543` / MIT; weights have separate terms |

Authors, papers and transformations are recorded in the [STT notice](../licenses/NOTICE-Moonshine.txt),
[dialogue notice](../licenses/dialogue-data-NOTICE.md), and [TTS notice](../licenses/sanoTTS-jp-NOTICE.txt).
Sarashina2.2-3b-instruct-v0.1 was a teacher-audit pilot, not an automatically accepted
answer source or an on-device model. Speaker profiles/IDs were discarded.
User conversations and private recordings are not training data; STT outputs were
not used to train the reply LM.

## Reply model pipeline

Kana conversion → 1,024-token BPE → language pretraining → E5 representation
distillation → short daily-dialogue tuning. There are 114 authored families,
286 original questions and 336 reviewed teacher paraphrases: 622 distinct questions.
Prefix/suffix expansion yields 14,928 rows, NOT 14,928 independent meanings.
Final answers are authored short replies. Review was by the coding agent, not
an external human evaluation. Runtime generates tokens without a reply lookup
table or retrieval database, but answer memorization remains strong.

| Evaluation | Result and caveat |
| --- | --- |
| STT tuning subset | 64 dev clips; best FP32 PER 13.57%, optimized W8A8 PER 14.49%; not kanji CER |
| LM canonical prompts | 114/114 exact; known meanings and answers |
| LM wording-dev | 85/137 exact; held-out wording within known meanings, used for selection |
| Post-selection challenge | Agent rated 21 pass / 4 partial / 15 fail among 40; not general conversation accuracy |
| Device parity | 32/32 match native C output; does not establish semantic correctness |

Device LM SHA256: `985505b6abfe3504ccadd6b535a48a87e8a48ebb61183af0e9d8305cf5ef26e7`.
TTS SHA256: `a1eb6b0812e2ad2a228836088a3e34160cb66731492fb957a5891605db2fa1b6`.
STT hashes are in export manifests. Seeds do not guarantee bit-identical training
across CUDA/software versions. See [reproduction](REPRODUCE.en.md) and the
[detailed experiment commands](../tiny_lm/DIALOGUE_EXPERIMENTS.md).

Current dialogue weights/tokenizer remain on hold for distribution because of
RealPersonaChat-derived stages and unresolved weight-licensing interpretation.
Fine-tuning does not erase provenance. A less restricted lineage would require
rebuilding the tokenizer and initializing/training weights from cleared sources.
The UsefulSensors reference audio has no explicit license in its card; it is
neither bundled nor used as training data.
