# Search and study engine: completion plan

Written 2026-10-13. Companion to [PLAN.md](../PLAN.md) (sections 4, 6, 8, 10, 11, 12) and [DATA_SOURCES_PLAN.md](DATA_SOURCES_PLAN.md). Owner direction: finish the engine completely, then make the Windows and Android apps usable end to end for someone studying the scriptures.

This is a milestone-level plan with acceptance gates. Each milestone gets its own bite-sized, test-first task plan when it starts (as DATA_SOURCES_PLAN did), because the early milestones decide interfaces that later tasks depend on.

## 1. What "engine complete, lacking nothing" means

The engine is complete when one native library, driven identically from Windows x64 and Android arm64, provides every capability below, offline, deterministically, with measured quality and speed, and nothing else is needed to build the app screens.

| # | Capability | Contract |
|---|---|---|
| C1 | **Semantic search** (genome-heavy fusion of dense + sparse + genome, with ColBERT as an optional extra; fusion is configuration, not code) | PLAN 6.1-6.3 as amended by the 2026-10-13 evaluation below; filters per `docs/SEARCH_SPEC.md`; top 20 by default |
| C2 | **Phrase search** (model-free) | FTS5 per served language over the shipped text; case-insensitive consecutive words, accents preserved, no stemming or implicit OR (PLAN 6.4) |
| C3 | **Reference parsing and resolution** | "John 3:16", "Jn 3:16-18", "Salmos 23", "D&C 64:7", ranges across chapters; uses the catalog's per-language aliases; ambiguity returns candidates, never a guess |
| C4 | **Similar verses** | Stored-genome similarity with a named profile; excludes the source verse; labeled as not Experiment D (PLAN 6.4) |
| C5 | **Filters** | Volume, book, chapter and arbitrary verse-ID sets applied before each lane |
| C6 | **Lifecycle** | Lazy load, preload, unload; cancellation between stages; request IDs; stale-response discard; one in-flight request policy |
| C7 | **Identity and caching** | `configurationId` over base revision, tokenizer, encoder, head, index, fusion and filter hashes; cache keys per PLAN 10 |
| C8 | **Diagnostics** | Per-stage times, candidate and token counts, actual precision and provider; compact in release builds |
| C9 | **Errors** | Distinct codes: missing pack, incompatible version, corruption, invalid or over-512 input, insufficient resources, inference or index failure, cancelled |
| C10 | **Quality and speed evidence** | Gates in section 4, on this PC and on the V29 |

Everything else (reading, notes, highlights, languages, settings) is the application layer, not the engine.

## 2. Where we stand

| Piece | State |
|---|---|
| Experiment D reference (Python) | Done. Reproduces the packaged validation inside its intervals; filters and edge cases specified and tested |
| Encoder export and quantization | FP32 ONNX exact-parity; INT8 variants built and screened; **ranking gate running** |
| ColBERT token pack | Built: 41,995 rows, 1,625,561 vectors, FP16 3.33 GB. INT8 token storage **not yet evaluated** |
| Tokenizer | 40 golden cases; native binding not built |
| Catalog and content DB | Done (KJV text, 5 languages, per-language names and aliases) |
| Similar verses, phrase search, reference parser, configuration identity | **Reference implementations done 2026-10-13** (`tool/similar_verses.py`, `phrase_search.py`, `reference_parser.py`, `config_identity.py`; checks and goldens in `test/engine_capabilities_check.py`, `test/golden/engine_capabilities.json`). Round trip: all 209,975 reference strings across five languages parse back to their own verse ID |
| Native engine, FFI, Dart service | **Not started** |
| Android toolchain, V29 benchmark | Not started (no Rust, NDK, SDK or adb installed) |

## 2b. Stores the engine reads (measured 2026-10-13)

