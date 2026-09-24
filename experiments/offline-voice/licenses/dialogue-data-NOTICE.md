# Dialogue training assets (local research; not bundled)

The lab code license does not replace external data/model terms.
No downloaded corpus, teacher weights, student weights, participant metadata,
or generated dialogue corpus is committed. Cache contents must not be pushed.

## LLM-jp OASST1 Japanese

- Source: https://huggingface.co/datasets/llm-jp/oasst1-21k-ja
- Revision: `f05b5816a8c1ce8c1f5ae3cd87ae5a7b6409fea5`
- Declared license: Apache-2.0.
- Japanese DeepL translation of the English OpenAssistant subset, by LLM-jp.
- Authors listed on the data card: Hirokazu Kiyomaru, Hiroshi Matsuda, Jun Suzuki,
  Namgi Han, Saku Sugawara, Shota Sasaki, Shuhei Kurita, Taishi Nakamura,
  Takashi Kodama, Takumi Okamoto.
- Used for kana language pretraining. Teacher-generated QA pilots are separate
  experiments and are not automatically included in the human dialogue run.

## Qwen teacher

- Source: https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507
- Revision: `cdbee75f17c01a7cc42f958dc650907174af0554`
- Declared license: Apache-2.0. Original LICENSE and model card retained in cache.
- Local training-data generation only; not deployed on the ESP32 or used at run time.
- Pilot generation is not factual ground truth. Failed pilots are not training data.

## RealPersonaChat

- Source: https://github.com/nu-dialogue/real-persona-chat
- Revision: `28d0b6b3865b29cabc26c230a2db37cdf315e937`
- License: CC BY-SA 4.0, https://creativecommons.org/licenses/by-sa/4.0/
- Authors: Sanae Yamashita, Koji Inoue, Ao Guo, Shota Mochizuki,
  Tatsuya Kawahara, Ryuichiro Higashinaka.
- Citation: *RealPersonaChat: A Realistic Persona Chat Corpus with Interlocutors'
  Own Personalities*, PACLIC 2023, pp. 852–861.
- Public masked dialogues only. Speaker attributes, personality profiles, IDs,
  evaluations and timestamps are discarded. No participant identification,
  attribute inference, or imitation of an individual speaker is intended.
- Modifications: dialogue-level split, text filtering, automatic phoneme/kana
  conversion, adjacent-turn pairs, length limits and question deduplication.
- Treat prepared derivatives as CC BY-SA 4.0. Attribution and share-alike terms
  must be considered before publishing data or trained weights. This experiment
  does not assert that a trained derivative may be released under MIT.
- Local original LICENSE and source manifest: `.cache/realchat/`.

Private device recordings and the user's conversation are not training sources.

## Additional training-only teachers

- Japanese instruction audit: `sbintuitions/sarashina2.2-3b-instruct-v0.1`,
  revision `4f3626fb1b64b3e97c908e67f27b2d627ba2a999`.
  Source: https://huggingface.co/sbintuitions/sarashina2.2-3b-instruct-v0.1
  Declared MIT, SB Intuitions. Original LICENSE/model card retained in cache.
  Audit replies are not automatically training data and are not deployed.
- Semantic teacher: `intfloat/multilingual-e5-small`,
  revision `614241f622f53c4eeff9890bdc4f31cfecc418b3`.
  Source: https://huggingface.co/intfloat/multilingual-e5-small
  Declared MIT. Citation: Liang Wang, Nan Yang, Xiaolong Huang, Linjun Yang,
  Rangan Majumder, Furu Wei, *Multilingual E5 Text Embeddings: A Technical Report*,
  2024. Input-representation distillation only; not a runtime model or retrieval
  service. Vector targets derived from RealPersonaChat retain that corpus's
  separate terms.
- Reviewed daily question paraphrases use the pinned Qwen teacher with original
  authored seed questions. Generated answers from failed QA pilots are excluded.
  Final daily answers are original authored examples, not scraped replies.
