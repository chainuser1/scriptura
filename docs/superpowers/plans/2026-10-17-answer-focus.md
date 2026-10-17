# Answer focus Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the BGE reranker as "Answer focus": an optional pack that reorders search's top candidates so passages that answer the question come first, chosen and configured per device without the reader having to understand hardware.

**Architecture:** The engine gains a `focus` request that scores (question, passage text) pairs with an ONNX cross-encoder, on the graphics chip (DirectML, Windows) or the CPU. The app keeps text out of the engine as today: after a search it sends the top K texts and reorders by the returned scores. A device trial times the already-installed BGE-M3 encoder (same architecture and size as the reranker) to predict cost before anything is downloaded; the result picks the variant (fp16 for a working graphics chip, int8 for the CPU, or none) and K. Two optional packs live in the bucket; a device downloads only its own, offered like the optional word-level index.

**Tech Stack:** Rust (`ort` 2.0.0-rc.14, `tokenizers` 0.22.2), Flutter/Dart, Python tooling (onnx, onnxruntime quantization and float16 conversion).

**Spec:** owner decisions in this conversation (2026-10-17), recorded in memory `answer-focus-design`; evidence in [RERANKER_STAGE2_RESULTS.md](../../RERANKER_STAGE2_RESULTS.md).

## Global Constraints

- The UI never says "reranker"; the feature is **Answer focus**.
- Off, missing or failing: search behaves exactly as today (same results, same order, same tests).
- The engine never receives or stores scripture text beyond the strings passed in one `focus` request.
- Variant chosen by measured device performance, not by OS name. Same logic on Windows and Android; graphics acceleration is Windows-only in this plan (Android uses the CPU; NNAPI/QNN later).
- Advanced settings: Answer focus **Automatic** (default) / **On** / **Off**, what it is using, **Measure again**.
- Packs: `answer-focus-int8-v1` (~550 MB) and `answer-focus-fp16-v1` (~1.1 GB), each with the Apache-2.0 licence; offered, never fetched silently; "Not now" respected.
- Credits name BAAI bge-reranker-v2-m3 and its Apache-2.0 licence.
- Ranking uses verse text only (stage-2 choice B); no context windows.
- No co-author trailer in commits.

## Review Focus

1. A search issued while focus is still scoring the previous one: the older result must never replace the newer.
2. Focus slower than predicted (cold start, battery saver): search must still show results within the budget, unfocused.
3. DirectML present but failing at run time (driver): fall back to CPU once, remember it, never crash.
4. Spanish (and other served languages) queries: passages in the query's language.
5. A pack that is partly downloaded, or swapped while a search runs.

---

### Task 1: Quality and speed gate (research, before any app code)

**Files:** `tool/reranker_speed.py` (exists), `docs/RERANKER_STAGE2_RESULTS.md` (append), `local-benchmarks/reranker-speed/`

- [ ] Finish the running timing pass; blind-grade every new top-5 passage it lists; `--score`.
- [ ] Add fp16 ONNX (`onnxruntime.transformers.float16.convert_float_to_float16`, keep IO in fp32) and its CPU parity check against fp32 (max |score diff| and top-5 agreement on all 72 questions).
- [ ] Separate venv `local-benchmarks/dml-venv` with `onnxruntime-directml`; time fp16 on this machine's Radeon graphics for K = 10, 15, 30.
- [ ] Decide and record: int8 keeps a fresh direct-P@5 gain with the 95% interval above 0; at least one (variant, K) runs at ≤ 1.5 s median on this laptop. **If neither holds, stop here** and report.

### Task 2: Pack builder and bucket index

**Files:** Create `tool/build_answer_focus_pack.py`; modify `tool/make_bucket_index.py`; test `test/answer_focus_pack_check.py`

**Produces:** `artifacts/hosting/bucket/answer-focus-int8-v1.zip`, `answer-focus-fp16-v1.zip`, updated `index.json` entries `{format, archive{name,bytes,sha256}, files, optional: true}`.

