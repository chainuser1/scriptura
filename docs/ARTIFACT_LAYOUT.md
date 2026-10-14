# Where things live (final layout, 2026-10-13)

The project folder holds source, docs and small goldens only (about 0.8 GB with `.venv`, `.dart_tool` and Flutter's
generated `windows/flutter/ephemeral`, all regenerable). Everything large lives outside it.

## Originals (never modified, never moved)

`<projects>\scriptura\`

| Item | What it is |
|---|---|
| `application_databases/` | `scriptures_genome.db`, `questions_genome.db`, `scripture_genome_raw.db` (read-only inputs) |
| `bge-m3-pinned-*.zip`, `scripture-retrieval-english-v1.zip`, `scripture-genome-question-hidden4096-*.zip` | model, retrieval index, genome head archives |
| `app-backups/scriptures_reader_mobile-before-phase0-20261011/` | the complete pre-rebuild project; every legacy file removed from the project is byte-identical here |

## Artifacts root (generated, gitignored by being outside the repo)

`<projects>\scriptura\artifacts\` is reached from the project through directory junctions, so
every tool keeps its existing relative paths:

| Project path (junction) | Real location | Contents |
|---|---|---|
| `generated-artifacts/` | `artifacts/generated` | `release/` (content.db, catalog.db, phrase-index.db, manifest.json; production), `engine-pack/` (1.5 GB; production), `colbert-pack-v1/` (3.2 GB; optional production pack), `onnx-int8/` (encoder variants), `lds-view/`, `dist/` (arm64 APK), eval JSON |
| `.artifact-staging/` | `artifacts/staging` | `import-application-v1/extracted/` (unzipped inputs; rebuild by unzipping the originals), `import-application-v1/databases` (junction to the originals), `validation/` (cached evaluation signals), `entities.db` |
| `engine/target/` | `artifacts/cargo-target` | Rust build output |

## Hosting staging (what you upload)

`<projects>\scriptura\artifacts\hosting\` is written by `tool/prepare_hosting.py` (hard links,
no extra disk) and is the only place you need to upload from:

| Folder | Contents | Size | Status |
|---|---|---|---|
| `search-data/` | `engine-pack-v1/` (encoder, tokenizer, head, indexes, people index), `colbert-pack-v1/` (optional), `index.json`, `README.md` | 1.53 GB + 3.33 GB | contains no scripture text; ready once you accept the licence table in its README |
| `content/` | `application-v1+kjv/` (`content.db`, `catalog.db`, `phrase-index.db`), `index.json`, `README.md` | 60 MB | scripture TEXT: do not publish until the rights review (D9) |
| `PUBLISHING_CHECKLIST.md` | the steps, commands and cautions | | not for upload |

### The bucket (what the app downloads)

The app downloads by itself on first run from `kDefaultDataAddress` in `lib/app/hosting.dart`
(`https://huggingface.co/buckets/chainuser1/scriptura/resolve/`); there is no folder picker or download button. The
bucket root holds four files:

| File | Made by | Notes |
|---|---|---|
| `index.json` | `tool/make_bucket_index.py` -> `hosting/bucket/index.json` | lists each pack with its `archive` (zip name, size, SHA-256) and the files expected after unpacking |
| `engine-pack-v1.zip` (0.98 GB) | zipped from `search-data/engine-pack-v1/` | required for search |
| `colbert-pack-v1.zip` (3.07 GB) | zipped from `search-data/colbert-pack-v1/` | optional; the app fetches it too, so Compass is the default |
| `scripture-content-v1.zip` (24 MB) | `tool/make_bucket_index.py` -> `hosting/bucket/` | scripture TEXT, gated by D9: verses 1-31,102 (Bible) are public domain; verses 31,103-41,995 (Book of Mormon, Doctrine and Covenants, Pearl of Great Price, all five languages) are LDS-licensed text, so serving this file publicly needs the owner's permission or licence |
| `entities-pack-v1.zip` (0.2 MB) | `tool/build_entities_pack.py` then `make_bucket_index.py` | purified people, places and groups (names and verse ids; no text) |
| `answers-pack-v1.zip` (1.9 MB) | `tool/build_answers_pack.py` then `make_bucket_index.py` | study questions a passage speaks to, curated edges only; question texts are project-generated |
| `topics-pack-v1.zip` (0.8 MB) | `tool/build_topics_pack.py`, then `make_bucket_index.py --include-topics` | **not uploaded by default (rights, D9)**: topic numbers and weights from a Church-compiled index; sharper similar verses; human-judged nDCG@8 0.686 -> 0.798 |

The zip is downloaded with resume (Range), checked against the index SHA-256, unpacked by the engine library
(`se_extract_zip`, streaming, path-escape safe), size-checked against the index and installed; then it is deleted.
Side-loaded test data: `dev-packs/` in the app's external files directory (see `tool/android_device_run.py`); an optional
`dev-packs/data-address` file points the downloader at a test server.

Other finished products live in `generated-artifacts/dist/`: `Scriptures-Setup-1.0.0.exe` (Windows installer, 18 MB,
unsigned) and `app-release.apk`.

## Production artifacts (what ships)

1. `generated-artifacts/release/` content release: text for the served languages, catalog, phrase index.
2. `generated-artifacts/engine-pack/` search data: INT8 encoder, tokenizer, head, retrieval indexes, people index.
3. `generated-artifacts/colbert-pack-v1/` optional word-level index.
4. Native libraries: `scripture_engine.dll` (Windows bundle) and `libscripture_engine.so` with `libonnxruntime.so`
   (Android `jniLibs`, staged by `tool/build_engine_android.py`).

## Removed on 2026-10-13 (and how to get it back)

| Removed | Why it was safe | Recreate |
|---|---|---|
| staged zip copies, staged database copies (3.9 GB) | SHA-256 identical to the originals | unzip or use the originals |
| all legacy databases and models (1.36 GB, 36 files) | owner decision 2026-10-13; every file verified byte-identical in the phase-0 backup (`app-backups/.../assets/resources`) | copy from the backup; classes and rights notes stay in `docs/legacy_disposition.json` |
| `onnx-fp32/` (2.3 GB) | reproducible | `tool/export_onnx.py` (then `tool/quantize_onnx.py`) |
| ONNX Runtime Android AAR, Flutter `build/` | downloaded or built | `tool/build_engine_android.py`, `flutter build ...` |

## Rebuilding the layout on another machine

`python tool/setup_artifact_layout.py` (dry run) and `--apply` create the artifacts root and junctions and are
idempotent. The builders then regenerate each artifact: `tool/build_release.py`, `tool/build_engine_pack.py`,
`tool/build_colbert_pack.py`, `tool/quantize_onnx.py`, `tool/build_engine_android.py`.
