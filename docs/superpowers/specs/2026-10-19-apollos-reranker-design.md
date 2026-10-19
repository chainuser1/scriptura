# Apollos: a second Answer Focus reranker — Design

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:writing-plans to
> turn this design into an implementation plan before any code is written.

## Intent and why

Answer Focus (the reranker that reorders search results toward direct answers)
currently has exactly one model: BAAI/bge-reranker-v2-m3, shipped as the
`answer-focus-int8-v1`/`answer-focus-fp16-v1` packs. Research this cycle
(`docs/ANSWER_FOCUS_CHALLENGERS_RESULTS.md`,
`docs/ANSWER_FOCUS_NEMOTRON_HELDOUT_RESULTS.md`) found
nvidia/llama-nemotron-rerank-1b-v2 ranks noticeably better on both the original
and a fresh held-out question set (any-direct coverage 0.909 vs 0.636; fewer
wrong passages shown). The owner decided to ship it as a second, named,
user-visible model choice, intended to become the new default for existing
and new users.

The two models are given personal names so the in-app picker doesn't read as
version numbers: **Ezra** (today's BGE model, unchanged) and **Apollos**
(the new Nemotron model). This design covers making Apollos a real,
selectable, working second reranker — not re-litigating whether to ship it;
that decision is already made.

## Current state (what exists today)

- One focus model slot throughout the stack: `engine_pack.dart`'s config
  builder emits one `focus_model`/`focus_tokenizer`/`focus_device` triple
  (`lib/services/engine/engine_pack.dart:181`); the Rust engine holds exactly
  one `Option<Mutex<FocusSlot>>` (`engine/src/engine.rs:82`); `focus.rs`'s
  `Focus` struct and its `encode_pair` method
  (`engine/src/focus.rs:100-102`) are written specifically for BGE's
  tokenizer-pair format (`<s> q </s></s> p </s>`, via the Rust `tokenizers`
  crate's pair-encoding, 512-token limit).
- Device-capability selection (`lib/services/engine/answer_focus.dart`) is a
  pure, 3-outcome decision: `none` / `int8` (CPU, picks the largest candidate
  count `k` that fits a 1.5s budget using a measured `cpu_ms` and a fixed
  per-candidate cost constant `_cpuFactor`) / `fp16` (GPU, fixed starting
  `k=10`, adapts from real search times afterward). This is binary
  (`FocusVariant` is a closed 3-value enum) with no notion of "which model."
- `PackKind` (`lib/services/engine/engine_pack.dart:34-45`) is a generic,
  already-proven manifest+SHA256 install mechanism used for 7 pack kinds
  today, including `focusInt8`/`focusFp16`. Adding more kinds is mechanical.
- Apollos's tokenization is structurally different: a single concatenated
  string (`"question:{q} \n \n passage:{p}"`), not a tokenizer pair, and its
  official template/prefix differs from Ezra's. (The Qwen challenger tested
  earlier used yet another format entirely — not relevant here, Qwen is not
  being shipped.)
- Apollos has **two verified-working packs**: fp16 (GPU/DirectML, ~2.5GB)
  and int8 (CPU, ~2.0GB, `apollos-int8-weight-only-v1`). The first int8
  attempt (dynamic quantization) was broken — one test pair's score flipped
  sign — and was replaced with weight-only quantization (int8 storage,
  `DequantizeLinear` back to fp32 before the matmul; activations stay
  fp32), which passes all three verification pairs within tolerance. See
  `apollos-int8-fixed-weight-only` memory. Weight-only int8 shrinks
  download/disk size; it does not by itself mean faster inference or
  lower RAM than fp16 — that's a separate, unmeasured question, same as
  Ezra's own int8 tier was originally measured rather than assumed.

## Goals

1. Apollos becomes a second, independently selectable reranker, named in the
   UI, with its own pack(s), own tokenization path, own device-capability
   handling.
2. Existing users are migrated to Apollos as the new default on update.
   New users default to Apollos too.
3. A user can explicitly pick Ezra or Apollos in Settings; the choice is
   named and described in a warm, personal tone (not technical specs).
4. A device that can't run the user's chosen model falls back silently to
   the other model, using the exact same mechanical pattern Ezra's own
   fp16→int8 runtime fallback already uses (`focus.rs`'s
   `fall_back_to_cpu`/`Focus::score`'s retry-on-GPU-failure) — extended to
   also cover "chosen model's pack isn't usable at all on this device," not
   only "GPU failed mid-session." With both Apollos tiers now working,
   this scenario (Apollos entirely unavailable) should be rare — most
   devices get either fp16 (GPU) or int8 (CPU) Apollos — but the mechanism
   stays in place for the genuine edge case (e.g. a device too slow even
   for Apollos's CPU budget, mirroring Ezra's own "too slow for Automatic"
   outcome).
5. The very first time a device can't get the user's chosen/default model
   at all (both Apollos tiers unusable on this device), show one prominent,
   explicit notice:
   **"Scriptura Labs is working on a solution"** (exact copy is the
   builder's call within that spirit — see Non-goals). After that first
   showing, the unavailable option appears permanently greyed out in the
   picker, not hidden, with the same explanation available on tap/hover.
   This same show-once-then-grey pattern applies generally: any time a
   chosen reranker stops being available (GPU failure later, pack deleted,
   etc.), not only the CPU-only-at-migration case.

## Non-goals

- Re-deriving or re-explaining Apollos's int8 quantization fix. The weight-
  only approach is already built, verified, and placed
  (`apollos-int8-fixed-weight-only` memory) — this design consumes the
  finished pack, it doesn't revisit how it was made.
- Changing Ezra at all. Ezra's existing int8/fp16 packs, tokenization, and
  behavior are untouched.
- A third reranker, or a generic "N reranker families" abstraction beyond
  what's needed for exactly two. Don't build a plugin system for
  rerankers nobody has asked for yet.
- Exact UI copy/wording for the two model descriptions or the "working on a
  solution" notice — the warm/personal tone and the specific trigger
  conditions are decided; final wording is the plan's/builder's call,
  reviewed by the owner before ship (this is product copy, not a technical
  decision this design needs to lock down).
- Qwen or any other challenger model. Only Ezra and Apollos ship.
- Revisiting the challenger/held-out research methodology or re-running
  those experiments. Already complete and reported.

## Constraints

- No change to Ezra's shipped behavior, packs, or tokenization format.
- Apollos ships with both tiers this round: fp16 (GPU/DirectML,
  `apollos-fp16-v1`) and int8 (CPU, weight-only quantization,
  `apollos-int8-weight-only-v1`). Do not assume int8 is faster or lower-
  RAM than fp16 without measuring — weight-only quantization shrinks
  storage, not necessarily runtime cost (stated plainly in the pack's own
  `CONVERSION_NOTICE.txt`).
- The engine config contract (`focus_model`/`focus_tokenizer`/`focus_device`
  triple passed from Dart to Rust) may grow a new field for "which
  tokenization/encoding family," but must stay backward compatible: an
  absent field must default to Ezra's current behavior (today's BGE
  pair-encoding), so a config built by old app code against a new engine
  binary (or vice versa) doesn't silently misencode.
- Model names ("Ezra"/"Apollos") are user-visible UI strings and also
  reasonable internal identifiers (file/dir names, log lines, pref keys) —
  reuse the same short lowercase token (`ezra`/`apollos`) in code and packs,
  keep the capitalized display form only in UI-facing strings.
- Per the owner's standing review-before-ship practice for this whole
  research line: no claim that Apollos beats Ezra "in general" should appear
  in shipped copy — it's a per-device/per-situation choice, framed
  positively ("Apollos looks harder for the exact answer") without a direct
  superiority claim that could read as overclaiming given the research's own
  "exploratory, not fully independent" caveats.

## Architecture

### Rust engine (`engine/src/focus.rs`, `engine/src/engine.rs`)

Generalize `Focus` to carry a small, closed "family" distinction instead of
being BGE-specific, while keeping everything that is genuinely
model-agnostic (session management, GPU probe/fallback, cancellation,
batching, tensor construction) exactly as it is today — none of that code
needs to change.

```rust
pub enum RerankerFamily {
    Ezra,     // BAAI/bge-reranker-v2-m3: tokenizer pair-encoding, 512 tokens
    Apollos,  // nvidia/llama-nemotron-rerank-1b-v2: single concatenated string
}
```

- `Focus::open` gains a `family: RerankerFamily` parameter (default/absent in
  config → `Ezra`, satisfying the backward-compatibility constraint above).
- `encode_pair` (today BGE-pair-specific) becomes two small functions
  dispatched on `family`: the existing tokenizer-pair call for `Ezra`;
  for `Apollos`, build the single string
  `format!("question:{query} \n \n passage:{text}")` and tokenize it as one
  sequence (plain `tok.encode(&s, true)`, no pair API). Max token length
  per family: 512 for Ezra, a conservative value for Apollos (the Kaggle
  pipeline validated correctness up to 8192, but pick a budget-appropriate
  cap here, not the full 8192 — the device-capability `_cpuFactor`-style
  budget math in Dart needs its own per-family constant anyway; see below).
- Everything else in `score`/`score_on_device`/`fall_back_to_cpu`/
  `cpu_session`/`gpu_available` is unchanged: it already operates on token
  ID tensors, not on anything BGE-specific.
- `GPU_BATCH` (currently a single constant tuned for BGE's int8 batching
  behavior) likely needs a per-family value once Apollos runs on GPU in
  practice — the plan should measure this rather than assume BGE's tuning
  transfers.

`engine.rs`'s `FocusSlot`/`self.focus` stay a single slot (one model loaded
at a time, matching how it's actually used — a device runs one chosen
reranker, never both at once). The slot's `NotLoaded` variant gains the
`family` field, threaded through from config.

### Engine config contract

`EnginePaths`'s JSON builder (`lib/services/engine/engine_pack.dart:181`)
adds one field alongside the existing three, e.g. `'focus_family': 'ezra' |
'apollos'`, omitted (→ Ezra) when no focus model is configured, matching the
existing `if (focus != null) ...` pattern.

### Dart device-capability selection (`lib/services/engine/answer_focus.dart`)

This is the piece that most needs real design, not just plumbing. Today
`choose()` picks a **precision tier** (`none`/`int8`/`fp16`) for one fixed
model. It now needs to also pick **which model**, with Apollos fp16-only.

Recommended shape (builder may refine during planning, this is the
intended behavior, not exact code):

- `FocusVariant` becomes two dimensions conceptually: which model
  (`ezra`/`apollos`) × which precision (`int8`/`fp16`/`none`) — but keep the
  actual enum small and concrete rather than a generic cross product. A
  reasonable concrete shape: `enum FocusModel { ezra, apollos }` plus the
  existing `FocusVariant` kept for precision, with `FocusChoice` carrying
  both `model` and `variant`. Both models now have a real int8-CPU and
  fp16-GPU tier.
- Selection logic, given the mode is the user's pick (default: automatic →
  Apollos preferred):
  - If GPU available: Apollos fp16 (the new default good case).
  - If GPU not available: Apollos's own int8-CPU budget ladder (its own
    per-candidate cost constant, not Ezra's `_cpuFactor` — see Review Focus
    #4), mirroring Ezra's existing `_ks`-based "most candidates that fit
    the budget" logic exactly, just parameterized per model.
  - Only if Apollos's CPU ladder finds no candidate count fits even at the
    minimum (a device too slow for Apollos specifically, the genuine edge
    case Goal 4/5 cover): fall back to Ezra's existing ladder, set the
    "first time unavailable" flag so the UI shows the one-time notice, then
    greys Apollos in the picker from then on.
  - If the user explicitly chose Ezra in Settings: use Ezra's existing
    logic unchanged, regardless of GPU.
  - If the user explicitly chose Apollos and neither tier fits: same
    fallback-to-Ezra-with-notice as the automatic case, framed as "the
    device can't run your choice yet," not silently overriding their pick
    without explanation.