| Store | Format | Size | Notes |
|---|---|---|---|
| Dense | FP16 `[41995, 1024]` | 86 MB | exhaustive scan, normalized |
| Genome (weighted) | FP16 `[41995, 568]` | 48 MB | genome lane and similar verses; the stored `scripture_vectors` copy was dropped from the shipped DB |
| Sparse | CSR (1,156,270 non-zeros) | 4 MB | convert to term-major postings for the native build |
| ColBERT pack | FP16 shards, CLS dropped | 3.33 GB | INT8 storage (about 1.7 GB) pending its quality gate |
| Encoder | INT8 ONNX (`matmul_gather` variant) | 0.57 GB | |
| Head | FP16 matrices | 13 MB | native matrices |
| Phrase index | FTS5 per language | 17.5 MB | text index, not an embedding |
| Content / catalog | SQLite v2 | 42.1 MB / 0.2 MB | see DATA_SOURCES_PLAN Task 6c |

Optional embeddings queued by the owner (2026-10-13), each to be kept only if it improves the wording-robustness
set (`tool/query_robustness_set.json`): 3-verse window dense embeddings (about 86 MB; hours of CPU), per-language dense
embeddings for Spanish, Tagalog, Cebuano and Greek (about 86 MB each; hours each), and a review of the question
vectors already in `questions_genome.db`. They are experiments, not requirements; builds are resumable and run after
the evaluations so they do not compete for the CPU.

## 2c. Fusion decision from the evidence (2026-10-13)

Two independent evaluations on the INT8 query encoder, same candidate union, paired intervals over questions or intents:

| Method | 250-question benchmark Recall@10 | nDCG@20 | Wording set hit@10 (192 queries) | ColBERT |
|---|---|---|---|---|
| Experiment D as designed (28/14/28/30) | **0.068** | 0.081 | 0.43 | yes |
| 90% genome + 10% dense | 0.143 | 0.165 | 0.41 | no |
| **Lean `g80_nocol`**: dense .10, sparse .10, genome .80 | 0.142 | 0.166 | 0.43 | no |
| 75% genome, Experiment D text proportions | 0.143 | 0.169 | 0.45 | yes |
| **Full `blend_g80`**: dense .05, ColBERT .15, genome .80 | 0.142 | 0.166 | **0.47** | yes |
| 60% genome, ColBERT-heavy `blend_g60` | 0.118 | 0.139 | 0.51 | yes |

- Experiment D as designed is clearly worse than every genome-heavy alternative on the labeled benchmark (Recall@10 -0.075, interval -0.093 to -0.058) and not better on the wording set. It should not be the default.
- The two evaluations pull in opposite directions beyond about 75% genome: the labeled benchmark's answers come from the same process that trained the genome and rewards genome weight; the wording set (anchors authored by the assistant, not independently reviewed) rewards text signals that find well-known verses. 70-80% genome is the only band near the top of both.
- ColBERT at a small weight is a modest, statistically clear gain on the wording set (`blend_g80` minus `g80_nocol` = +0.036, interval +0.010 to +0.068) and free on the benchmark (-0.001, not significant). It costs 3.3 GB (1.7 GB if INT8 token storage passes) and about 150-200 ms per query on this PC.
- Sparse adds nothing measurable over 90:10 on either set; it is cheap (4 MB) and kept for lexical queries and phrase-like input.

**Decision (superseded by 2c-ii and 2c-iii):** the Lean default proposed here was withdrawn; the default is **Compass**. Fusion weights live in configuration and are part of `configurationId`. The default may move after a human-judged evaluation (PLAN 12.1: at least 100 independently reviewed intents).

### 2c-ii. Correction after user-style intent testing (2026-10-13)

The "Lean g80_nocol default" above was chosen from aggregate sets and is **withdrawn**. Testing real user-style queries (`tool/intent_test_set.json`, `tool/demo_queries.py`) showed that genome-heavy weights lose names, stories and keyword lookups, and that no single fixed weighting wins every intent.

