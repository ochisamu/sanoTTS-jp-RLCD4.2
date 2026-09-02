# Open JTalk provenance

The optional kanji profile compiles the 34 Open JTalk source files vendored by
the pinned sanoTTS-jp revision.

| Field | Value |
|---|---|
| Origin | Open JTalk (HTS Working Group / Nagoya Institute of Technology) |
| Imported from | `pyopenjtalk_plus-0.4.1.post9` sdist, `lib/open_jtalk/src` |
| License | Modified BSD; see `NOTICE-openjtalk.txt` |
| Upstream file count | 34 plus COPYING |
| sanoTTS combined-source SHA-256 | `572fc2b7341530ff56d9c415fdb7df41886ad9ed57e6975579cb3a4b644a5f43` |

The pinned sanoTTS-jp source makes one documented modification:
`jpcommon_label.c` changes `MAXBUFLEN` from 1024 to 256 to fit the ESP32-S3
memory budget. Its full provenance record is available at
`third_party/sanoTTS-jp/csrc/openjtalk/PROVENANCE.md`.
