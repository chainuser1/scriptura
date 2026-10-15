# Scriptura

Published by **Scriptura Labs**. Author: Jayson Rael Ramos.

An offline scripture reader for **Windows** and **Android** with search by meaning. A native Rust engine runs a multilingual
embedding model and a 568-gene "scripture genome" fingerprint on your own device: no account, no server, nothing about you
is sent anywhere.

The app is a Flutter UI over that engine. On first run it downloads its scripture text and search data once, verifies every
file, and then works entirely offline.

## What it does

- **Read** the standard works in five languages (English, Spanish, Tagalog, Cebuano, Greek) with parallel reading,
  bookmarks, highlights, notes and a reading position.
- **Search by meaning**: ask a question the way you would ask a person. Results combine four signals the project names
  Echo (embedding), Spark (exact words), Thread (word-level matching, optional) and Root (the genome). The mix is a
  setting; **Compass** is the default.
- **Exact phrases**, **references** ("John 3:16", in five languages) and **similar verses**.
- **Trails**: start from a verse, a question or one of eight starters and read an endless stream of related verses,
  steered by Like, Skip and Less like this, with the reason under every verse. Learning stays on your device.
- **People, places and groups**: "Who is Captain Moroni?", "Where is Bethlehem?" are understood, and the app shows what
  it understood.
- **Study questions** a passage speaks to, a story page, accessibility (keyboard, screen reader, contrast, text size).

## How it is built

```
lib/                 Flutter app (adaptive Windows/Android shell, reader, search, study, settings)
engine/              Rust crate: tokenizer, ONNX encoder, fusion search, phrase and reference parsers, C ABI
tool/                Python tooling: build the data packs, evaluate search, audit quality, package releases
test/                Dart tests, golden data and Python checks (engine parity against a Python reference)
installer/           Inno Setup script for the per-user Windows installer
docs/                plans, specs, data-source rules and the engineering log
```

Search runs in a worker isolate through a JSON-over-C-ABI boundary. The Rust engine is verified against a Python
reference with golden files, so changes cannot silently change results.

## The data is not in this repository

Scripture text, model weights and search indexes are large and have their own licences, so they are **never committed**.
The app fetches them from a public bucket listed in `lib/app/hosting.dart` (`kDefaultDataAddress`); each download is checked
against SHA-256 values in the bucket's `index.json`. See [docs/ARTIFACT_LAYOUT.md](docs/ARTIFACT_LAYOUT.md) for what each pack
contains and how it is produced.

**Scripture text and its terms.** The Bible text (Genesis to Revelation, verses 1 to 31,102) is in the public domain: the
King James Version in English and public-domain translations in the other languages.

> **The licence and copyright of the Book of Mormon, Doctrine and Covenants and Pearl of Great Price belong to The Church of
> Jesus Christ of Latter-day Saints** (© Intellectual Reserve, Inc.). They cover verses 31,103 to 41,995 in all five
> languages. Their use is subject to the Church's terms; this repository does not contain that text and its licence grants
> no rights to it (see [docs/DATA_SOURCES_PLAN.md](docs/DATA_SOURCES_PLAN.md)).

| Pack | What it is | Size |
|---|---|---|
| scripture content | verse text, catalog, exact-phrase index | 24 MB |
| engine pack | INT8 query encoder, tokenizer, genome head, indexes | 1.0 GB |
| entities | people, places, groups (names and verse ids) | under 1 MB |
| answers | study questions per passage | under 1 MB |
| word-level index (optional) | ColBERT token index for the Compass profile | 3.1 GB |

## Build

Prerequisites: Flutter (stable), Rust (stable, MSVC on Windows), and for Android the SDK/NDK and JDK 17. The Python tooling
needs the packages in `tool/` imports (numpy, scipy, Pillow, onnx/onnxruntime for packs).

```powershell
# engine (Windows) and its tests
cd engine; cargo build --release; cargo test --release; cd ..

# Windows app and installer
flutter pub get
flutter build windows --release
python tool/build_installer.py            # needs Inno Setup 6

# Android (arm64): engine library, then the APK
python tool/build_engine_android.py
flutter build apk --release --target-platform android-arm64
```

The tests that need the large generated artifacts skip themselves when those are absent. Run them all with
`flutter test --concurrency=2`; `SCRIPTURA_LIVE=1 flutter test test/integration/live_bucket_test.dart` additionally installs
everything from the real bucket (about 4 GB).

## Releases

Installers are published as GitHub releases with stable asset names, so these links always point at the newest one:

- Windows: `https://github.com/<owner>/<repo>/releases/latest/download/Scriptura-Setup.exe`
- Android: `https://github.com/<owner>/<repo>/releases/latest/download/Scriptura.apk`

How a release is staged and published: [docs/RELEASING.md](docs/RELEASING.md). The Windows installer is not code-signed yet,
so SmartScreen will warn on first run.

## Documentation

- [docs/EXPERIENCE.md](docs/EXPERIENCE.md): who the app is for and what each reader gets
- [docs/ENGINE_PLAN.md](docs/ENGINE_PLAN.md): the native engine, parity gates, device benchmarks
- [docs/SEARCH_SPEC.md](docs/SEARCH_SPEC.md): search behaviour and fusion profiles
- [docs/ARTIFACT_LAYOUT.md](docs/ARTIFACT_LAYOUT.md): where generated data lives and what is uploaded
- [docs/DEVLOG.md](docs/DEVLOG.md): engineering log, decisions and measurements
- [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md): models, fonts and libraries used

## Licence

The source code is released under the **MIT licence** (see [LICENSE](LICENSE)), © 2026 Scriptura Labs. The same licence covers the
project's own machine-generated data (the genome head, entity index and study questions), which is provided as is and may
contain errors. Third-party components keep their own licences ([THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)).

The licence of the code never extends to the scripture text: public-domain Bible text is free to use, and the LDS-licensed
volumes (Book of Mormon, Doctrine and Covenants, Pearl of Great Price) remain under their owner's terms.