| Profile (dense/sparse/ColBERT/genome) | Comparison both@10 | Definition hit@10 | Story hit@10 | How-to hit@10 | Person right@10 | Benchmark R@10 | Wording hit@10 |
|---|---|---|---|---|---|---|---|
| Experiment D (.28/.14/.28/.30) | 0.56 | 0.67 | 1.00 | 0.50 | 0.54 | 0.068 | 0.43 |
| genomic (0/.10/.20/.70) | 0.46 | 0.50 | 1.00 | 0.83 | 0.30 | 0.136 | 0.50 |
| lean g80 (.10/.10/0/.80) | 0.36 | 0.50 | 0.83 | 0.83 | 0.12 | 0.142 | 0.43 |
| **balanced B1 (.15/.10/.25/.50)** | 0.56 | 0.67 | 1.00 | 0.83 | 0.53 | 0.105 | 0.48 |
| balanced B2 (.10/.10/.20/.60) | 0.53 | 0.67 | 1.00 | 0.83 | 0.47 | 0.125 | 0.51 |
| balanced no-ColBERT (.25/.15/0/.60) | 0.55 | 0.67 | 1.00 | 0.83 | 0.47 | 0.120 | 0.46 |

- Intent sets are small (6-9 queries per family) and assistant-authored; read them as direction, not proof.
- **Fixed default: balanced B1 or B2** (genome .50-.60, ColBERT .20-.25, dense .10-.15, sparse .10). Best two-signal duo: genome .85 + ColBERT .15. Without the ColBERT pack, balanced no-ColBERT is nearly as good.
- Weight routing by query regex or score peakedness did not beat a fixed balanced profile on aggregates (peakedness AUC ~0.6); an A24 definition boost hurt.
- Mechanisms that do help, because they change *what is matched* rather than the weights: entity linking for named people (right@10 0.81 vs 0.12-0.54), concept-wise soft-AND for comparisons (both@10 0.69 vs 0.36-0.56), phrase mode for quotations.
- Entity-linker gating is implemented in `tool/entity_linker.py` (checked by `test/entity_linker_check.py`, 22 cases): people with fewer than 8 tagged verses are ignored, generic people (over 5% of the corpus: Jesus Christ, God the Father) are recognised but never used as a filter, same-name people are separated by id-slug and qualifier words (English, Spanish, Tagalog, Cebuano, Greek table), the first-named person wins, and a namesake with at least 3x the verses wins a bare-name question while the other is offered as an alternative. Measured on 15 person questions: right-person share of top-10 0.93 (other same-name person 0.03), against 0.81 before gating; Experiment D 0.62. Compact `entities.db` export is 1.1 MB for 521 people, machine-generated and unreviewed, so it is not part of the release until the rights and quality review.
- Still required before E1 locks the default: visible interpretation chips so users can correct a wrong reading, and the human-judged pooled evaluation (PLAN 12.1). Known limit: Bible names that differ by language (Moisés, Santiago) are not matched yet.

### 2c-iii. Search profiles (owner-approved 2026-10-13)

All mixes stay available as named profiles; **Compass is the default**. Registry: `tool/data/fusion_profiles.json` (checked by `test/fusion_profiles_check.py`).

Signals: **Echo** = dense (meaning), **Spark** = sparse (exact words), **Thread** = ColBERT (word by word), **Root** = genome (topic, form, tone).

| Profile | Echo | Spark | Thread | Root | Was | Use |
|---|---|---|---|---|---|---|
| **Compass** (default) | .10 | .10 | .20 | .60 | balanced B2 | best all-rounder |
| Wayfarer | .15 | .10 | .25 | .50 | balanced B1 | names and definitions |
| Lantern | .25 | .15 | 0 | .60 | balanced no-ColBERT | automatic fallback without the ColBERT pack |
| Chorus | .28 | .14 | .28 | .30 | Experiment D | validated reference |
| Tide | 0 | .10 | .20 | .70 | genomic | topic and feeling |
| Feather | .10 | .10 | 0 | .80 | lean g80 | smallest and fastest; never default |
| Gemini | 0 | 0 | .15 | .85 | best duo | genome plus ColBERT |

