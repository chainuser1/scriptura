# Plan self-review and refinement

Reviewed 2026-10-11 against local app code, artifact manifests, ZIP inventories, DB schemas, computed hashes, and the recorded experiment results. This is a design review, not an implementation audit or successful device benchmark. See [PLAN](../PLAN.md) and [artifact handoff](ARTIFACT_HANDOFF.md).

## 1. First proposal and why it needed revision

The simple proposal was: reuse Flutter, load a quantized BGE-M3, copy three DBs, and run Experiment D offline. That is directionally correct but incomplete. It hides tokenizer fidelity, runtime compatibility, huge ColBERT token storage, incomplete text coverage, and the difference between a notebook working and a mobile product working.

The legacy plan was worse for the current task: it assumed old 768-dimensional embeddings, graph algorithms, approximate search, fake confidence calculations, an already-complete pipeline, and a 200 MB memory ceiling. None is a valid baseline for this release.

The refined plan therefore puts a desktop reference, native-runtime proof, and mobile feasibility gate before the full UI rebuild. It preserves the old plan for history but does not follow it.

## 2. Adversarial review of the refined design

| Question/criticism | Evidence or risk | Refinement and status |
| --- | --- | --- |
| Are we selecting the right head? | Several 2048/4096/8192 and question/both experiments exist | Lock question-hidden4096 by checkpoint hash, not newest filename. Resolved in design. |
| Can we load the downloaded head with any existing loader? | NPZ keys differ from the research Safetensors/TorchScript loader | Explicit format-aware import, shape/gene validation, export parity. Resolved in design; implementation pending. |
| Is the app's tokenizer good enough? | Current code hashes unknown words and uses different special IDs | Replace with pinned native tokenizer and exact ID/mask goldens. Release blocker until tested. |
| Does a frozen encoder forbid quantization? | Frozen means not updated in training, not immutable deployment precision | Post-training export allowed; originals retained; no retraining initially. Resolved conceptually. |
| Will INT8 make the base 568 MB and fast? | Partial operator/embedding quantization and runtime buffers can dominate | Measure real files, coverage, RAM, latency. No fixed-size or speed guarantee. Open gate. |
| Can our existing 4096 head consume a quantized base? | Same dimensions do not ensure unchanged representation | Compare all outputs through the head and final ranks. No automatic retraining or acceptance. Open gate. |
| Does a typical dense ONNX export reproduce Experiment D? | It may omit sparse/ColBERT projections and masking | Explicit multi-output contract and component-level goldens. Open gate. |
| Can each phone search re-encode 400–600 candidates? | Potentially much more inference than one query | Precompute token vectors; retain on-demand encoding only as reference/explicit measured alternative. Open gate. |
| Is precomputing ColBERT free? | Illustrative FP16 payload is 3.44 GB at 40 tokens/verse; actual count unknown | Count tokens first, map/shard, benchmark I/O, evaluate index quantization separately. Open gate. |
| Do all 12 GB of the V29 belong to the app? | OS, other apps, native buffers and mapped pages also use memory | Measure whole-process peak; proposed 2 GB review target, not a promise. Open gate. |
| Should we add HNSW immediately? | Only ~42k candidates; approximation adds recall/version/debug costs | Native exhaustive scan first; profile before adding approximation. Resolved initial scope. |
| Is the English index truly language-independent? | Learned sparse tokens and encoder quality vary by query language | Separate query/display/search-index language, expose coverage; evaluate each language. Resolved semantics, quality remains limited. |
| Can all DBs go in the APK? | Raw genome DB alone is ~860 MB; reader does not need it | Versioned external packs, question/raw optional, no eager giant asset bundle. Resolved initial packaging design. |
| Should we instantly split the three DBs per language? | Adds work/migrations before correctness | Start with existing DBs; only split later through a verified derived export. Avoided premature complexity. |
| Does MIT cover scripture distribution? | Text editions have separate provenance and rights | Edition-level review is a publication gate; do not assume rights. Open nontechnical gate. |
| Will new artifact installs erase notes? | Shared files and legacy ID differences can corrupt personal state | Separate writable user DB, transactions, explicit ID mapping, backups, rollback tests. Resolved design; tests pending. |
| Is FTS phrase identical to literal text? | Tokenizers normalize case/punctuation and can affect accents | Define consecutive-word semantics; separate any future literal mode. Resolved product contract. |
| Should we show confidence from scores? | Z-scores depend on candidates and are uncalibrated | Show rank/context; numerical scores debug-only. Resolved. |
| Why not use Python inside the shipped desktop app? | Easiest reference, but creates a different production stack from mobile | Python only for tools/reference; shared native core for shipped clients. Added build complexity acknowledged. |
| Does one shared native core eliminate platform differences? | Libraries, filesystems, CPU instruction sets, lifecycle differ | Separate platform builds and device qualification; same mathematical contract, not assumed bitwise hardware identity. Open build gate. |
| Can we promise iPhone support now? | No phone and no verified Mac/signing pipeline | Preserve portability; defer supported release/testing claims. Explicitly deferred. |
| Are proposed 3/6-second and 2-GB budgets credible? | They are targets without benchmarks | Mark provisional; freeze before tuning, revise only with measured failure/owner approval. Open gate. |

## 3. Evaluation critique: product preference versus benchmark

The owner preferred many Experiment D examples. That is useful qualitative evidence, but the packaged 250-question/eight-language validation report favored weighted genome/dense 90:10 on its annotated targets:

