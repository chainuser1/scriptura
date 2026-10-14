# Third-party notices

Scriptura is published by Scriptura Labs under the MIT licence (see LICENSE). The app bundles or downloads the following. Each keeps its own licence; follow the upstream licence text for exact terms.

## Models and data

| Component | Use | Licence |
|---|---|---|
| BGE-M3 (BAAI/bge-m3), pinned revision 5617a9f6 | query encoder (INT8 dynamic quantization of the ONNX export) and tokenizer | MIT |
| Scripture Genome head (question-hidden4096), trained by the project (Scriptura Labs) | maps a question to the 568-gene space | project terms (see the model card) |
| Bible text (Genesis to Revelation): King James Version and the other languages' translations | reading and exact-phrase search | public domain |
| Book of Mormon, Doctrine and Covenants, Pearl of Great Price, all languages (verses 31,103 to 41,995) | reading and exact-phrase search | licence and copyright belong to The Church of Jesus Christ of Latter-day Saints, © Intellectual Reserve, Inc.; use is subject to the Church's terms and not covered by this project's licence |

## Runtime libraries

| Component | Use | Licence |
|---|---|---|
| ONNX Runtime | runs the encoder (bundled on Windows, `libonnxruntime.so` on Android) | MIT |
| Flutter and Dart SDK, and the pub packages in `pubspec.lock` | app framework | BSD-3-Clause (packages carry their own, mostly BSD or MIT) |
| SQLite (via the `sqlite3` package and `rusqlite`) | local databases and FTS5 | public domain |
| Rust crates (`tokenizers`, `ort`, `rusqlite`, `memmap2`, `half`, `zip`, `regex`, `serde`, and others in `engine/Cargo.lock`) | native engine | MIT and/or Apache-2.0 |

## Fonts

| Font | Use | Licence |
|---|---|---|
| Inter | interface | SIL Open Font License 1.1 (`assets/fonts/Inter-LICENSE.txt`) |
| Source Serif 4 © Adobe | scripture text | SIL Open Font License 1.1 (`assets/fonts/SourceSerif4-LICENSE.md`) |

The Loos typeface from the owner's brand kit is **not** bundled.