- Profiles that need Thread are unavailable (greyed out) until the ColBERT pack is installed; the engine then falls back to Lantern.
- Profile choice sits under an Advanced search setting; the interpretation chips (person, comparison, phrase) are separate and always visible.
- The chosen profile id is part of `configurationId`, so results are reproducible.

## 3. Architecture (recommendation, needs owner confirmation)

**One Rust crate, `scripture_engine`, behind a narrow C ABI called from Dart FFI.**

- `tokenizers` (the official Hugging Face core) so token IDs match the goldens by construction; no handwritten tokenization.
- ONNX Runtime through a Rust binding, CPU provider first (INT8 encoder; head as native matrices).
- Native kernels for dense, genome and sparse scans (deterministic top-k with ascending verse-ID ties), mapped ColBERT pack reads and MaxSim, z-score fusion.
- `rusqlite` with bundled SQLite for FTS5 phrase search.
- Pure functions for fusion and parsing, tested without a model.

Why Rust over the plan's C++ plus a Rust tokenizer: one toolchain instead of two for tokenizer plus kernels, memory safety around mapped files and buffers, simple cross-compiling to `aarch64-linux-android` and `x86_64-pc-windows-msvc`, and a smaller C ABI surface to audit. The cost is a less-trodden path for ONNX Runtime on Android, which is milestone E3's first spike. If that spike fails, the fallback is C++ for ORT and kernels with the same C ABI; milestones E0-E2 do not change.

Alternatives considered: the existing Dart `onnxruntime` package plus a Dart tokenizer (rejected: tokenizer fidelity and large-array performance on the UI isolate side), a separate Python service (rejected: not shippable), cloud inference (rejected by PLAN 1.8).

**Interface** (PLAN 11, extended):

```text
SemanticRequest(query, filter, topK, requestId)
PhraseRequest(phrase, language, filter, topK, requestId)
SimilarVersesRequest(verseId, filter, topK, requestId)
ReferenceRequest(text, language) -> list of candidate (verse range | chapter | book)
SearchResponse(requestId, rankedVerseIds, diagnostics, configurationId)
```

The engine returns IDs and scores only. Text, references and localization come from the repository and catalog, so display language and edition changes never touch engine caches.

## 4. Milestones and acceptance gates

### E0 Close the reference and the open decisions (Python, no new toolchain)
- **INT8 gate: run 2026-10-13** on the 250-question, 8-language sample with the real ColBERT pack (`tool/eval_quantized.py`, `test/golden/quantization_eval.json`). Overall result: Experiment D Recall@10 -0.04% (`matmul_gather`) / +0.58% (`matmul`) and NDCG@20 -0.72% / -0.46% against FP32, inside the 2% rule; the 90:10 blend -2.6% / -1.8% (`gather`) and -1.3% / -1.8% (`matmul`), all inside the paired 95% interval except where noted. The literal per-language 5% relative rule fails mechanically (worst -8.8% `gather`, -17.3% `matmul`) because baselines are tiny (Cebuano Recall@10 0.029) and the absolute shifts are noise; paired per-language intervals show `matmul` has no significant negative difference in any language or metric, while `matmul_gather` has a few small significant drops (Spanish and German NDCG, French Recall@10 on 90:10). Decision pending the owner: `int8_matmul` (1.37 GB, quality indistinguishable from FP32) vs `int8_matmul_gather` (0.57 GB, small risk in accented Latin-script languages). The PLAN 12.1 gate should be restated as a paired absolute-difference test, not a per-language relative percentage.
- Evaluate **INT8 token storage** for the ColBERT pack (per-token scale; MaxSim ranking against FP16) and decide 1.7 GB vs 3.3 GB. Same gate.
- Implement and test in the reference: **phrase search** (FTS5 index builder over the shipped text per language, escaping, Unicode, empty and operator cases), **reference parser** (aliases from the catalog, ranges, ambiguity), **similar verses** (named profile, golden outputs).
- Define `configurationId` and the cache-key rules as code, with tests.
- **Gate:** every capability C1-C5, C7 has a reference implementation with committed goldens, and the two precision decisions are recorded with evidence.

