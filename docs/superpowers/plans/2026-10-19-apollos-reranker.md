# Apollos Reranker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Apollos (nvidia/llama-nemotron-rerank-1b-v2) a second, named, selectable Answer Focus reranker alongside Ezra, with Apollos as the new default where the device supports it.

**Architecture:** Generalize the Rust `Focus` struct with a `RerankerFamily` enum that only changes tokenization (pair-encoding for Ezra vs. a single concatenated string for Apollos); every other engine mechanism (session management, GPU probe/fallback, cancellation, batching) is untouched. Dart's device-capability selection grows a "which model" dimension alongside its existing "which precision tier" dimension — Apollos now has both an int8 (CPU) and fp16 (GPU) tier, same two-tier shape as Ezra — with explicit, separately-persisted state for "user's model preference" vs. "active fallback," so a device auto-recovers from a fallback once the real blocker (a device too slow for even Apollos's CPU tier, the remaining rare edge case) is fixed, without ever overriding an explicit user choice.

**Tech Stack:** Rust (engine, `ort` crate, `tokenizers` crate), Dart/Flutter (app, existing `PackKind`/`PackStore`/`UserStore` pref patterns).

**Spec:** `docs/superpowers/specs/2026-10-19-apollos-reranker-design.md`

## Global Constraints

