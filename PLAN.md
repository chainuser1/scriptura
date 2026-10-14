# Scripture Reader — implementation plan

Version 1.0 · Written and reviewed 2026-10-11 · Status (2026-10-13): Phase 0 complete except V29 device identity; Phase 1 complete (Python reference reproduces the packaged validation; see DEVLOG). Phase 2 desktop half done (ONNX export, INT8 quantization, ColBERT pack); the native engine is planned in [docs/ENGINE_PLAN.md](docs/ENGINE_PLAN.md) (milestones E0-E4, owner direction 2026-10-13: engine complete first, then the Windows and Android apps). Runtime/app implementation has not started. Earlier record: [Phase 0 baseline](docs/PHASE0_BASELINE.md).

This is the active plan for replacing the old search implementation with the selected Scripture Genome artifacts. It supersedes [the legacy plan](docs/archive/PLAN-legacy.md), old backend-parity requirements, and old deployment assumptions. It does not claim that the current scaffold implements this design.

Companion documents:

- [Artifact locations, verified inventory, and copy/import runbook](docs/ARTIFACT_HANDOFF.md)
- [Self-review, rejected assumptions, and unresolved decisions](docs/PLAN_REVIEW.md)
- [DEVLOG](DEVLOG.md): append implementation evidence for each completed milestone.

## 1. Purpose and fixed decisions

Build an offline scripture reader whose default search is **Experiment D: BGE-M3 dense + sparse + ColBERT + Scripture Genome**. Exact-phrase search is an explicit alternative, not an automatic hidden reranker. Results retrieve existing scripture text; this is not a generative answer model.

Decisions established with the owner:

1. Use the recent three application databases, not the app's older databases/search logic.
2. Use **question-hidden4096**, not the newer-looking 8192 or `both` experiments.
3. Preserve BGE-M3 as encoder. Evaluate deployment quantization before considering retraining or a smaller replacement encoder.
4. Windows must run fully offline after installation/import. A dedicated GPU and hosted service are not architectural requirements.
5. Android product target is Android 13+ on compatible hardware. First test phone: vivo V29, Snapdragon 778-series, 12 GB physical RAM, 8 GB extended RAM, Android 15, approximately 123 GB free storage as reported by the owner. Extended RAM is not part of our physical-memory budget.
6. Full offline Android Experiment D is the intended outcome, subject to measured feasibility. Do not silently replace it with dense-only retrieval when resources are insufficient.
7. Keep iOS-compatible boundaries, but defer a supported iPhone release until Mac build access and real-device testing exist. No iPhone is currently available.
8. No retraining, cloud inference, graph propagation, HNSW, query expansion, or online learning in the initial implementation.

OS compatibility does not guarantee performance. Publish tested hardware separately. Record the Windows test machine's CPU, RAM, disk, OS, and GPU availability during Phase 0; these are not yet established.

## 2. Findings from the current app

| Existing item | Observed finding | Action |
| --- | --- | --- |
| `lib/search_intelligence/pipeline/run_search_pipeline.dart` | Empty file | Implement a new integration; do not describe the pipeline as complete |
| `core/semantic/onnx_loader.dart` | Hashed unknown words, hardcoded special IDs, mean pooling | Replace with pinned tokenizer and normalized CLS contract |
| `core/semantic/embedding_loader.dart` | Old 768-dimensional embeddings and graph dependencies | Replace with 1024-dimensional dense and 568-dimensional genome assets |
| `database/loaders/database_initializer.dart` | Old remote artifact manifest | Replace; disable automatic old downloads |
| `reader_mode/` | Existing UI/provider scaffolding | Reuse only after compile, accessibility, and contract review |
| `pubspec.yaml` | Flutter/Riverpod, SQLite, ONNX wrapper dependencies | Qualify versions/platform support; package presence is not proof of working integration |
| Platform folders | Android present; Windows and iOS absent | Add target scaffolding in a checkpointed working tree |
| Git | App folder is not currently a Git repository | Back up and establish a code-only baseline before structural edits |
| Recent artifacts | Four serving ZIPs and three DBs found; outer hashes verified | Use the handoff allowlist, not a recursive copy of the artifact folder |
| Legacy resources | `assets/resources` holds old search DBs/indexes, a legacy encoder, extra editions and study aids; no user notes | Classify, quarantine, never load. Owner decisions (2026-10-13): English text is KJV, serve only complete languages, no Japanese. See [DATA_SOURCES_PLAN](docs/DATA_SOURCES_PLAN.md) |

