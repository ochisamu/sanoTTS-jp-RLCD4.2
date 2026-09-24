# Licenses and publication scope

[日本語](README.md) · [Home](../README.en.md)

Reviewed 2026-09-24. Provenance guidance, not legal advice or a warranty.
The [MIT license](../LICENSE) covers original lab code, not all assets below.

| Asset | Terms / preserved notices |
| --- | --- |
| STT weights | [Moonshine Community full text](Moonshine-Community-LICENSE.txt), [attribution and modifications](NOTICE-Moonshine.txt) |
| FLEURS | CC BY 4.0; authors/source/phoneme conversion in the STT notice; not bundled |
| LM data and teachers | [Pinned revisions and uses](dialogue-data-NOTICE.md); RealPersonaChat-derived weights on distribution hold |
| sanoTTS code | [MIT](sanoTTS-jp-MIT.txt), pinned submodule |
| sanoTTS v4 weights | [Model terms](sanoTTS-jp-model.md), [required notice](sanoTTS-jp-NOTICE.txt), [Apache text](sanoTTS-jp-Apache-2.0.txt) |
| Generated speech | [Voice rules](VOICE_TERMS.md), including restrictions and downstream obligations |
| CharaDock DSP | Apache-2.0, [notice](NOTICE-CharaDock.txt), [full text](waveshare-examples-Apache-2.0.txt) |
| Waveshare BSP | Apache-2.0, [source/modifications](rlcd-demo-NOTICE.md), same full text |
| Shinonome 16px | [Original terms](Shinonome-LICENSE.txt), [authors](Shinonome-AUTHORS.txt), [conversion provenance](Shinonome-NOTICE.md) |
| ESP-IDF / esp_codec_dev | [Dependency notice](DEPENDENCIES.md); audit all linked dependencies before binary releases |

## Publishable scope

Prepare source, reproduction instructions, original licenses, attributions, authored
tests and cleared aggregate results. Exclude model weights, learned tokenizer
artifacts, downloaded data, recordings, full-flash backups, build products and secrets.
Generated font tables are recreated locally from pinned, verified originals.

**Current LM weights and combined firmware releases remain on hold.** CC BY-SA is
not a non-commercial license; the unresolved issue is its application to this
particular trained lineage. Relabeling it MIT is not a solution. External downloads
or local training do not remove applicable terms.

Moonshine commercial use requires registration; annual revenue above USD 1 million
including affiliates requires separate licensing (read the complete agreement and
its exceptions). Preserve required notices, the agreement and prominent
`Powered by Moonshine AI` attribution. Follow the [AUP](https://moonshine.ai/use-policy),
including age conditions and no undisclosed recording. Restrictions on training
other foundational generative models are separate from inference use; this lab
does not train the reply LM using STT outputs.

Missing TTS v4 attribution and Apache text have been supplied. README files credit
the voice provider. Displaying kanji glyphs does not enable the optional Open JTalk
kanji-input dictionary; enabling that profile requires another dependency review.

`python tools/publication_check.py` checks artifacts and required notice files.
It does not provide legal clearance, complete dependency auditing or permission
to publish. See the [remaining publication checks](PUBLICATION_REVIEW.md).