- No change to Ezra's shipped behavior, packs, tokenization, or default int8/fp16 tier logic.
- Apollos ships with both tiers this round: fp16 (`apollos-fp16-v1`, GPU/DirectML) and int8 (CPU, weight-only quantization, hosted as `apollos-int8-weight-only-v1.zip` but its manifest's internal `"format"` field is `"apollos-int8-v1"` — verified directly against the real shipped zip 2026-10-19; `PackKind`'s format string MUST be `'apollos-int8-v1'` to match, since the app checks this field exactly (`engine_pack.dart`'s `m['format'] != kind.format` guard) and a mismatch makes every install of this pack fail with `wrong_kind`. This reuses a string the design doc earlier warned against reusing, from before this was checked against the real file — the owner explicitly decided to keep the manifest as-is rather than regenerate/re-verify the pack, so this is the correct, current value, not an oversight). Do not assume int8 is faster or lower-RAM than fp16 without measuring.
- `focus_family` absent from engine config must default to Ezra's current pair-encoding behavior (old-app/new-engine or new-app/old-engine compatibility).
- Internal identifiers use lowercase `ezra`/`apollos`; capitalized `Ezra`/`Apollos` only in UI-facing strings.
- An explicit user preference for Ezra is never auto-switched to Apollos, ever, under any re-probe.
- No claim in shipped copy that Apollos beats Ezra "in general" — frame as a per-device choice, not a superiority claim.

## Review Focus

- **Old app binary talking to a new engine, or vice versa, mid-rollout:** `focus_family` must be treated as absent (→ Ezra) by an engine that predates this change, and an app that predates this change must never send `focus_family` at all (so a new engine defaults it to Ezra too). Covered by Task 2's config round-trip test.
- **A user with an explicit Ezra preference, later offered a fixed Apollos int8 pack:** must never auto-switch. Covered by Task 6's `keep()`-successor test (`resolveFallback` in this plan).
- **The "shown once, then greyed" notice reappearing on an ordinary update** (not a reinstall) because of a pref-key mismatch: covered by Task 7's persistence test (same pref survives a value round-trip; this plan does not add update-specific migration since there is no pre-existing pref to migrate from).
- **Apollos's much larger per-candidate cost silently inheriting Ezra's `_cpuFactor`/`GPU_BATCH` tuning by copy-paste:** covered by Task 5 and Task 8, which require their own named constants, never shared with Ezra's.
- **A device re-probes into Apollos becoming available, but an in-flight search is using Ezra:** `resolveFallback`'s output only takes effect on the next engine (re)start (same as every existing `FocusChoice` change today — `_startEngineNow` is already the single place choices take effect), so no new mid-search-switch logic is needed; Task 6's test confirms the function is pure and has no side effect on a running engine.
- **Apollos's larger (2.4GB fp16) model hanging rather than cleanly failing on a borderline GPU, where Ezra's smaller model would have loaded fine:** no real hardware exists in this environment to test this directly (same measurement gap Task 5 already names for per-candidate cost). Task 1's `Focus::open` reuses the exact same timeout-free GPU session commit Ezra already uses — this plan does not add a load-time watchdog, since doing so correctly (without false-positiving on a merely slow first load) is a real design question of its own, not a mechanical addition. Recorded here as a known, deliberately deferred gap rather than silently dropped: if real-device testing later surfaces a hang (not a clean `Err`), it needs its own follow-up investigation, not a guessed timeout value bolted on now.
- **Apollos's int8 (weight-only quantization) silently assumed to be faster or lower-RAM than fp16 just because it downloads smaller:** the pack's own `CONVERSION_NOTICE.txt` states this explicitly isn't guaranteed (activations still compute in fp32). Covered by Task 5's own named constant for Apollos's CPU-tier cost (not borrowed from Ezra's `_cpuFactor`, and not assumed equal to it).

---

## File Structure

- `engine/src/focus.rs` — add `RerankerFamily` enum, generalize `Focus::open`/`encode_pair`; everything else (session mgmt, GPU fallback, batching, cancellation) untouched.
- `engine/src/engine.rs` — `Config.focus_family` field, `FocusSlot::NotLoaded.family`, thread `family` through `focus_op`.
- `engine/tests/focus_e2e.rs` — extend `pack()`/`shared()` to take a family; add Apollos-specific encoding/scoring tests (skip gracefully if `generated-artifacts/apollos-fp16-v1` isn't built, same pattern as Ezra's int8/fp16 skip).
- `lib/services/engine/answer_focus.dart` — `FocusModel` enum, `FocusChoice` gains a `model` field, `choose()`/`adapt()` become model-aware, new `resolveFallback()` function (the "un-sticking" logic).
- `lib/services/engine/engine_pack.dart` — `PackKind.apollosFp16`/`PackKind.apollosInt8` entries.
- `lib/app_controller.dart` — new `PackStore` getters (one per Apollos tier), new `focusModelPreference` persisted pref, `_focusKind`/`_focusPack()`/`friendly()`/`missingData`-adjacent logic grow Apollos arms for both tiers; `measureDevice()` calls `resolveFallback()` instead of `keep()` directly.
- `test/answer_focus_choice_test.dart` — extend with Apollos-aware cases; new tests for `resolveFallback()`.
- Settings UI (model picker) — new widget; exact file left to the implementer per the design's Non-goals (UI copy/placement is a build-time call), but it must consume `FocusModel`/`FocusChoice` as defined in this plan, not invent its own shape.

---

### Task 1: `RerankerFamily` and Apollos tokenization in the Rust engine

**Files:**
- Modify: `engine/src/focus.rs`
- Test: `engine/tests/focus_e2e.rs`

**Interfaces:**
- Consumes: nothing new from other tasks.
- Produces: `pub enum RerankerFamily { Ezra, Apollos }` (in `engine/src/focus.rs`, `derive(Clone, Copy, PartialEq, Eq)`); `Focus::open(model: &Path, tokenizer: &Path, threads: usize, want_gpu: bool, family: RerankerFamily) -> Result<Self, String>` (5th param added, inserted after `want_gpu` to keep the existing 4 args' order); `Focus::encode(&self, query: &str, text: &str) -> Result<Vec<u32>, String>` replacing the family-specific dispatch (keeps `encode_pair` as a thin deprecated-in-place alias is NOT needed — rename call sites instead, see Task 1 Step 5).

- [ ] **Step 1: Write the failing test for Apollos's single-string encoding**

```rust
// engine/tests/focus_e2e.rs, new test
#[test]
fn apollos_concatenates_question_and_passage_as_one_string() {
    let Some(f) = shared_apollos() else { return };
    let ids = f.encode("What is the capital of France?", "Paris is the capital of France.").unwrap();
    // Re-tokenize the same literal string the Kaggle pipeline used and compare, rather than hand-building IDs:
    // "question:What is the capital of France? \n \n passage:Paris is the capital of France."
    let expected_text = "question:What is the capital of France? \n \n passage:Paris is the capital of France.";
    let direct = f.tokenizer_encode_single(expected_text).unwrap(); // see Step 3 helper
    assert_eq!(ids, direct);
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cargo test --manifest-path engine/Cargo.toml apollos_concatenates_question_and_passage_as_one_string`
Expected: FAIL (compile error: `shared_apollos`, `encode`, `tokenizer_encode_single` not defined)

- [ ] **Step 3: Implement `RerankerFamily`, `Focus::open`'s new param, and `Focus::encode`**

In `engine/src/focus.rs`:
- Add `pub enum RerankerFamily { Ezra, Apollos }` above `pub struct Focus`.
- Add a `family: RerankerFamily` field to `Focus`.
- `Focus::open` signature becomes `pub fn open(model: &Path, tokenizer: &Path, threads: usize, want_gpu: bool, family: RerankerFamily) -> Result<Self, String>`; store `family` in the returned struct (both the GPU and CPU-session-fallback return paths).
- Replace `encode_pair` with `encode`, dispatching on `self.family`:
  - `RerankerFamily::Ezra` → exactly today's body (`self.tok.encode((query, text), true)...`).
  - `RerankerFamily::Apollos` → build `format!("question:{query} \n \n passage:{text}")`, then `self.tok.encode(s, true).map_err(err)?.get_ids().to_vec()` (single-sequence encode, not a pair — confirm the `tokenizers` crate's `encode` accepts a plain `&str`/`String` as input in addition to the pair tuple it's called with today; if the trait bound requires a distinct call shape, use `EncodeInput::Single(s.into())` explicitly).
  - Add a small test-only helper `#[cfg(test)] pub fn tokenizer_encode_single(&self, s: &str) -> Result<Vec<u32>, String>` that calls the tokenizer directly without the `question:`/`passage:` formatting, so Step 1's test can independently verify the format string without duplicating the production formatting logic in the test itself. (This helper only needs to exist behind `#[cfg(test)]`; it is not part of the public API other tasks consume.)
- Update every call site of `encode_pair` in `focus.rs` (inside `score_on_device`) to call `self.encode(...)` instead — this is the only behavior-preserving rename needed for Ezra; Apollos's new branch is additive.
- Add `fn shared_apollos()` to `engine/tests/focus_e2e.rs`, mirroring the existing `shared("int8")`/`shared("fp16")` pattern but pointing at `generated-artifacts/apollos-fp16-v1` and passing `RerankerFamily::Apollos`, `want_gpu: true` (Apollos is fp16/GPU-only; skip gracefully with `eprintln!` + `None` if the pack isn't built, same as `pack()` does today).
- Update the existing `shared()` helper's `Focus::open(...)` call to pass `RerankerFamily::Ezra` as the new 5th argument (its two existing callers, `shared("int8")`/`shared("fp16")`, keep working unchanged otherwise).

- [ ] **Step 4: Run test to verify it passes**

Run: `cargo test --manifest-path engine/Cargo.toml apollos_concatenates_question_and_passage_as_one_string`
Expected: PASS (or a clean skip-with-message if `generated-artifacts/apollos-fp16-v1` isn't present in this environment — in which case also manually confirm the pack exists at that path on a machine that has downloaded it, before trusting the skip)

- [ ] **Step 5: Run the full existing focus suite to confirm the `encode_pair` → `encode` rename didn't break Ezra**

Run: `cargo test --manifest-path engine/Cargo.toml --test focus_e2e`
Expected: all existing tests (`pairs_tokenize_like_python`, `long_passages_are_truncated_to_the_model_limit`, `int8_on_the_cpu_matches_the_reference`, `a_batch_scores_like_one_by_one`, etc.) still PASS unchanged

- [ ] **Step 6: Commit**

```bash
git add engine/src/focus.rs engine/tests/focus_e2e.rs
git commit -m "engine: generalize Focus with a RerankerFamily so Apollos can use its own tokenization"
```

---

### Task 2: `focus_family` in the engine config contract

**Files:**
- Modify: `engine/src/engine.rs`

**Interfaces:**
- Consumes: `RerankerFamily` from Task 1.
- Produces: `Config.focus_family: Option<String>` (deserialized `"ezra"` | `"apollos"`, default `None`); `FocusSlot::NotLoaded` gains a `family: RerankerFamily` field; `focus_op` passes the resolved family into `Focus::open`.

- [ ] **Step 1: Write the failing test for the backward-compatible default**

```rust
// engine/tests/engine_e2e.rs (or wherever existing Config-from-JSON tests live; follow that file's pattern) — add:
#[test]
fn focus_family_absent_in_config_defaults_to_ezra() {
    // Build a Config from a JSON object with no "focus_family" key (use the same JSON construction
    // pattern this file already uses for other Config fields) and confirm the engine's FocusSlot ends up
    // requesting RerankerFamily::Ezra when a focus request is made — assert via the same mechanism this
    // file already uses to inspect FocusSlot state (likely the engine's `info()` JSON, or a focused request
    // that only succeeds/behaves one way for Ezra's known test pack). Follow this file's existing idiom
    // for asserting engine internal state rather than reaching into private fields directly.
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cargo test --manifest-path engine/Cargo.toml focus_family_absent_in_config_defaults_to_ezra`
Expected: FAIL (field/behavior not implemented yet)

- [ ] **Step 3: Implement the config field and threading**

In `engine/src/engine.rs`:
- Add `#[serde(default)] pub focus_family: Option<String>,` to `Config`, near the existing `focus_device` field.
- Add a small `fn parse_family(s: Option<&str>) -> RerankerFamily { match s { Some("apollos") => RerankerFamily::Apollos, _ => RerankerFamily::Ezra } }` (anything absent or unrecognized → Ezra, satisfying the backward-compat constraint explicitly, not just by accident of `Option` defaulting).
- Add `family: RerankerFamily` to `FocusSlot::NotLoaded`, set from `parse_family(cfg.focus_family.as_deref())` at construction (near the existing `(Some(m), Some(t)) => Some(Mutex::new(FocusSlot::NotLoaded { ... }))` arm).
- In `focus_op`, when transitioning `NotLoaded → Ready`, pass `*family` into `Focus::open(model, tokenizer, *threads, *gpu, *family)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cargo test --manifest-path engine/Cargo.toml focus_family_absent_in_config_defaults_to_ezra`
Expected: PASS

- [ ] **Step 5: Run the full engine test suite for regressions**

Run: `cargo test --manifest-path engine/Cargo.toml`
Expected: all tests PASS (single-threaded if the known pre-existing `focus_e2e.rs` parallel-resource-contention flakiness appears: `cargo test --manifest-path engine/Cargo.toml -- --test-threads=1`)

- [ ] **Step 6: Commit**

```bash
git add engine/src/engine.rs engine/tests/
git commit -m "engine: thread focus_family through Config and FocusSlot, defaulting to Ezra"
```

---

### Task 3: `FocusModel` and model-aware `FocusChoice` in Dart

**Files:**
- Modify: `lib/services/engine/answer_focus.dart`
- Test: `test/answer_focus_choice_test.dart`

**Interfaces:**
- Consumes: nothing new from other tasks (pure Dart logic, no engine dependency).
- Produces: `enum FocusModel { ezra, apollos }`; `FocusChoice` gains `final FocusModel model` (constructor becomes `FocusChoice(this.model, this.variant, this.k, this.predictedMs)`, `FocusChoice.none` becomes `const FocusChoice(FocusModel.ezra, FocusVariant.none, 0, 0)` — Ezra is the "nothing chosen yet" placeholder model since it's always available); `toJson()`/`fromJson()` include `model`; `choose({required double cpuMs, required bool gpu, required FocusMode mode, required FocusModel preferred})` gains a `preferred` parameter. Apollos has both an int8-CPU and fp16-GPU tier (same shape as Ezra), so this task's `choose()` must give Apollos its own CPU ladder, not just a GPU branch — the exact per-candidate cost constant for that ladder is Task 5's job; this task wires the branch using a placeholder constant Task 5 then replaces (see Task 5's Interfaces).

- [ ] **Step 1: Write the failing tests for model-aware choice**

```dart
// test/answer_focus_choice_test.dart — add within group('choose', ...):
test('preferring Apollos with a working graphics chip gets Apollos fp16', () {
  final c = choose(cpuMs: laptop, gpu: true, mode: FocusMode.automatic, preferred: FocusModel.apollos);
  expect(c.model, FocusModel.apollos);
  expect(c.variant, FocusVariant.fp16);
});

test('preferring Apollos without a graphics chip gets Apollos int8 on a fast-enough device', () {
  final c = choose(cpuMs: 600, gpu: false, mode: FocusMode.automatic, preferred: FocusModel.apollos);
  expect(c.model, FocusModel.apollos);
  expect(c.variant, FocusVariant.int8);
});

test('preferring Apollos on a device too slow for even its smallest int8 candidate count falls back to Ezra', () {
  final c = choose(cpuMs: 50000, gpu: false, mode: FocusMode.automatic, preferred: FocusModel.apollos);
  expect(c.model, FocusModel.ezra); // Apollos's own ladder (Task 5) found nothing that fits; fall back
});

test('preferring Ezra always gets Ezra, with or without graphics', () {
  expect(choose(cpuMs: laptop, gpu: true, mode: FocusMode.automatic, preferred: FocusModel.ezra).model, FocusModel.ezra);
  expect(choose(cpuMs: laptop, gpu: false, mode: FocusMode.automatic, preferred: FocusModel.ezra).model, FocusModel.ezra);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `flutter test test/answer_focus_choice_test.dart`
Expected: FAIL (compile errors: `FocusModel`, `preferred` param, `c.model` not defined)

- [ ] **Step 3: Implement `FocusModel` and update `FocusChoice`/`choose()`**

In `lib/services/engine/answer_focus.dart`:
- Add `enum FocusModel { ezra, apollos }` near `FocusVariant`.
- Add `final FocusModel model` to `FocusChoice`; update the constructor, `FocusChoice.none`, `toJson()` (add `'model': model.name`), `fromJson()` (parse `model` via `FocusModel.values.byName(...)`, defaulting to `FocusModel.ezra` if the key is absent — old persisted JSON from before this change has no `model` key, so `fromJson` must not throw on its absence), `operator ==`, `hashCode`, `toString()`.
- `choose()` gains `required FocusModel preferred`. New body shape when `preferred == FocusModel.apollos`: if `gpu`, return `FocusChoice(FocusModel.apollos, FocusVariant.fp16, 10, cpu10)` (Apollos's own predicted-ms formula). Else, run an Apollos-specific CPU ladder (mirroring the existing `for (final k in _ks) { ... }` shape exactly, but over a placeholder `_apollosKs`/placeholder cost constant this task introduces — e.g. reuse `_ks`/`_cpuFactor` literally for now, Task 5 replaces both with Apollos's own named versions in the very next task): the first `k` whose predicted time fits the budget wins, `FocusModel.apollos`/`FocusVariant.int8`. If none fit, fall through to `FocusModel.ezra` and exactly today's Ezra-only logic. When `preferred == FocusModel.ezra`, use exactly today's Ezra-only logic unchanged, wrapping each returned `FocusChoice` with `FocusModel.ezra`.
- `adapt()` and `keep()` keep their current signatures for now (Task 6 replaces `keep()`'s call site with `resolveFallback()`; don't modify `keep()` itself in this task — leave it as dead code only if Task 6 fully replaces its only call site, otherwise keep it referenced).

- [ ] **Step 4: Run tests to verify they pass**

Run: `flutter test test/answer_focus_choice_test.dart`
Expected: PASS, including all pre-existing tests in this file (update any that construct `FocusChoice(...)` positionally to include the new `model` argument)

- [ ] **Step 5: Commit**

```bash
git add lib/services/engine/answer_focus.dart test/answer_focus_choice_test.dart
git commit -m "app: add FocusModel and make FocusChoice/choose() model-aware"
```

---

### Task 4: `PackKind.apollosFp16` and `PackKind.apollosInt8`

**Files:**
- Modify: `lib/services/engine/engine_pack.dart`

**Interfaces:**
- Consumes: nothing new.
- Produces: `PackKind.apollosFp16` with `format: 'apollos-fp16-v1'`, `dirName: 'apollos-fp16'`; `PackKind.apollosInt8` with `format: 'apollos-int8-v1'`, `dirName: 'apollos-int8'`. IMPORTANT, already verified directly against the real shipped zip (2026-10-19): despite the zip being named `apollos-int8-weight-only-v1.zip` (to distinguish it from an earlier broken build on disk/in the hosting bucket), its internal `manifest.json`'s `"format"` field is literally `"apollos-int8-v1"` — confirmed by extracting and reading it. `PackKind.format` MUST match this exact string, since `engine_pack.dart`'s own install/verify code does `if (m['format'] != kind.format) throw PackException('wrong_kind', ...)` — using the zip's filename instead would make every install of this pack fail. The owner explicitly decided to keep the manifest as-is (not regenerate/re-verify the pack) rather than fix the mismatch at the source, so `'apollos-int8-v1'` is the correct, deliberate value here, not an oversight.

- [ ] **Step 1: Add both enum entries**

In `lib/services/engine/engine_pack.dart`, add `apollosFp16('apollos-fp16-v1', 'apollos-fp16'),` and `apollosInt8('apollos-int8-v1', 'apollos-int8'),` to the `PackKind` enum, after `focusFp16`.

- [ ] **Step 2: Run the existing pack test suite to confirm nothing broke**

Run: `flutter test test/` (or the specific pack-related test file this repo already has for `engine_pack.dart`, if one exists — search `test/` for `engine_pack` or `PackKind` references first)
Expected: PASS, no new test needed for this step alone (it's a data-only addition; Task 8 exercises both through real selection logic)

- [ ] **Step 3: Commit**

```bash
git add lib/services/engine/engine_pack.dart
git commit -m "app: add apollosFp16 and apollosInt8 pack kinds"
```

---

### Task 5: Apollos's own per-candidate cost constants and CPU budget ladder

**Files:**
- Modify: `lib/services/engine/answer_focus.dart`
- Test: `test/answer_focus_choice_test.dart`

**Interfaces:**
- Consumes: `FocusModel`/updated `choose()` from Task 3 (Task 3 wired the Apollos branches using placeholder/Ezra-shared constants; this task replaces those placeholders with Apollos's own named constants).
- Produces: `const _apollosGpuK = 10;` (fixed starting candidate count for Apollos on GPU, mirroring Ezra's fp16 starting `k=10`); `const _apollosCpuFactor = ...;` and `const _apollosKs = [...];` (Apollos's own CPU-tier per-candidate cost constant and candidate-count ladder, independent of Ezra's `_cpuFactor`/`_ks` — weight-only int8 still computes in fp32, so there is no reason to assume its cost-per-candidate matches Ezra's int8 tier; see Note below). `choose()`'s Apollos branches use these constants explicitly, never Ezra's.

**Note on measurement:** per the design doc's Review Focus #4 (via the builder check), there is no real device available in this environment to measure Apollos's true per-candidate cost before shipping, on GPU or CPU. For the GPU starting point, ship the same conservative `k=10` Ezra's own fp16 tier uses (its comment already says "first searches measure the real graphics time" — the existing `adapt()` step-down logic, unchanged, corrects a wrong starting guess from real measured search times). For the CPU ladder, do not copy Ezra's `_cpuFactor`/`_ks` values verbatim and call it Apollos's constant — that would silently assume a ~1.24B-parameter Llama-family model costs the same per candidate as BGE-reranker-v2-m3, which the design doc explicitly warns against. Instead: reuse Ezra's exact *ladder shape* (`_ks = [30, 15, 10]`, same `kFocusBudgetMs = 1500`) but pick a deliberately conservative placeholder `_apollosCpuFactor` that assumes Apollos costs at least as much per candidate as Ezra until real measurement says otherwise — e.g. start from `_cpuFactor * 2` as a documented, named, clearly-flagged placeholder (a comment must say this is unmeasured and needs a real-device pass), not a silent copy. `adapt()`'s existing step-down logic then corrects it from real search times exactly as it already does for Ezra.

- [ ] **Step 1: Write the failing tests for Apollos's own constants**

```dart
test('Apollos gpu choice starts at k=10, independent of the CPU budget constant', () {
  final apollos = choose(cpuMs: laptop, gpu: true, mode: FocusMode.automatic, preferred: FocusModel.apollos);
  final ezra = choose(cpuMs: laptop, gpu: true, mode: FocusMode.automatic, preferred: FocusModel.ezra);
  expect(apollos.k, ezra.k); // both 10 today, by coincidence of the shared starting point, not a shared constant
  expect(apollos.model, FocusModel.apollos);
  expect(ezra.model, FocusModel.ezra);
});

test('Apollos CPU ladder predicts a different time than Ezra for the same device speed', () {
  final apollos = choose(cpuMs: laptop, gpu: false, mode: FocusMode.automatic, preferred: FocusModel.apollos);
  final ezra = choose(cpuMs: laptop, gpu: false, mode: FocusMode.automatic, preferred: FocusModel.ezra);
  // Same device, same k is plausible, but the predicted ms must come from Apollos's own constant, not Ezra's:
  expect(apollos.predictedMs, isNot(equals(ezra.predictedMs)));
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `flutter test test/answer_focus_choice_test.dart`
Expected: FAIL if Task 3's placeholder didn't already name distinct constants (confirm by reading the current state of `choose()` after Task 3 — if Task 3 already reused `_cpuFactor`/`_ks` literally for Apollos, this step should fail on the second test specifically, since `predictedMs` would be identical)

- [ ] **Step 3: Implement the named constants, replacing any literal/shared values reused from Ezra's path**

Add `const _apollosGpuK = 10;`, `const _apollosCpuFactor = _cpuFactor * 2; // unmeasured placeholder -- no Apollos CPU device benchmarked yet; adapt() corrects this from real search times`, and `const _apollosKs = [30, 15, 10];` near `_cpuFactor`/`_ks`. Reference them from `choose()`'s Apollos branches instead of Ezra's constants or bare literals.

- [ ] **Step 4: Run tests to verify they pass**

Run: `flutter test test/answer_focus_choice_test.dart`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add lib/services/engine/answer_focus.dart test/answer_focus_choice_test.dart
git commit -m "app: give Apollos its own GPU/CPU budget constants, independent of Ezra's"
```

---

### Task 6: `resolveFallback()` — the un-sticking logic

**Files:**
- Modify: `lib/services/engine/answer_focus.dart`
- Test: `test/answer_focus_choice_test.dart`

**Interfaces:**
- Consumes: `FocusModel`, `FocusChoice` from Task 3.
- Produces: `FocusChoice resolveFallback({required FocusModel preference, required FocusChoice fresh, required FocusChoice? before, required bool apollosInstallable})` — replaces `keep()`'s role at its one call site (Task 9); `keep()` itself stays in the file unchanged (still unit-testable, but no longer called from `app_controller.dart` once Task 9 lands) since removing it is not required by this plan and risks an unrelated diff.

**Design recap (from the spec's "Un-sticking a fallback" section):** `preference` is what the user actually wants (explicit choice, or Apollos by default). `fresh` is what this trial run just computed. `before` is the previously persisted choice. `apollosInstallable` is true when `fresh.model == FocusModel.apollos` — i.e. this trial run's own `choose()` call (Task 3/5) already found a usable Apollos tier for this device, GPU or CPU. The caller (Task 8) passes `fresh.model == FocusModel.apollos` directly; `resolveFallback` itself does not re-derive device capability. The function must:
- Never return `FocusModel.ezra` when `preference == FocusModel.apollos` AND `fresh.model == FocusModel.apollos` AND `apollosInstallable` — i.e., once Apollos is genuinely available, stop forcing the user back onto a stale Ezra fallback.
- Never return `FocusModel.apollos` when `preference == FocusModel.ezra` — an explicit Ezra preference is absolute, full stop, regardless of `fresh`/`apollosInstallable`.
- Otherwise, preserve `keep()`'s existing "installed wins against routine re-trial noise" behavior for whichever model is actually active, so a slow/busy re-trial doesn't strand an installed pack's precision tier.

- [ ] **Step 1: Write the failing tests for the three required behaviors**

```dart
group('resolveFallback', () {
  const ezraChoice = FocusChoice(FocusModel.ezra, FocusVariant.int8, 10, 1200);
  const apollosChoice = FocusChoice(FocusModel.apollos, FocusVariant.fp16, 10, 800);

  test('an explicit Ezra preference is never overridden to Apollos', () {
    final r = resolveFallback(preference: FocusModel.ezra, fresh: apollosChoice, before: ezraChoice, apollosInstallable: true);
    expect(r.model, FocusModel.ezra);
  });

  test('preferring Apollos, once genuinely installable, replaces a stale Ezra fallback', () {
    final r = resolveFallback(preference: FocusModel.apollos, fresh: apollosChoice, before: ezraChoice, apollosInstallable: true);
    expect(r.model, FocusModel.apollos);
  });

  test('preferring Apollos but still not installable keeps the Ezra fallback (no regression)', () {
    final r = resolveFallback(preference: FocusModel.apollos, fresh: ezraChoice, before: ezraChoice, apollosInstallable: false);
    expect(r.model, FocusModel.ezra);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `flutter test test/answer_focus_choice_test.dart`
Expected: FAIL (`resolveFallback` not defined)

- [ ] **Step 3: Implement `resolveFallback`**

```dart
FocusChoice resolveFallback({
  required FocusModel preference,
  required FocusChoice fresh,
  required FocusChoice? before,
  required bool apollosInstallable,
}) {
  if (preference == FocusModel.ezra) {
    return before?.model == FocusModel.ezra && fresh.model != FocusModel.ezra ? before! : fresh;
  }
  if (fresh.model == FocusModel.apollos && apollosInstallable) return fresh; // genuinely available now: un-stick
  if (before?.model == FocusModel.apollos && fresh.model != FocusModel.apollos) return before!; // installed Apollos wins against noise
  return fresh; // still on the Ezra fallback; nothing to un-stick yet
}
```

(One line on the approach: this mirrors `keep()`'s "installed wins against noise" shape per-model, but adds the explicit preference gate `keep()` never had. The body above is a starting point the implementer may refine against the three tests above, not a mandate — but all three tests must pass.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `flutter test test/answer_focus_choice_test.dart`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add lib/services/engine/answer_focus.dart test/answer_focus_choice_test.dart
git commit -m "app: add resolveFallback() so a device un-sticks from Ezra once Apollos is genuinely available"
```

---

### Task 7: First-time "working on a solution" notice state

**Files:**
- Modify: `lib/services/engine/answer_focus.dart` or `lib/app_controller.dart` (implementer's call which file owns the pref read/write, consistent with where `focus_gpu_failed`/`focus_declined` already live — those are in `app_controller.dart`, so put this there too for consistency)
- Test: `test/answer_focus_choice_test.dart` or a new `test/app_controller_focus_test.dart` if `app_controller.dart`'s existing tests live in a separate file (check `test/` first)

**Interfaces:**
- Consumes: `FocusModel`, `resolveFallback()` from Task 6.
- Produces: `bool get apollosUnavailableNoticeShown` / `void markApollosUnavailableNoticeShown()` on `AppController` (pref key `'apollos_unavailable_notice_shown'`, string `'1'`/absent, following the exact existing pattern of `focus_declined`/`focus_gpu_failed`).

- [ ] **Step 1: Write the failing test for the pref round-trip**

```dart
test('the Apollos-unavailable notice is shown once, then stays marked', () {
  // Follow this repo's existing pattern for constructing a testable AppController/UserStore
  // (check how focus_declined / declineAnswerFocus are tested today, if at all, or construct
  // a minimal UserStore-backed harness consistent with other AppController tests in this repo).
  final controller = /* construct per existing test harness pattern */;
  expect(controller.apollosUnavailableNoticeShown, isFalse);
  controller.markApollosUnavailableNoticeShown();
  expect(controller.apollosUnavailableNoticeShown, isTrue);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `flutter test <the test file from Step 1>`
Expected: FAIL (getter/method not defined)

- [ ] **Step 3: Implement the pref getter/setter**

In `lib/app_controller.dart`, near `declineAnswerFocus()`/`focus_declined`:
```dart
bool get apollosUnavailableNoticeShown => user.pref('apollos_unavailable_notice_shown') == '1';
void markApollosUnavailableNoticeShown() {
  user.setPref('apollos_unavailable_notice_shown', '1');
  notifyListeners();
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `flutter test <the test file from Step 1>`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add lib/app_controller.dart test/
git commit -m "app: persist whether the Apollos-unavailable notice has been shown once"
```

---

### Task 8: Wire Apollos into `AppController` (packs, downloads, selection)

**Files:**
- Modify: `lib/app_controller.dart`

**Interfaces:**
- Consumes: `PackKind.apollosFp16`/`PackKind.apollosInt8` (Task 4), `FocusModel`/`resolveFallback` (Tasks 3, 6), `apollosUnavailableNoticeShown` (Task 7).
- Produces: `PackStore get focusApollosFp16Packs`; `PackStore get focusApollosInt8Packs`; `_focusKind` and `_focusPack()` grow Apollos arms for both tiers; `missingData`-adjacent `_focusKind != null` checks account for all four (model × tier) combinations; `friendly()` gains `'apollos-fp16' || 'apollos-int8' => 'Answer focus'`; `measureDevice()` calls `resolveFallback()` instead of `keep()`; `focusChoice`'s persisted `FocusModel` becomes the source of truth for `_focusPack()`/`_focusKind` instead of only `FocusVariant`; a new persisted pref `focus_model_preference` (string `'ezra'`/`'apollos'`, defaulting to `'apollos'` when absent) that Task 9's UI reads/writes.

- [ ] **Step 1: Write the failing test for `_focusKind`/pack selection becoming model-aware**

(This exercises `AppController` end-to-end per whatever harness this repo's existing `AppController` tests already use — search `test/` for existing `AppController` construction patterns before writing this; do not invent a new harness.)

```dart
test('a persisted Apollos fp16 choice resolves to the apollos-fp16 pack kind', () {
  // Using the existing AppController test-construction pattern:
  // 1. persist a FocusChoice(FocusModel.apollos, FocusVariant.fp16, 10, 800) via user.setPref('answer_focus_choice', ...)
  // 2. assert controller's internal _focusKind-equivalent (likely exposed indirectly via offerAnswerFocus /
  //    a public getter this task adds if none exists) reflects 'apollos-fp16', not 'answer-focus-fp16'
});

test('a persisted Apollos int8 choice resolves to the apollos-int8 pack kind', () {
  // Same pattern, FocusChoice(FocusModel.apollos, FocusVariant.int8, 30, 1200) -> 'apollos-int8'
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `flutter test <file from Step 1>`
Expected: FAIL

- [ ] **Step 3: Implement the model-aware pack/kind resolution**

In `lib/app_controller.dart`:
- Add `PackStore get focusApollosFp16Packs => PackStore(Directory('${_root!.path}/scriptura'), PackKind.apollosFp16);` and `PackStore get focusApollosInt8Packs => PackStore(Directory('${_root!.path}/scriptura'), PackKind.apollosInt8);` near the existing `focusFp16Packs` getter.
- Rewrite `_focusKind` to branch on both `focusChoice?.model` and `focusChoice?.variant`:
  ```dart
  String? get _focusKind => switch ((focusChoice?.model, focusChoice?.variant)) {
        (FocusModel.ezra, FocusVariant.int8) => 'answer-focus-int8',
        (FocusModel.ezra, FocusVariant.fp16) => 'answer-focus-fp16',
        (FocusModel.apollos, FocusVariant.int8) => 'apollos-int8',
        (FocusModel.apollos, FocusVariant.fp16) => 'apollos-fp16',
        _ => null,
      };
  ```
- Rewrite `_focusPack()` with the matching four-way branch, returning `focusApollosInt8Packs.active()`/`focusApollosFp16Packs.active()` for the two Apollos cases.
- Update `friendly()` in the `ensureData`-adjacent closure: add `'apollos-fp16' || 'apollos-int8' => 'Answer focus',` alongside the existing `'answer-focus-int8' || 'answer-focus-fp16' => 'Answer focus',` arm.
- Add a new persisted-preference getter/setter, e.g. `FocusModel get focusModelPreference => FocusModel.values.byName(user.pref('focus_model_preference') ?? 'apollos');` / `void setFocusModelPreference(FocusModel m) { user.setPref('focus_model_preference', m.name); notifyListeners(); }` (absent pref defaults to Apollos, per the design's migration decision — "no explicit preference yet" means "treat as if they just picked Apollos"). Task 9's picker calls `setFocusModelPreference`.
- In `measureDevice()`, replace the `keep(before, fresh, installed: installed)` call: compute `apollosInstallable: fresh.model == FocusModel.apollos` (per Task 6's Interfaces — `choose()`'s own output already reflects whether this device found a usable Apollos tier, GPU or CPU; no separate pack-presence check needed here since `fresh` came from the trial, not from what's already downloaded), and call `resolveFallback(preference: focusModelPreference, fresh: fresh, before: before, apollosInstallable: apollosInstallable)` in place of `keep(...)`.
- In `_startEngineNow`'s `EnginePaths` construction, pass the new `focus_family` field (Task 2's engine contract) derived from `focusChoice?.model` (`'apollos'` or `'ezra'`), alongside the existing `focusGpu` computation — confirm `EnginePaths`' own `config()` builder (`lib/services/engine/engine_pack.dart:181`) is updated in this task too (it's listed as a separate file in File Structure but is small enough to fold into this task's Step 3 rather than a whole separate task).
- Update `EnginePaths.config()` (`engine_pack.dart:181`) to add `if (focus != null) 'focus_family': focusChoice?.model.name ?? 'ezra'` (or equivalent) alongside the existing three `focus_*` keys.

- [ ] **Step 4: Run test to verify it passes**

Run: `flutter test <file from Step 1>`
Expected: PASS

- [ ] **Step 5: Run the full Dart test suite for regressions**

Run: `flutter test`
Expected: all tests PASS (fix any call site this task's signature changes broke — e.g. other tests constructing `FocusChoice` positionally)

- [ ] **Step 6: Commit**

```bash
git add lib/app_controller.dart lib/services/engine/engine_pack.dart test/
git commit -m "app: wire both Apollos tiers through pack selection, downloads, and engine config"
```

---

### Task 9: Settings model picker UI

**Files:**
- Create: a new widget file under `lib/` (implementer's call on exact path/name, consistent with this app's existing Settings screen structure — find and follow the existing Settings page's file organization first)
- Modify: whatever existing Settings screen currently hosts the Answer Focus on/off/automatic control

**Interfaces:**
- Consumes: `FocusModel`, `FocusChoice`, `apollosUnavailableNoticeShown`/`markApollosUnavailableNoticeShown` (Task 7), `resolveFallback` (via `AppController`, Task 8).
- Produces: a picker UI showing "Ezra" and "Apollos" as named choices with short descriptions (warm/personal tone, exact copy is this task's call, reviewed by the owner before ship per the design's Non-goals); Apollos greyed out with an explanation when `!apollosInstallable` on this device, using the exact copy "Scriptura Labs is working on a solution" the first time it becomes true for this install (triggering `markApollosUnavailableNoticeShown()`), and a quieter persistent greyed state on every view after that.

- [ ] **Step 1: Confirm the existing Settings screen structure before writing new code**

Read the file that currently renders the Answer Focus on/off/automatic control (search for `FocusMode`/`setFocusMode` usage in `lib/`) and identify where a model picker fits alongside it.

- [ ] **Step 2: Write the widget**

No prescribed code here — this is UI layout work the design explicitly leaves to the builder (exact copy, exact placement). Requirements this step must satisfy, verified in Step 3:
- Both Ezra and Apollos always appear as choices (Apollos is never hidden, only greyed).
- Selecting a choice calls through to the preference pref Task 8 introduced (`focus_model_preference`), then triggers the same re-measure/engine-restart flow `setFocusMode`/`remeasure()` already use.
- The first time Apollos is unavailable on this device (`apollosInstallable == false` and `!apollosUnavailableNoticeShown`), show the prominent notice and call `markApollosUnavailableNoticeShown()`; every subsequent view shows only the quiet greyed state.

- [ ] **Step 3: Write and run a widget test confirming the three behaviors above**

Follow this repo's existing widget-test conventions (find an existing Settings widget test for a pattern to match, e.g. one covering `FocusMode` selection today, if one exists).

Run: `flutter test <new widget test file>`
Expected: PASS

- [ ] **Step 4: Manually run the app and exercise the picker**

Per this project's standing practice for UI changes: start the app, open Settings, confirm both choices render, confirm selecting each one behaves correctly, confirm the greyed state and one-time notice render as expected on a device without a working GPU (or by simulating `apollosInstallable: false` if no such device is available to test on directly).

- [ ] **Step 5: Commit**

```bash
git add lib/ test/
git commit -m "app: add the Ezra/Apollos model picker to Settings"
```

---

## Completion

After Task 9, run the full test suites one more time end to end:

```bash
cargo test --manifest-path engine/Cargo.toml -- --test-threads=1
flutter test
```

Both must be fully green before this plan moves to its real-device check.

### Real-device end-to-end test (owner request, 2026-10-19)

After both suites are green, build the Android APK and install it on the owner's own phone (a real
device, not an emulator) for a genuine end-to-end check — not a substitute for Tasks 1-9's own tests,
an additional check this plan does not consider complete without. At minimum, confirm on the device:

1. The app builds and installs cleanly (`flutter build apk` or this repo's existing Android build
   script, per whatever `tool/build_engine_android.py`/existing release tooling already does — follow
   that, don't invent a new build path).
2. The Settings model picker (Task 9) shows both Ezra and Apollos, and switching between them actually
   changes search ranking behavior (a quick manual before/after search comparison is enough, not a
   formal benchmark).
3. On this specific phone, confirm which Apollos tier actually gets chosen (fp16/GPU or int8/CPU) via
   the device trial, and that it runs without crashing or hanging — this is the first real data point
   for the design's Review Focus items #4 (Apollos's unmeasured per-candidate cost) and #5 (GPU
   load/memory behavior on real hardware, not just the no-hardware-available placeholder reasoning
   Tasks 5 and the Review Focus list currently rely on).
4. If the device picks Apollos's CPU tier and real search times suggest Task 5's placeholder
   `_apollosCpuFactor` guess (`_cpuFactor * 2`) is badly wrong in either direction, note the real
   measured value — this becomes a tracked follow-up to replace the placeholder with a real constant,
   not a blocker for this plan's own completion (the existing `adapt()` step-down logic already
   corrects for this at runtime regardless).

Report what was observed (which tier was chosen, whether it worked, any crash/hang) back to the owner
as part of this plan's final report — this is real evidence the Review Focus list's open measurement
questions deserved, and the first chance to confirm or correct them.

### Hugging Face bucket upload (owner decision, 2026-10-19: explicitly held until this point)

Do NOT upload `apollos-fp16-v1.zip`/`apollos-int8-weight-only-v1.zip` to the live hosting bucket
(`kDefaultDataAddress`'s `index.json`) at any point before this. Uploading to that bucket is a real,
hard-to-reverse action on the actual address real users' installed apps already query — it should
only happen once there's a working build that can actually request and use these packs (i.e. after
the real-device test above has passed), not as a side effect of landing any individual task.

Once the real-device test above has passed: this is the deliberate "ship it" step, done consciously,
not automatically. The owner performs or explicitly approves the actual upload (same standing rule as
every other upload in this project: no pushes/uploads without the owner). This plan's own completion
does not require the upload to have happened — it requires the app to be *ready* for it.