### E1 Native core on Windows x64
- Tokenizer parity: all 40 goldens, byte-identical IDs. **Passed 2026-10-13** (`engine/tests/tokenizer_parity.rs`, tokenizers crate pinned to 0.22.2 like the Python reference, pinned tokenizer.json verified by hash).
- Encoder parity: dense cosine at least 0.9999 versus the matching ONNX reference output; sparse token sets identical; ColBERT within tolerance. **Passed 2026-10-13** on 8 multilingual queries with the INT8 `matmul` graph through the `ort` crate (2.0.0-rc.14): dense cosine 1.000000, sparse token sets identical (max weight difference 0), ColBERT minimum token cosine 1.000000 (`engine/tests/encoder_parity.rs`).
- Kernels and fusion: top-20 IDs for the 6 golden queries equal the Python reference for the same precision; on the 250-question sample, Recall@10 and NDCG@20 within 0.002 of the reference run for the same encoder. **Top-20 part passed 2026-10-13:** 12 queries x 7 profiles, identical verse IDs, scores within 1e-3, equal candidate counts (`engine/tests/fusion_parity.rs`, reference `tool/make_fusion_goldens.py`). The 250-question metric sample is still to run natively.
- Deterministic ties, bounded scratch memory, no per-query allocation spikes, cancellation checkpoints between stages (C6).
- **Gate:** parity above, plus warm semantic median at most 3 s and p95 at most 6 s on this machine (which is slower than the target phone class), recorded with the hardware. **Latency measured 2026-10-13 (this PC, 1 encoder thread, Compass with ColBERT, 12 queries):** warm median 239 ms, max 294 ms, encode plus search; index open 0.2 s warm cache.

**E1 status (2026-10-13):** native phrase search, reference parsing (all 41,995 verses x 5 languages round-trip), similar verses, gated entity linking (shared word lists in `engine/data/entity_linker_words.json`), configuration identity and cache keys (byte-identical to the Python reference), profile fusion with eligibility filters and cancellation checkpoints, and the JSON-over-C ABI (`engine/src/capi.rs`: `se_open`, `se_request`, `se_cancel`, `se_close`, `se_free_string`) are implemented and parity-tested (`engine/tests/*`). The 250-question metric sample has not been run natively; top-20 identity on 12 queries x 7 profiles is the stronger per-query evidence collected instead. Bounded scratch memory is by construction (candidate union at most 600 rows, ColBERT scratch of one passage); a measured memory budget comes with the E3 device benchmark.

### E2 Dart integration and Windows usable search
- FFI binding, a worker isolate, `SearchService` interface with `UnavailableSearchService` for missing packs, request IDs and stale-result handling.
- Search UI states: preparing, searching, cancelled, error with specific message, results with localized reference, KJV text, context.
- **Gate:** offline end-to-end on Windows after process restart: semantic, phrase, reference jump, similar verses, filters, cancellation; widget and integration tests; no network access.

**E2 status (2026-10-13):** implemented and tested. `lib/services/engine/` (FFI binding, worker isolate with request IDs and cancellation, `SearchService`, `UnavailableSearchService`, pack store with hash-verified install), `lib/app_controller.dart` (content plus engine lifecycle), `lib/reader_mode/screens/engine_search_screen.dart` (preparing, searching, cancelled, error with reason, empty, results, reference card, person chips, filters by volume, similar verses, fallback disclosure), `data_screen.dart` (import and status). Tests: 12 search widget tests with a scriptable fake, 6 pack-store tests, 9 native-engine integration tests, and `restart_e2e_test.dart` (install release, search every mode, restart on the same data directory, search again; no network). Windows release build bundles `scripture_engine.dll` and launches. `tool/build_engine_pack.py` assembles the 1.53 GB engine pack.