Historical DEVLOG completion claims are not fresh verification. No Flutter build or device benchmark was performed to write this plan. Flutter/ADB were not found by the current shell's PATH check; verify/install the toolchain in Phase 0 rather than assuming it is absent everywhere.

## 3. Locations and authoritative identities

```text
APP_ROOT      <projects>\scriptures_reader_mobile
ARTIFACT_ROOT <projects>\scriptura
RESEARCH_ROOT D:\scriptures_pandora_genome_model
```

Settings inside the verified downloaded bundles are authoritative, not a hardcoded notebook default. Research code is reference material, not a second shipping runtime.

```text
Base: BAAI/bge-m3
Base revision: 5617a9f61b028005a4858fdac845db406aefb181
Head: question-hidden4096
Architecture: Linear(1024,4096), GELU, Linear(4096,568), Sigmoid
Checkpoint SHA-256: 5a68ef73167f48899c927dfb5e25dfe8ff50d0b8e8310cd6f3ff3c93b8bf9952
gene_ids.txt SHA-256: 16878f92a2f6434b39ef6d68c633f2cd815751f2b4be8767a309e32442baf195
Candidate corpus: 41,995 English passages
Reference FlagEmbedding version: 1.4.2
Reference maximum input: 512 tokens including special tokens
```

Hugging Face head repository: `chainuser1/Scripture_Genome_Multilingual_Head_BGE_M3`. Its head archives do not replace the separate base model or retrieval corpus. Pin remote release revisions and hashes when establishing distribution; do not make mutable `main` the production identity.

## 4. Architecture and ownership

```text
Flutter: reader / search / settings / downloads / personal library
                         │
Application services: typed requests, cancellation, language/display policy
          ┌──────────────┴──────────────────────────┐
          │                                         │
Content repositories                          Search engine worker
SQLite read-only content                      pinned native tokenizer
SQLite writable user data                     BGE-M3 + genome head
language-specific phrase index                dense/sparse/genome candidates
          │                                   ColBERT + Experiment D fusion
          └────────────────────┬────────────────────┘
                               │
                       canonical verse IDs
                               │
                   localized text + context + provenance
```

Responsibilities:

- **Flutter UI:** input, navigation, rendering, download consent, progress, accessibility. No inference or large numeric loops on the UI isolate.
- **Content repository:** typed SQL access, language fallback, book/chapter navigation, stable IDs.
- **User repository:** notes, highlights, bookmarks, settings, reading position, export/restore; separate from replaceable content.
- **Search engine:** tokenization, model execution, deterministic arithmetic, mapped index access, cancellation checkpoints, scores/IDs. No network fetching.
- **Artifact manager:** local import/download, verification, activation/rollback, optional-package lifecycle.

### 4.1 Technology choice and qualification

Retain Flutter and Riverpod. Prefer one native search engine with a narrow C ABI callable from Dart FFI and a test harness runnable without Flutter. Initial recommendation: C++ for ONNX Runtime/retrieval kernels, with the official Rust-based Hugging Face Tokenizers implementation behind a small C ABI. This tokenizer dependency is deliberate: do not replace it with approximate handwritten tokenization. Qualify Windows x64 and Android arm64 builds early; reuse a maintained bridge if it passes every contract instead of inventing another wrapper.