| Method | Recall@10 | NDCG@20 |
| --- | ---: | ---: |
| Weighted genome/dense 90:10 | 0.1449 | 0.1677 |
| Experiment D | 0.0670 | 0.0813 |

Candidate-union target recall was 0.4420. This means some annotated targets never reach the reranking stage; better reranking alone cannot recover them. BGE three-signal measurements also used the shared union, not an independent end-to-end candidate generator.

These are validation results, not held-out test proof. Targets are incomplete and derived from the same annotation process used for training; approximately 5,009 of 41,995 verses appear as labeled answers. A relevant unlisted passage can be counted as a miss. Conversely, a preferred single example does not prove general superiority.

Refinement: retain Experiment D because it is the chosen product behavior, reproduce it faithfully, retain the 90:10 baseline in evaluation, and add independently reviewed direct-answer/context judgments. Do not advertise Experiment D as the benchmark winner or tune on the final test set. The question track trains with eligible scripture records as well as training questions; it evaluates held-out question IDs, not unseen-corpus understanding.

## 4. Numerical pitfalls found during review

1. Weighting both vectors by `w` squares the intended feature weights. Use `sqrt(w)` on both; avoid weighting stored weighted vectors again.
2. Family Q=0 is a retrieval rule, not deletion of model features or retraining.
3. Changing normalization from candidate-union z-score to full-corpus z-score changes Experiment D.
4. Changing `ddof=1` to population variance or mishandling a single candidate changes edge behavior.
5. Zero-padded passage tokens can incorrectly beat negative similarities in MaxSim; mask padding out.
6. Different special-token retention can change ColBERT even if dense embeddings look correct.
7. A question's label is a weighted answer profile, not literal query metadata; historical output values are not necessarily an inference bug.
8. Quantized query vectors may be compatible with existing passage vectors, but compatibility must be tested instead of forcing a costly rebuild or assuming perfect parity.
9. The row-order hash and the `.npy` file hash are distinct. Store and validate both with defined serialization.
10. Deterministic tie handling is a deliberate portability refinement; document differences from notebook argpartition rather than conceal them.

## 5. What must be decided from measurements

| Decision | Evidence required | Default until decided |
| --- | --- | --- |
| Native inference/provider/version | Windows/Android operator support, parity, performance | One pinned CPU path; do not chase accelerators first |
| Base precision | Actual file size, peak RAM, eight-language quality | INT8 candidate, FP32/FP16 reference retained |
| Head precision | Error through same base and retrieval pipeline | FP32 or qualified FP16; not automatic INT8 |
| ColBERT storage precision | Token count, I/O, MaxSim/ranking error | FP16 reference mapped/sharded |
| Android supported hardware | V29 results plus lower-tier testing if widening support | V29 is initial test target, not universal Android 13 guarantee |
| Windows minimum hardware | Named CPU-only benchmark machine | Not published yet |
| Full offline mobile if budgets fail | Measured breakdown and quality/cost options | Pause release promise and discuss; no hidden cloud fallback |
| Public text distribution | Source/edition rights review | Do not publish unreviewed text packs |
| iOS release | Mac/Xcode/signing plus real device | Deferred |

Changing a head, tokenizer, corpus edition, feature mask, candidate budget, normalization scope, precision, or candidate language creates a new configuration identity and invalidates relevant caches. If training/label changes become necessary, that belongs in a new research/evaluation version, not an unnoticed app update.

## 6. Final self-review checklist

- [x] User's selected model, Experiment D default, and optional phrase mode preserved.
- [x] Exact source paths, hashes, DB table names, and later copy directions documented.
- [x] Existing assets distinguished from proposed exports and token indexes.
- [x] Old plan preserved; unsupported old guarantees marked superseded.
- [x] Windows reference precedes mobile/UI complexity; iOS not falsely claimed tested.
- [x] Numeric/tokenizer/ID contracts and multi-language caveats explicit.
- [x] Resource assumptions challenged, not presented as measurements.
- [x] User data, text provenance, updates/rollback, offline import, and privacy covered.
- [x] Quality and performance acceptance gates specified with evidence requirements.
- [x] Scope exclusions prevent old graph/HNSW logic creeping back into the baseline.
- [ ] Device benchmarks, export parity, and application tests — future implementation work.
- [ ] Public distribution rights audit — future publication gate.

Review conclusion: the plan is implementable as a staged engineering program, not an assertion that every target will meet performance budgets. Begin Phase 0 and the executable reference. Do not rebuild the complete interface or retrain until the highest-risk runtime/storage questions have evidence.

## 7. Primary technical references checked

- [ONNX Runtime mobile deployment](https://onnxruntime.ai/docs/tutorials/mobile/) — CPU baseline and device-specific performance qualification.
- [ONNX Runtime quantization](https://onnxruntime.ai/docs/performance/model-optimizations/quantization.html) — conversion/accuracy and large-model constraints.
- [BGE-M3 documentation](https://bge-model.com/bge/bge_m3.html) — distinct dense, sparse, and ColBERT outputs.
- [Hugging Face Tokenizers core](https://github.com/huggingface/tokenizers/tree/main/tokenizers) — complete tokenizer pipeline, not simple word lookup.
- [SQLite FTS5](https://www.sqlite.org/fts5.html) — token-based phrase semantics.
- [Flutter platform integration](https://docs.flutter.dev/platform-integration) — platform-specific build requirements.

These upstream references inform architecture, not a claim that the existing app or downloaded bundles already implement the recommended runtime.