- [ ] Test first: the check script asserts each zip holds `model.onnx` (single file, no external data), `tokenizer.json`, `LICENSE`, `manifest.json` whose sizes and SHA-256 match, and that ONNX Runtime loads the model and scores 3 fixed pairs within 1e-3 of the fp32 reference stored in `test/golden/answer_focus_pairs.json`.
- [ ] Implement: export, merge external data into one file, int8 and fp16, write manifest, zip, add to index.
- [ ] Commit.

### Task 3: Engine `focus` request

**Files:** Create `engine/src/focus.rs`; modify `engine/src/engine.rs` (Config fields `focus_model`, `focus_tokenizer`, `focus_device`), `engine/src/lib.rs`, `engine/Cargo.toml` (Windows: `ort/directml`); test `engine/tests/focus_e2e.rs` (skips without the pack).

**Produces:** request `{"op":"focus","query":str,"texts":[str],"request_id":n}` → `{"scores":[f32],"device":"gpu"|"cpu","ms":f64}`; `{"op":"device_trial"}` → `{"cpu_ms":f64,"gpu_ms":f64|null}` (encoder on a fixed 30 x 64-token batch); errors `focus_unavailable`, `bad_request`.

- [ ] Tests first: scores match `test/golden/answer_focus_pairs.json` within 1e-3 (int8 within 0.05); empty `texts` → empty scores; cancel honoured between batches; unknown device falls back to CPU and reports it.
- [ ] Implement: pair encoding with the reranker tokenizer (truncate 512), batched padding, sigmoid not applied (raw logits), DirectML session with CPU fallback cached on first failure.
- [ ] `cargo test --release`, commit.

### Task 4: Device choice

**Files:** Create `lib/services/engine/answer_focus.dart`; test `test/answer_focus_choice_test.dart`

**Produces:** `enum FocusMode {automatic, on, off}`; `FocusChoice choose({required double cpuMs, double? gpuMs, required FocusMode mode})` → `(variant: none|int8|fp16, k: 10|15|30, predictedMs)`; prefs `answer_focus` (mode), `answer_focus_choice` (last result JSON).

- [ ] Tests first (pure function): GPU fast → fp16; GPU absent, CPU fast → int8 with the largest K within 1.5 s; both slow → none; mode off → none; mode on with both slow → int8, K 10.
- [ ] Implement; commit.

### Task 5: Pack download and wiring

**Files:** modify `lib/services/engine/engine_pack.dart` (PackKind `focusInt8`, `focusFp16`), `lib/app_controller.dart` (offer, fetch, pass `focus_*` config, run trial after engine ready), `lib/services/engine/search_service.dart`; tests in `test/widget_test.dart`.

- [ ] Tests first: offer appears once the trial chooses a variant and nothing is installed; "Not now" hides it; installing the chosen pack reopens the engine with focus config; the other variant is never downloaded.
- [ ] Implement; commit.

### Task 6: Search uses Answer focus

**Files:** modify `lib/features/search/search_screen.dart`; tests in `test/widget_test.dart`

- [ ] Tests first: with focus active, results appear in score order (fake engine scores); a newer search wins over a slower older focus; focus error or timeout (2 x predicted) shows the unfocused order; phrase and similar searches are never focused; the question-trail button seeds from the focused top three.
- [ ] Implement; commit.

### Task 7: Settings and credits

**Files:** modify `lib/features/settings/settings_screen.dart`, `lib/features/about/about_screen.dart`; tests `test/ui/about_screen_test.dart`, `test/widget_test.dart`

- [ ] Tests first: Advanced shows Answer focus with Automatic/On/Off, "Using: graphics chip | processor | not installed", Measure again re-runs the trial; credits name BAAI bge-reranker-v2-m3 (Apache-2.0); the word "reranker" appears nowhere in `lib/`.
- [ ] Implement; full suite, `flutter analyze`, Windows and Android builds; commit.

### Task 8: Release

- [ ] Owner uploads the two packs and `index.json`; app release (version bump, installers) after the upload is verified by the downloader against the published index.