- `adapt()`'s real-time step-down logic and `keep()`'s "already installed
  wins" rule need the same per-model treatment Ezra has today, extended to
  not cross-contaminate (an installed Apollos pack shouldn't be "kept" if
  the trial now says Ezra, and vice versa) — the plan should write this out
  explicitly as a task, since `keep()`'s current single-`FocusVariant`
  signature needs to become model-aware.
- A new persisted pref (or an extension of `answer_focus_choice`) records:
  current model+variant choice, and whether the "Apollos unavailable, we're
  working on it" notice has already been shown (so it only shows once, then
  greys permanently per Goal 5).

### Pack management (`lib/services/engine/engine_pack.dart`)

Add `PackKind` entries for both tiers now:
`apollosFp16('apollos-fp16-v1', 'apollos-fp16')` and
`apollosInt8('apollos-int8-v1', 'apollos-int8')`. IMPORTANT, corrected
2026-10-19 after reading the real shipped zip: the int8 pack's *filename*
is `apollos-int8-weight-only-v1.zip` (to distinguish it on disk/in the
hosting bucket from an earlier broken build that used the plain name),
but its internal `manifest.json`'s `"format"` field is literally
`"apollos-int8-v1"` — the two were never changed to match. Since
`engine_pack.dart`'s install/verify logic checks `m['format'] !=
kind.format` and throws if they differ, `PackKind.format` MUST be
`'apollos-int8-v1'` (matching the manifest), not the zip's filename, or
every install of this pack fails. The owner decided to keep the manifest
as-is rather than regenerate/re-verify the pack. Every switch currently enumerating `PackKind`/`FocusVariant`
(the `_focusKind` getter, `_focusPack()`, the `order` map in
`downloadAndInstall`, the `friendly()` switch, the download switch's case
arms — all identified in the earlier research pass, `app_controller.dart`)
needs its new arm(s). This is mechanical, following the existing
`focusInt8`/`focusFp16` pattern exactly — no new mechanism, just more cases.

### UI: Settings model picker

A new picker (likely in Settings › Advanced, alongside or replacing the
existing Answer Focus on/off/automatic control) listing Ezra and Apollos as
named choices, each with a short warm/personal-tone description (exact copy
decided during planning/build, not here — see Non-goals). Apollos shows
greyed-out with an explanation when unavailable per Goal 5's behavior.

### Migration (existing installs)

On first run after the update that ships this: if the user has no explicit
model preference yet (i.e., they never saw a picker before — this is new),
treat them as if they'd just picked Apollos (the new default), and run the
same selection/fallback logic above as if that were a fresh choice. No
separate migration code path — reuse the normal selection flow with
"preferred model = Apollos" as the default preference, which is simpler and
less risky than a one-time special-cased migration script.

### Un-sticking a fallback (owner decision, 2026-10-19)

With both Apollos tiers now working, a device falling back to Ezra should
be rare (only a device too slow for Apollos's CPU budget *and* without a
GPU). But the mechanism still matters — for that edge case, and for the
general principle that a fallback is never silently permanent. A device
parked on Ezra this way is **not** stuck there permanently. Re-probe
automatically at the two natural existing checkpoints, both already present
in the app:

- **App update** — a later update could raise Apollos's CPU budget, change
  its packs, or otherwise change what this device can run; the normal
  "trial runs if no choice yet, or mode just changed" logic isn't enough by
  itself here, since the user already has a choice (Ezra). The plan needs a
  small explicit rule: if the user's preference is "Apollos" (explicit or
  default-from-migration) but the active choice is Ezra-via-fallback,
  re-run `choose()` on next app start after an update that changes which
  Apollos packs are available — not on every single launch, to avoid
  re-probe churn.
- **The existing "Measure again" button** (`remeasure()` in
  `app_controller.dart`, already user-triggered today) — works as-is, no
  change needed, since it already re-runs the full trial.

This means `keep()`'s "installed wins" rule needs a carve-out: it should
keep an installed pack against routine re-trial noise (the original
purpose), but must NOT keep a fallback-to-Ezra choice against a fresh trial
that now finds Apollos genuinely available (GPU fixed, or Apollos int8 now
installed). The plan should treat "chosen model preference" (what the user
wants) and "active fallback" (what they're getting instead, and why) as
two separate pieces of persisted state, not conflate them — this is the
piece of new logic the builder check flagged as real, not plumbing.

The "shown once, then greyed" notice (Goal 5) still only shows its
prominent first-time form once ever per cause; afterward the picker simply
un-greys Apollos silently when a re-probe succeeds (no new notice needed
for the "good news" direction — only the original unavailability got the
prominent treatment).

## What's left to the builder (plan-time decisions)

- Exact persisted-pref shape for model+variant+notice-shown state (a single
  JSON blob like today's `answer_focus_choice`, or split prefs — builder's
  call, consistent with existing `UserStore.setPref` patterns).
- Apollos's per-family token budget and GPU batch size — measure, don't
  assume BGE's tuning constants transfer.
- Exact copy for the two model descriptions and the "working on a solution"
  notice (reviewed by the owner before ship).
- Whether the model picker lives in Settings › Advanced as a new control or
  reshapes the existing Answer Focus on/off/automatic control — a UI/UX
  call informed by whatever Settings currently looks like, not dictated
  here.
- Test coverage shape: this clearly needs new Dart unit tests (mirroring
  `test/answer_focus_choice_test.dart`'s existing coverage of `choose()`/
  `adapt()`/`keep()`) and new Rust `engine/tests/` coverage (mirroring
  `focus_e2e.rs`'s existing pattern) for Apollos's encoding path
  specifically — both are plan tasks, not resolved here.

## Review Focus

(For the plan's self-review and reviewer, in priority order)

1. **Old app binary + new engine, or vice versa, during a staged rollout**:
   does the `focus_family`-absent-defaults-to-Ezra contract actually hold
   if only one side of the app/engine pair is updated? This is the most
   likely real-world way this breaks silently.
2. **A user who already explicitly chose Ezra, then Apollos later gets
   fixed to support int8 too**: their explicit Ezra choice must survive
   unchanged — the re-probe/un-stick logic above (see "Un-sticking a
   fallback") only applies when the user's *preference* is Apollos but
   they're on a fallback; an explicit Ezra preference is never
   auto-switched. This is now resolved by the design, not open.
3. **The "shown once, then greyed" notice state surviving app
   reinstall/data reset**: is "already shown" persisted somewhere that
   survives a normal update but is intentionally not expected to survive a
   full reinstall (same as other first-run notices), or could a user see
   the notice repeatedly across ordinary updates if the pref key changes?
   Builder's call, consistent with how other first-run notices in this app
   already behave.
4. **Apollos's much larger token budget (8192) vs Ezra's 512**: a search
   candidate passage that's short for Ezra's budget could be comparatively
   expensive for Apollos's larger model at the same token count — does the
   per-family GPU_BATCH/budget math in Dart's `choose()` actually reflect
   Apollos's real per-candidate cost, or does it inherit Ezra's
   `_cpuFactor`-style constant by copy-paste mistake during planning?
5. **GPU memory**: Apollos (1.24B params, fp16 ≈ 2.4GB) is meaningfully
   larger than Ezra's fp16 pack — does loading it on a GPU that's borderline
   for Ezra produce a clean failure (falls back per Goal 4) or a crash/hang
   the existing fallback logic doesn't catch?