### E3 Android arm64 and the V29 spike
- Toolchain: Rust targets, NDK, ONNX Runtime Android libraries, mapped files from app storage (never `pubspec` assets).
- **Gate:** warm semantic median at most 3 s, p95 at most 6 s, cold semantic-ready at most 15 s, whole-process peak at most 2 GB (PLAN 12.2), 20-minute session without thermal kill or crash; results identical to Windows for the golden queries.
- If it fails: report measured options (INT8 ColBERT, smaller candidate budget as an explicit versioned configuration); never silently remove a signal.

**E3 status (2026-10-13):** Android toolchain installed (JDK 17, SDK 36, build-tools 36.0.0, NDK 28.2.13676358, platform-tools); `rustup target add aarch64-linux-android`. `tool/build_engine_android.py` cross-compiles the engine (`--no-default-features --features dynamic-ort`) and stages `libscripture_engine.so` (9.4 MB, exports `se_*`, depends only on libc/libm/libdl) with ONNX Runtime 1.31.0 from the official onnxruntime-android AAR (34 MB) into `android/app/src/main/jniLibs/arm64-v8a`; the app is arm64-v8a only. A side-load path (`dev-packs/` in the app's external files directory) and an auto-run benchmark (`dev-packs/run-benchmark` -> `benchmark.json`) exist for the device gate; `tool/android_device_run.py` installs, pushes the packs and prints the gate summary. **V29 gate measured 2026-10-14 (vivo V2250, Android 15, arm64, 11.5 GB RAM, release APK, real FP32 encoder + ColBERT pack):** compass (default): warm median 195 ms, p95 465 ms, cold first query 700 ms, peak RSS 1,729 MB; lantern (no ColBERT): median 118 ms, p95 128 ms, cold 123 ms, RSS 1,718 MB; phrase 8 ms, similar 8 ms. All four gates pass (median <= 3 s, p95 <= 6 s, cold <= 15 s, RSS <= 2 GB); RSS has the least headroom (about 320 MB). Note for side-loading: files pushed by `adb` are only readable by the app when world-readable, so `android_device_run.py` runs `chmod -R a+rwX` on dev-packs; the result file is written to the app's files directory, not dev-packs.

### E4 Hardening
- Fuzzed queries (empty, 512-token limit, emoji, mixed script), concurrent and rapid-fire requests, low-memory and background behavior, corrupted or truncated packs, version mismatch between catalog, content DB and indexes.
- Golden parity run as a single command (CI-style) covering Python reference, native engine and both platforms.
- **Gate:** the "lacking nothing" checklist in section 1 is fully ticked with links to tests.

## 5. What comes after the engine (not planned here yet)

User data (`user.db`: bookmarks, notes, highlights, reading position), the study experience (chapter reader, verse selection and context, side-by-side translations because all languages share verse IDs, history), settings and accessibility, first-run install and import, interface localization for the five languages, Windows and Android packaging and signing, then the release host and downloader (Hugging Face, deferred by the owner).

## 6. Decisions and prerequisites

| # | Decision | Recommendation |
|---|---|---|
| D11 | Engine implementation language | Rust, with C++ as the documented fallback |
| D12 | ColBERT | Optional enhanced pack, not required: without it the engine uses the Lantern profile; precision FP16 (3.3 GB) until INT8 token storage passes its gate |
| D13 | Android scope | arm64-v8a only, Android 13+, V29 as the first device (PLAN 1.5) |
| D14 | Installing toolchains | Rust (rustup), then Android SDK, NDK and platform-tools; the V29 connected with USB debugging at E3 |

## 7. Risks

1. **ONNX Runtime on Android through Rust** is the least proven link. Mitigation: spike first in E3, keep the C ABI stable so C++ can replace the core.
2. **Memory on the phone.** The mapped ColBERT pack is read-heavy; page-cache behavior and the 2 GB budget are measured, not assumed.
3. **Latency of 600-candidate MaxSim.** About 100-200 ms per query measured in Python on this PC; kernels should be faster, but the phone is unmeasured.
4. **Scope creep into the app.** The engine gate list above is the boundary; UI polish waits for E2.