Pin ONNX Runtime, tokenizer, bridge, Flutter/Dart, NDK, and compiler versions after the spike passes. The old Dart ONNX package is not an automatic commitment. Establish one CPU path first; add hardware execution providers only if coverage, parity, memory, and speed improve on target devices. ORT recommends starting quantized mobile models on CPU and measuring device-specific acceleration. [ORT mobile guidance](https://onnxruntime.ai/docs/tutorials/mobile/)

Qualify one cross-platform SQLite access layer with bundled SQLite/FFI behind repositories; verify FTS5 on Windows and Android with compile options and an actual phrase query. Do not assume the existing mobile `sqflite` configuration covers desktop or every extension.

### 4.2 Proposed layout — not an existing implementation

```text
lib/app/                     bootstrap, navigation, lifecycle
lib/features/reader/         scripture/context screens
lib/features/search/         semantic and phrase search UI
lib/features/library/        bookmarks, notes, highlights
lib/features/downloads/      install/import/progress/recovery
lib/features/settings/       language, appearance, storage
lib/data/content/            three DB adapters, typed repositories
lib/data/user/               writable schema/migrations
lib/services/search/         requests, native bridge, result mapping
lib/services/artifacts/      manifest verification/activation
native/scripture_search/     model sessions, tokenizer bridge, math kernels
tool/                        offline validation/export/index builders
test/                        unit/repository tests, tiny synthetic fixtures
integration_test/            installed-pack/offline/lifecycle/UI tests
docs/                        decisions, contracts, benchmark evidence
.artifact-staging/            ignored local imports; never bundled app source assets
```

Implement behind the new interface, establish parity, switch callers, then remove unused legacy code in scoped commits. Do not ship both entire search stacks or delete personal data during cleanup.

## 5. Data design

### 5.1 Three source databases, initially unchanged

| File | Main tables | Purpose |
| --- | --- | --- |
| `scriptures_genome.db` | `scripture_vectors`, `scriptures_<language>`, `scripture_text_sources`, `language_coverage`, `database_metadata` | Text, references, shared verse features, coverage/provenance |
| `questions_genome.db` | `question_vectors`, `questions_<language>`, `question_metadata`, `collections`, `question_collections`, `question_targets`, `question_target_reviews` | Question browsing, suggestions, curated answer links |
| `scripture_genome_raw.db` | `verse_genome_raw`, `database_metadata` | Optional research/debug inspection |

Vectors are little-endian float32 BLOBs: 568 × 4 = **2,272 bytes**. Validate byte order, dimension, finiteness, and `[0,1]` range. They are not BGE dense embeddings. Raw keyed JSON scores are separate and cannot substitute for normalized vectors.

One semantic ID has one genome shared across translations. Match IDs explicitly; an arbitrary SQL row number is not an embedding row. `question_targets.verse_id` crosses DB files: validate references in the builder/app because a SQLite foreign key cannot enforce that cross-file relationship.

Questions support collections and explicitly labeled curated answers. They are not a hidden exact-match override to Experiment D and need not be installed for free-text semantic verse search. Adding question-neighbor retrieval to ranking would be a new experiment.

### 5.2 Language, editions, and navigation

Use the exported scripture tables, not machine-filled training translations. Exported coverage: English, Spanish, Tagalog, Cebuano, and Greek each have 41,995 passages; French 35,810; German 36,831; Hebrew 21,759. Coverage is not a certification of edition equivalence or redistribution rights.

- Resolve verse ID in the display-language table; if missing, show English with a visible fallback label. Never silently machine-translate missing text.
- Use supplied reference/shortened fields. Some localized tables still carry English canonical reference metadata.
- Read `scripture_text_sources` for the actual edition/source. A language table may contain mixed sources; do not label all English text as one edition.
- Build a stable canonical book-order/chapter catalog from reviewed metadata, not alphabetical sorting or `verse_id ± 1` assumptions.
- Compare retrieval JSONL text to English display text by ID. Differences require an explicit search-edition/display-edition policy; never overwrite source text to force equality.
- Whitelist language-to-table mappings; bind SQL values. Do not interpolate user-controlled table names.

Query and display languages are independent, but retrieval is not language-invariant. Version 1 searches the English index. Sparse overlap may be weaker cross-language. Displaying Tagalog after ranking English passages does not create Tagalog candidate retrieval. Later candidate-language packs need their own representations and evaluation.

### 5.3 Separate writable user storage

Create `user.db` with versioned migrations for bookmarks, notes, verse-level highlights, reading position/history, settings, and optional opt-in search history. Store canonical IDs and corpus/version identity. Later substring highlights also need edition/language and text anchors. Never reuse an old app integer ID until its mapping to the new corpus is verified.

Use SQLite backup or closed/checkpointed connections for backups; copying an active main DB while ignoring WAL files can lose changes. Migrations must be transactional and recoverable. Retain old user DBs until migration/review passes; unresolved IDs belong in a recoverable report, not the trash. No account, sync, or remote query logging is required in version 1.

## 6. Exact Experiment D contract

### 6.1 Tokenization and model outputs

1. Validate nonempty input. Preserve Unicode and case for the pinned tokenizer; do not apply old KJV spelling replacements or word hashing to semantic input.
2. Match the tokenizer's normalizer, pre-tokenizer, vocabulary, special tokens, masks, and padding exactly. Golden token-ID tests cover all eight languages, RTL, accents, punctuation, emoji, and mixed-language queries.
3. One encoder pass provides dense, sparse, and ColBERT outputs. Dense = final-layer CLS, L2-normalized, 1024 values; never mean pooling.
4. Match reference sparse projection/activation, special-token exclusions, repeated-token aggregation, and ColBERT projection/normalization/retained tokens. Compare FlagEmbedding outputs instead of guessing policies.
5. Feed normalized dense to the selected head with reference GELU/Sigmoid behavior; retain 568 outputs. They are not relevance probabilities.
6. Keep 512 tokens including specials as the reference limit. Reject over-limit input with an actionable message initially; do not silently discard its end. Dynamic padding/bucketing must preserve predictions, not allocate 512 tokens for every short query.

### 6.2 Mathematics

With query dense `d`, predicted genome `g`, stored verse genome `v_i`, and family weights:

```text
B=.75, I=.50, N=.50, Q=0, T=.75, U=.75, all others=1
g_w = normalize(sqrt(w) * g)
v_w = normalize(sqrt(w) * v_i)
dense_i  = dot(d, normalized_dense_i)
genome_i = dot(g_w, v_w)
sparse_i = sum(query_token_weight[t] * passage_token_weight[i,t])
```

Apply `sqrt(w)` on both sides, not `w` on both sides. Family Q remains in the head output and is excluded only from retrieval similarity. Do not weight preweighted vectors again. Match reference FP16 matrix decoding/normalization; even re-normalizing exported values requires a parity check.

Retrieve top 200 independently by dense, sparse, and genome across the eligible corpus; form a deduplicated union of at most 600 IDs. For each candidate:

```text
colbert_i = mean_over_retained_query_tokens(
    max_over_retained_passage_tokens(dot(query_token, passage_token))
)
```

Padding never participates: mask invalid passage positions with negative infinity, not zero. Empty retained-token outputs are reported invalid-input/asset conditions. Use float32 vector accumulation and float64 standardization where practical.

Compute all four score arrays on the SAME candidate union. Use sample standard deviation, `ddof=1`:

```text
z(s) = (s - mean(s)) / sample_std(s)
final_i = .28*z(dense)_i + .14*z(sparse)_i
        + .28*z(colbert)_i + .30*z(genome)_i
```

Empty union returns no results; one member returns that member with zero standardized scores. Constant arrays (`std <= 1e-12`) become zeros. Reject nonfinite values. Tie-break by ascending canonical verse ID after descending score. Notebook argpartition tie choices may differ: record tie-only differences as a deliberate deterministic portability refinement.

Default result count = 20; changing display count does not change top-200 lane budgets. Canon/book/chapter filters apply before each lane and standardization; record this as a filtered configuration. Fused z-scores are not percentages, probabilities, or comparable confidence across queries.

### 6.3 Index algorithms

- **Dense:** exhaustive normalized matrix-vector scan, native vectorized top-k. Around 43 million dense products per query for 41,995 × 1024; measure bandwidth/latency.
- **Genome:** exhaustive 41,995 × 568 weighted scan. Use stored verse labels, not newly predicted verse genomes.
- **Sparse:** token-ID posting lists built from existing CSR weights. This is learned sparse retrieval, not BM25/FTS. Preserve zero-score tie behavior when fewer than 200 passages overlap positively.
- **ColBERT:** mapped token slices for union candidates, batched MaxSim with bounded scratch buffers.
- **HNSW/FAISS:** not required initially. Exhaustive numerical search is the baseline; it is unrelated to the phrase-mode meaning of “exact.” Add approximation only after profiling and candidate-recall measurement.

### 6.4 Similar verses, phrase mode, and references

`similarVerses(verseId)` uses the stored genome directly. Begin with a named genome-similarity profile, excluding the source verse. Do not label this Experiment D unless that complete pipeline is implemented/evaluated for verse queries.

Phrase mode bypasses every model. Build per-language FTS5 indexes from displayed source text. Initial UI semantics: **case-insensitive consecutive-word phrase matching, accents preserved, with tokenizer punctuation boundaries**. No stemming, synonym expansion, or implicit OR fallback. This is not byte-identical substring matching; a future literal-punctuation mode needs separate verification. FTS5 phrase behavior is tokenizer-dependent. [SQLite FTS5](https://www.sqlite.org/fts5.html)

Escape user quotes for FTS syntax and bind SQL parameters; parameter binding alone does not make MATCH syntax literal. Test quotes/operators, empty input, Greek/Hebrew diacritics, and missing translations. Phrase search searches the selected language only and shows coverage rather than secretly searching English.

Reference navigation is a separate explicit parser/action, such as `John 3:16`, with multilingual aliases and Psalm/Psalms tests. Do not introduce hidden keyword-based semantic ranking overrides.

## 7. Quantization and model export

The base ZIP contains PyTorch weights/tokenizer/projections, not a verified mobile ONNX model. Head NPZ exports also need an app-compatible export/loader. A quantized head does not quantize BGE-M3.

Steps:

1. Pin an export environment and record source/config hashes. Keep originals unchanged.
2. Wrap the base to expose dense `[B,1024]`, sparse token weights plus matching token IDs/masks, and ColBERT `[B,T,1024]` plus valid lengths. Never send full `[B,T,250002]` tensors through Flutter; keep tensors native.
3. Export FP32 ONNX using external tensor data when required. Verify all supported lengths and large-model exporter/optimizer limitations.
4. Export the head separately as a small ONNX graph or validated native matrix operations. Start with FP32, qualify FP16 independently, and preserve separate base/head identities.
5. Establish unquantized parity BEFORE building INT8. Inspect actual quantization coverage: an unquantized vocabulary embedding table can leave the export much larger than the theoretical INT8 size.
6. Start with a supported CPU path. Static calibration, if used, draws training-only multilingual queries/passages. No validation/test calibration. Test selective quantization or other schemes only against measured failures.
7. Compare quantized query outputs against the existing full-precision passage indexes, including through the unchanged head. Rebuild indexes only if incompatibility is demonstrated or deliberately versioning a new representation.
8. Never substitute another 1024-dimensional encoder on dimensionality alone. Distillation/retraining is a separate owner-approved project if deployment cannot meet agreed limits.

INT8 is a first candidate, not a promised fourfold app-memory reduction or speedup. Quantization can affect quality and operator support; retain sensitive parts in higher precision when needed. Do not begin with INT4. [ORT quantization guidance](https://onnxruntime.ai/docs/performance/model-optimizations/quantization.html)

## 8. ColBERT: the key feasibility gate

The retrieval ZIP has no permanent token index; the notebook encodes candidate passages on demand. That can reproduce the desktop reference but may be too slow on a phone.

Build an **English precomputed ColBERT pack** offline with the pinned encoder and exact retrieval texts. Use uncompressed/mappable shards, 64-bit offsets, token counts, explicit row IDs, dimensions, precision, retention policy, and hashes. Compare stored-vector MaxSim with fresh encoding. Do not re-encode the entire corpus on the phone during installation.

Measure size first. Illustratively, 41,995 verses × 40 tokens × 1024 dimensions × 2 bytes = **3.44 GB FP16** before metadata. INT8 storage roughly halves that vector payload but adds scales and can change rankings. Compression for download is distinct from inference quantization; mapped runtime blocks must remain efficiently readable.

Order of experiments:

1. Count actual retained tokens; estimate FP16/INT8 size before building.
2. Stream resumable FP16 shards as reference storage.
3. Benchmark indexed reads and MaxSim on Windows and the V29.
4. Only if necessary, test token-vector quantization separately. If still unacceptable, present measured options to the owner; do not silently prune tokens, reduce dimensions/candidates, or omit ColBERT.

Map on demand. Do not deserialize every token into Dart lists or duplicate indexes per worker. Start with one inference session and bounded queue. Declare the precision/model compatibility of query and passage sides separately.

## 9. Runtime storage, installation, and updates

Development copies go into ignored `.artifact-staging/` (see handoff). Production files live in platform application-support storage, not user-specific Windows paths or multi-gigabyte `pubspec.yaml` assets.

```text
<application-support>/scriptura/
  user/user.db
  content/<version>/scriptures_genome.db
  content/<version>/questions_genome.db          optional
  content/<version>/scripture_genome_raw.db       optional
  phrase/<content-version>/<language>/
  models/<encoder-version>/                    base + tokenizer
  heads/<head-version>/                        head + gene IDs
  indexes/<index-version>/                     dense/sparse/genome/ColBERT
  manifests/                                  trusted compatibility metadata
  active.json                                 small active-version pointer
  staging/<install-id>/                        incomplete install only
```

Keep source DBs intact initially. Reading requires scripture content; semantic search requires models/indexes; question browsing/raw inspection are optional. Later split language downloads without changing the logical contracts.

Installation protocol:

1. Show download and installed sizes, free space including unpack/rollback, and optional components. Get download consent. Support local-pack import for air-gapped Windows installations.
2. Verify a version-pinned trusted manifest: names, hashes, dimensions, tokenizer/base/head compatibility, ID mapping, minimum runtime.
3. Download resumably to staging, binding resume state to object identity and expected hash. Reject archive traversal, absolute paths, links, unexpected files, and unreasonable expansion size.
4. Verify files, SQLite integrity, and a model/index smoke test before activation. A hash detects corruption; authenticity needs a trusted manifest/signature, not a manifest supplied with an untrusted file.
5. Release old handles then atomically update the active pointer. Versioned directories avoid replacing files still mapped/open on Windows.
6. On failure retain the old release. Never delete `user.db`. Cleanup only resolved paths owned by the install; no broad recursive deletion.
7. Keep one compatible rollback release until successful restart. Optional-pack removal must not remove an active required dependency.

No tokens/credentials in the app. MIT model/code licenses do not grant rights to redistribute scripture editions. Audit source rights and notices before public distribution. Local/private artifact availability is not permission to publish it.

## 10. Application behavior

- Reader-first startup: do not make reading wait for BGE-M3. Load semantic models lazily or through user-approved preload.
- Semantic is default; phrase is an explicit toggle with search language and coverage.
- Submit-to-search initially. Cheap suggestions can be live, but do not encode every keystroke on a 300 ms debounce.
- Show preparing/searching/cancelled/error states. Discard stale responses using request IDs; check cancellation between native stages even if a running operation cannot immediately stop.
- Results carry verse ID, reference, text, actual display language/source/fallback, rank, and optional debug scores. Offer surrounding context.
- No uncalibrated confidence percentages or claims that feature scores establish definitive interpretation.
- Font scaling, screen readers, contrast, keyboard navigation, and Hebrew bidirectional text are required tests.
- Missing/corrupt semantic packs produce a specific message and explicit alternatives. Never label a fallback as Experiment D.
- Cache keys include exact query, filters, mode, candidate language, tokenizer/base/head/index/fusion identities. Display-language changes can re-render cached IDs, not reuse wrong-language text.
- Sensitive queries remain local by default. No automatic query telemetry or medical treatment claims.

## 11. Typed boundaries

```text
SemanticRequest(query, filters, topK, requestId)
PhraseRequest(phrase, searchLanguage, filters, topK, requestId)
SimilarVersesRequest(verseId, filters, topK, requestId)
SearchResponse(requestId, rankedVerseIds, diagnostics, configurationId)
getPassage(verseId, displayLanguage) -> text/reference/source/fallback
getChapter(bookId, chapter, displayLanguage) -> ordered passages
getQuestion(qId, language) -> text/collections/curated targets
```

Diagnostics identify actual precision/provider/model/index versions, candidate/token counts, and per-stage times. Release builds return compact results, not huge tensors. Define native buffer ownership/release, errors, thread safety, cancellation, and background lifecycle. Failures distinguish missing pack, incompatible version, corruption, invalid/over-length input, insufficient resources, inference/index failure, and cancellation. SQL/native cleanup is exception-safe.

## 12. Verification and provisional budgets

These are engineering gates, **not measured performance**. Freeze benchmark inputs and budgets before tuning. If infeasible, document the failure and obtain an explicit revision.

### 12.1 Correctness and quality

- Seven main artifact hashes match the handoff; inner files match manifests.
- Exact tokenizer IDs/masks for every golden case.
- Initial unquantized tolerances: dense cosine ≥0.9999; maximum head-output absolute delta ≤0.001. Inspect sparse/ColBERT errors and ranking changes too; document both sides' precision.
- Deterministic ranking with explicit handling of near ties; diagnose differences, not only average vector similarity.
- All served IDs resolve to text/fallback; all question edges resolve; feature and row order match.
- Evaluate precision changes separately. Proposed quantization review gate: ≤2% relative degradation in mean Recall@10 and NDCG@20 against the SAME Experiment D reference sample; no language >5% relative degradation without review. Report absolute changes and paired question-cluster intervals because low baselines are noisy. This is not proof of equivalence.
- Create at least 100 independently reviewed intents covering definitions, symbolism, personal struggle, doctrinal distinctions, historical context, and multilingual/mixed inputs. Label direct answers versus supporting context versus irrelevant results. Do not hardcode benchmark answers.

Reuse the 250-question/eight-language validation sample only with its exact IDs/inputs/configuration. If only aggregate reports are available, restore inputs from the research archive before claiming reproduction. Keep translations together for grouping/uncertainty; 2,000 rows are not 2,000 independent questions. Reserve final test evaluation until choices are frozen.

### 12.2 Performance targets, not promises

Initial proposed V29 targets for representative short queries: warm semantic median ≤3 seconds, p95 ≤6 seconds; cold semantic-ready ≤15 seconds; peak whole-app memory target ≤2 GB, measured including native allocations/mapped pages. Long inputs up to 512 tokens are a separate stress tier. Reassess these budgets explicitly if they fail before declaring supported devices.

Measure at least 100 warm queries, repeated cold starts, and a 20-minute search session. Report tokenizer, encoder, head, scans, token reads, ColBERT, fusion, SQL/render times; RAM, disk I/O, thermal trend, battery observations, crashes/OS kills. Use release/profile builds and document charging/power-saving state. Test offline after process restart, not just warm cached answers.

Record Windows CPU-only baseline and hardware before setting its performance budget. Kaggle GPU timings do not predict phone performance. Android 13 installation/behavior checks may use emulator/device testing; an emulator cannot certify mobile inference speed.

### 12.3 End-to-end and security/recovery tests

Test first install, local offline import, interrupted transfer, hash mismatch, disk full, incompatible head/index, optional-pack absence, cancellation, process death, background memory pressure, upgrades/rollback, and user-data preservation. With networking disabled, restart and exercise reading, semantic search, phrase search, similar verses, bookmarking, and note persistence. No required authentication/model download may occur after packs are installed.

Unit tests cover math, padding, zero vectors, ties, duplicate sparse tokens, FTS escaping/Unicode, language/table allowlists, fallback, and migrations. Use tiny synthetic/licensed fixtures in Git; real-corpus QA artifacts remain external unless distribution is cleared.

## 13. Phased backlog and exit criteria

No speculative day-count promises. Each phase requires evidence. Log changed files, plan sections, commands/results, tradeoffs, and remaining risks in DEVLOG before a focused commit.

### Phase 0 — protect and establish baseline

- [x] Back up the app externally; inventory legacy assets and any user data. (2026-10-11, [baseline](docs/PHASE0_BASELINE.md))
- [x] Add ignore rules BEFORE copying new artifacts: staging, generated packs, private logs, secrets, local QA; retain synthetic tests.
- [x] Establish code-only Git with an explicit initial allowlist/owner-approved remote; never stage all existing binary assets blindly. (local repo only; no remote chosen)
- [x] Verify toolchains; add Windows scaffold safely and inspect the diff rather than overwrite the project. (Android SDK still absent)
- [x] Copy allowlisted artifacts using the handoff; verify outer and inner hashes. (2026-10-12)
- [ ] Record Windows hardware (done) and V29 physical RAM/device identity (pending Android SDK/adb).

Exit: recovery path, source baseline, verified staging, and toolchain/hardware records. Met except the V29 identity.

### Phase 1 — executable reference

- [x] Implement `tool/verify_artifacts.py` and `tool/reference_search.py` (plus `tool/validate_experiment_d.py`).
- [x] Validate schemas, vectors, row IDs, edges, and source/text mapping.
- [x] Load pinned base and format-correct selected head; reproduce all four signals and ranking in a Windows development Python environment. (FlagEmbedding parity exact; packaged 250-question validation reproduced, all 20 means inside report intervals, max diff 0.0006)
- [x] Remove notebook globals; save golden cases/configs/environment identities. (`test/golden/`)
- [x] Specify filtered search, empty/single-candidate behavior, and tie policy. ([SEARCH_SPEC](docs/SEARCH_SPEC.md))

Exit: repeatable reference and matched evaluation configuration without Kaggle session dependencies. **Met 2026-10-13.** Python is a development tool, not a shipping dependency.

### Phase 2 — full-precision native export and device spike

- [ ] Export base/head with external-data handling and operator inventory. (Base done 2026-10-13: single FP32 multi-output graph, opset 20, 24 distinct ops, 2.27 GB external data; head export/native matrices pending.)
- [ ] Qualify native tokenizer, ORT CPU, and FFI on Windows x64/Android arm64. (Python ORT CPU on Windows x64 qualified; native tokenizer/FFI/arm64 pending.)
- [ ] Compare token IDs and all outputs with Phase 1; add head parity. (Token-ID goldens and ONNX-vs-PyTorch output parity done; native-tokenizer comparison and head parity pending.)
- [ ] Run a minimal benchmark screen on the V29 before full UI work.

Exit: correctness evidence and measured loading/inference cost. If FP32 cannot fit, use desktop reference and assess quantization feasibility explicitly; do not pretend device parity passed.

### Phase 3 — INT8 and precomputed ColBERT

- [ ] Generate INT8/selective mixed-precision base, keeping reference separate.
- [ ] Count actual tokens; build resumable FP16 token shards with validated IDs/offsets.
- [ ] Reuse dense/sparse/genome assets after parity checks; convert layout only as required.
- [ ] Benchmark full native Experiment D on Windows and V29.
- [ ] Quantize token storage only if necessary and independently evaluated.

Exit: quality/memory/latency/storage report and mobile go/no-go. On failure present measured options; do not remove signals or switch to cloud silently.

### Phase 4 — content and installation

- [ ] Implement read-only DB repositories and provenance contract.
- [ ] Implement user DB/migration/recovery, navigation catalog, language fallback.
- [ ] Build phrase indexes and test runtime FTS5 support/semantics.
- [ ] Implement trusted-manifest download/local import, activation, rollback, optional packs.

Exit: offline content startup on Windows/Android; malformed imports rejected; upgrades preserve user data.

### Phase 5 — integrate the application

- [ ] Replace old search callers/startup downloads.
- [ ] Implement reader-first startup, semantic default, phrase toggle, context, provenance, settings, personal library, optional question browsing.
- [ ] Add stored-genome similar verses with named profile.
- [ ] Test cancellation/lifecycle, accessibility, RTL, keyboard/mouse/touch.
- [ ] Remove dead old search code after replacement tests pass, preserving migration evidence.

Exit: complete install → search → read/context → bookmark/note workflow, without old graph/model dependencies.

### Phase 6 — release hardening

- [ ] Run quality, performance, recovery/security, and offline E2E suites.
- [ ] Freeze runtime/model/index/fusion versions; perform final declared test evaluation.
- [ ] Audit scripture redistribution rights and model/runtime notices.
- [ ] Produce signed Windows/Android releases and separate versioned packs; signing secrets stay outside Git. Review current store packaging policies when selecting a channel, not the legacy OBB instructions.
- [ ] Publish tested devices, coverage, storage needs, limitations, upgrade/recovery instructions.

Exit: qualified Windows offline and Android releases. iOS qualification is later and requires Mac/Xcode/signing plus real hardware. [Flutter platform setup](https://docs.flutter.dev/platform-integration)

## 14. Deferred work and decision gates

Deferred: iPhone release, additional semantic candidate languages, retraining/distillation, adaptive fusion, intent classification, question-neighbor ranking boosts, extra rerankers, approximate indexing, cloud sync, generated answers, graph algorithms, and relevance-probability claims. None is necessary to reproduce Experiment D.

Main unresolved gates: mobile inference cost, ColBERT index size, native tokenizer/runtime build, scripture distribution rights, and Windows hardware. See the [review](docs/PLAN_REVIEW.md) for consequences and alternatives.

## 15. Instructions for the next developer or coding agent

1. Read this plan, handoff, and review before changes. Archived instructions are historical only.
2. Begin with Phase 0, not UI redesign or training. Preserve source artifacts and user data.
3. Proposed tools/native modules/generated ONNX and ColBERT files are work to implement, not existing deliverables.
4. Keep base/head/gene order/IDs/edition text/family weights/score normalization explicit. Do not copy defaults from the older `experiment_d_latest_8192_cell.py`.
5. Implement one bounded milestone with tests and DEVLOG evidence, then focused code-only commits. No data binaries, credentials, or user files. No push without authorization.
6. Report unmet requirements with evidence/options. Do not quietly substitute algorithms, lower budgets, change labels, or send queries to a service.
7. Handoff completed/remaining checklist items, artifact identities, commands, tests, and risks. A document or mock screen is not a working search engine.

## 16. Final review conclusion

Proceed with the desktop reference and a small Android feasibility build, then integrate the application. This exposes expensive mobile assumptions early and protects correctness/user data. BGE-M3 quantization is justified as an experiment; mobile success remains to be demonstrated. No new model family or retraining is required to begin.
