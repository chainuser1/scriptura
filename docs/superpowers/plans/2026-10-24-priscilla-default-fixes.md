# Priscilla Default Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Fix the real bugs a fresh whole-branch review found in `priscilla-default-fresh-install` (already merged to this branch's history): the combined first-run notice's "Continue" action never actually fetches Priscilla on a true clean install, the notice can get stuck forever with no way to dismiss it on a slow device, and an existing user who already has Ezra installed and working loses it silently on upgrade. Also add a lightweight first-run warning when the automatic trial falls back off Priscilla, so a slow-device reader isn't left with silent, unexplained behavior.

**Architecture:** Three small, independent fixes to `AppController` (`focusModelPreference`'s fallback becomes conditional on "nothing installed yet" rather than unconditional; `ensureData` resolves a download kind from the preference directly when no trial has run yet, not only from a persisted `focusChoice`; `offerPriscillaDefaultSetup` is tightened to stop offering once anything is installed or focus is off) plus one new small piece of Home-screen UI (a dialog shown once per completed automatic trial that fell back off the preferred default, built from the existing `focusTrial` future and the existing `AlertDialog`/`acceptOverride` machinery Settings already uses -- no new override-acceptance mechanism).

**Tech Stack:** Flutter/Dart, existing `AppController`/`FocusModel`/`PackKind` machinery, no new dependencies.

**Spec:** None written separately -- this plan's own Global Constraints section below captures the decisions made directly with the project owner (via AskUserQuestion) in the conversation that produced it, plus the fresh reviewer's findings (`.superpowers/sdd/2026-10-24-priscilla-default-on-fresh-install/progress.md`'s final review, findings #1, #2, #4, #5 specifically) that these decisions respond to; treat both as the spec.

## Global Constraints

- **Finding #4's fix (owner's choice):** `focusModelPreference`'s unset-pref fallback becomes Priscilla **only when no Answer Focus model is installed at all** (checked across all four models via `_installedVariant`, not just Priscilla). A reader with Ezra (or any model) already installed and an unset preference keeps reading as Ezra -- exactly today's pre-this-plan behavior for them. Only a reader with genuinely nothing installed gets the new Priscilla default. This is the single root-cause fix: it also shrinks finding #2's "stuck forever" scenario to just a genuinely fresh install on a slow device, since an upgrading user is no longer in scope for the new default at all.
- **Finding #1's fix (owner's choice: fix properly, not defer):** `ensureData`'s focus-kind resolution must not require a trial to have already run. When `includeFocus` is true, no `focusChoice` is persisted yet, and `focusModelPreference` is not Ezra, resolve the int8 pack kind directly from the preference (e.g. `FocusModel.priscilla` -> `'priscilla-int8'`) via `PackKind`'s own `dirName`-to-kind-string mapping already used elsewhere (`focusKind`'s own switch in `app_controller.dart:103-111` is the pattern to extend, not replace).
- **Finding #5's fix:** `offerPriscillaDefaultSetup` must also check `focusMode != FocusMode.off`, matching `offerAnswerFocus`'s own existing check.
- **Finding #2's remaining fix (owner's choice: add a lightweight Home warning, not just a silent accurate fallback):** once a completed automatic trial (`AppController.focusTrial`) lands on a model other than the preferred default for a reader who never explicitly chose anything, show a one-time dialog on Home explaining the fallback (not required to be a blocking modal with "try anyway" -- see Task 3 for the exact shape) -- reuse `overrideAccepted`/`acceptOverride` (already generic across all four models, unchanged by this plan) rather than inventing new persisted state for "has this reader seen the fallback explanation".
- **`offerPriscillaDefaultSetup`'s "stops being offered" condition** changes from "once a Priscilla pack is on disk" to "once anything is installed OR the preference is no longer at its default-triggering unset state" -- i.e., it should track the same "nothing installed yet" condition Task 1's `focusModelPreference` fix introduces, not re-derive a separate one.
- Do not change `choose()`, `resolveFallback()`, or `keep()` in `answer_focus.dart` -- the reviewer confirmed their fallback logic is already correct; the bugs are entirely in `AppController`'s and the UI's consumption of them.
- Do not change `RerankerFamily`, the Rust engine, `PackKind`, or any uploaded pack/`index.json`.
- Update the stale doc comments the reviewer flagged: `focusModelPreference`'s own comment (currently claims the warn dialog protects this path, which was not true before this plan and needs to accurately describe the new conditional-fallback behavior after it), and `resolveFallback`'s doc comment in `answer_focus.dart` (currently says "Ezra by default", predates Priscilla's default change -- update to describe the preference parameter generically without naming which model is "the" default, since `answer_focus.dart` itself has no opinion on that).
- Fix the notice copy bug the reviewer found (finding #8, scoped in here since Task 2 already touches this line): "about 1.9 GB total" is wrong once base data is already installed and only the focus pack remains -- compute the actual remaining download description rather than a hardcoded string, or scope the fix to only ever show the notice before base data exists (see Task 2 for the exact call).

## Review Focus

- **A genuinely fresh install where the device fits Priscilla:** tapping "Continue" must result in the Priscilla pack actually being fetched and installed, not just base data -- Task 2's own test must prove this by checking `missing`/the actual download request, not merely `lastRunIncludedFocus` (the previous plan's own test only proved the flag was set, not that it did anything, per finding #1 and finding #7).
- **An upgrading reader with Ezra already installed and an unset preference:** must NOT be re-trialed into Priscilla and must NOT lose working reranking -- `focusModelPreference` must still resolve to Ezra for them, `focusTrialDue` must stay false (no spurious re-trial), and the combined notice must never appear for them at all.
- **A genuinely fresh install on a slow device:** the automatic trial falls back to Ezra (or `FocusChoice.none`), and the reader sees a one-time explanation dialog on Home, not silence and not a notice stuck offering a download forever.
- **The notice correctly disappears once the trial lands on anything** (Priscilla fitting, or Ezra via fallback) -- not just once a Priscilla pack specifically appears on disk, since a slow-device fresh install may correctly end up on Ezra forever without ever having a Priscilla pack on disk at all.
- **Settings' picker must not show "Priscilla selected" while Ezra is what's actually running** -- a reader who opens Settings after a silent/dialog-acknowledged fallback should see the picker accurately reflect what `focusModelPreference` actually resolves to after Task 1's fix (this should fall out of Task 1 automatically since `_ModelPicker`'s `selected: {app.focusModelPreference}` already reads the same getter -- the Review Focus test confirms it, it is not new code).

---

### Task 1: `focusModelPreference`'s fallback becomes conditional on nothing installed

**Files:**
- Modify: `lib/app_controller.dart:141-146` (`focusModelPreference` getter)
- Test: `test/app_controller_focus_notice_test.dart` (new tests alongside Task 1's own tests from the prior plan)

**Interfaces:**
- Consumes: `AppController._installedVariant(FocusModel)` (existing, unchanged, reads pack-store disk state directly).
- Produces: `AppController.focusModelPreference` now returns `FocusModel.priscilla` for an unset pref only when `_installedVariant` is `FocusVariant.none` for every `FocusModel` value; otherwise (anything installed, for any model) returns `FocusModel.ezra` for an unset pref, matching the original pre-Priscilla-default behavior. Tasks 2 and 3 consume this directly -- no new getter needed, every existing caller (`measureDevice`, the Settings picker, `focusTrialDue`) already reads `focusModelPreference`.

- [x] **Step 1: Write the failing tests**

```dart
test('with nothing installed and no preference ever set, the default is still Priscilla', () {
  final controller = AppController.fixed(root: Directory.systemTemp.createTempSync(), user: UserStore.memory());
  expect(controller.focusModelPreference, FocusModel.priscilla);
});

test('with Ezra already installed and no preference ever set, the default stays Ezra, not Priscilla', () {
  final root = Directory.systemTemp.createTempSync();
  _markInstalled(root, PackKind.focusInt8); // copy this helper from answer_focus_trial_test.dart if not already in this file
  final controller = AppController.fixed(root: root, user: UserStore.memory());
  expect(controller.focusModelPreference, FocusModel.ezra);
});

test('with Apollos already installed (not Priscilla) and no preference ever set, the default stays Ezra', () {
  final root = Directory.systemTemp.createTempSync();
  _markInstalled(root, PackKind.apollosInt8);
  final controller = AppController.fixed(root: root, user: UserStore.memory());
  expect(controller.focusModelPreference, FocusModel.ezra);
});
```

(This file already has `_markInstalled` and the `PackKind`/`dart:convert`/`dart:io` imports from the prior plan's Task 3 -- reuse them, do not redefine.)

- [x] **Step 2: Run test to verify it fails**

Run: `flutter test test/app_controller_focus_notice_test.dart`
Expected: FAIL on the second and third new tests (`Expected: FocusModel:<FocusModel.ezra> Actual: FocusModel:<FocusModel.priscilla>`); the first passes already (unconditional-Priscilla and nothing-installed-Priscilla happen to agree).

- [x] **Step 3: Implement the conditional fallback in `lib/app_controller.dart`**

```dart
/// Which model Answer focus should use: the reader's explicit choice (Settings' picker writes this), or --
/// when none has been made yet -- Priscilla if this device has nothing installed at all, else Ezra (an
/// upgrading reader who already has a working installed model, e.g. Ezra, keeps it rather than being silently
/// re-trialed into a model they never asked for and do not have downloaded -- see the fresh-install-fixes
/// plan's own Global Constraints for why). The device trial and warn-and-override dialog still protect a
/// device that does not fit Priscilla when it IS the resolved default (see choose()/resolveFallback() in
/// answer_focus.dart, and the Home-level fallback notice in home_screen.dart for the first-run case).
FocusModel get focusModelPreference {
  final saved = user.pref('focus_model_preference');
  if (saved != null) return FocusModel.values.byName(saved);
  final nothingInstalled = FocusModel.values.every((m) => _installedVariant(m) == FocusVariant.none);
  return nothingInstalled ? FocusModel.priscilla : FocusModel.ezra;
}
```

- [x] **Step 4: Run test to verify it passes**

Run: `flutter test test/app_controller_focus_notice_test.dart`
Expected: PASS, all tests in the file.

- [x] **Step 5: Run the full suite and fix any test that assumed the OLD unconditional-Priscilla fallback**

Run: `flutter test`
Expected: most tests unaffected (`AppController.fixed()` with no `root:` has `_root == null`, so `_installedVariant` returns `FocusVariant.none` for every model via its own `if (_root == null) return FocusVariant.none;` early return -- the `nothingInstalled` check is trivially true for every test from the prior plan that didn't pass a `root:`, so they keep resolving to Priscilla exactly as before). Any failure here means a test DOES pass `root:` and relies on the old unconditional behavior while also having something installed -- fix that test's own setup (it was implicitly relying on "installed state doesn't affect the default", which was never a stated requirement), not this task's new logic. Ledger any such fix as a `Ruling:` with what the test's real intent was and why the fix preserves it.

- [x] **Step 6: Commit**

```bash
git add lib/app_controller.dart test/app_controller_focus_notice_test.dart
git commit -m "fix: default to Priscilla only when nothing is installed yet, not unconditionally"
```

---

### Task 2: `ensureData` resolves a download kind from the preference, not only from a trial

**Files:**
- Modify: `lib/app_controller.dart` (`ensureData`, around line 678-690; also `offerPriscillaDefaultSetup`, lines 175-185)
- Modify: `lib/features/home/home_screen.dart` (the new notice's text, to stop hardcoding "1.9 GB total")
- Test: `test/app_controller_focus_notice_test.dart` (an `ensureData`-level test), `test/widget_test.dart` (fix the existing `group('home', ...)` tests from the prior plan to assert on the real download request, not just `lastRunIncludedFocus`)

**Interfaces:**
- Consumes: `AppController.focusModelPreference` (Task 1's fix), `PackKind` enum (`lib/services/engine/engine_pack.dart`, unchanged), the existing `focusKind` getter's switch pattern (`app_controller.dart:103-111`, read, not modified -- Task 2 adds a sibling resolution path, not a replacement).
- Produces: `ensureData`'s `missing` set now includes the preference-resolved kind (e.g. `'priscilla-int8'`) when `includeFocus` is true, no trial has run yet, and the preference is not Ezra -- no new public method, this is internal to `ensureData`'s own body. `offerPriscillaDefaultSetup` narrows to stop offering once anything is installed (any model) or focus mode is off. Task 3 does not depend on anything new here beyond `offerPriscillaDefaultSetup`'s existing signature.

- [x] **Step 1: Write the failing test for `ensureData` resolving a focus kind with no trial yet**

```dart
test('ensureData requests the preferred model\'s own pack kind even before any trial has run', () async {
  final root = Directory.systemTemp.createTempSync();
  final svc = FakeSearchService((r, id) async => SearchResponse(mode: 'device_trial', raw: {'cpu_ms': 200.0, 'gpu': false}));
  final app = AppController.fixed(root: root, search: svc, user: UserStore.memory());
  expect(app.focusChoice, isNull, reason: 'no trial has run yet in this test');
  expect(app.focusModelPreference, FocusModel.priscilla, reason: 'nothing installed, so Priscilla is the default');
  // ensureData's own missing-kind resolution is exercised directly via a small accessor rather than a real
  // network fetch -- read ensureData's real current body before writing this: if it has no seam to test the
  // `missing` set directly, add the smallest one that does not change ensureData's public behavior (e.g. a
  // private `_missingFocusKind()` helper `ensureData` itself calls, which the test can also call directly).
});
```

Note to implementer: the plan intentionally leaves the exact test seam to your judgment, within this constraint -- the test must prove the *resolved kind string* (e.g. `'priscilla-int8'`) is computed correctly without requiring a real network call or a completed trial, not merely that `ensureData` doesn't crash. If `ensureData`'s current structure makes this awkward without a refactor, extracting a small private pure function (`String? _focusKindToFetch()` or similar, called from both `ensureData` and directly from the test) is the right size of change -- do not restructure `ensureData` beyond that.

- [x] **Step 2: Run test to verify it fails**

Run: `flutter test test/app_controller_focus_notice_test.dart`
Expected: FAIL -- today's `ensureData` only adds `focusKind` (trial-dependent, null pre-trial) to `missing`, never a preference-resolved fallback.

- [x] **Step 3: Implement the preference-resolved kind in `lib/app_controller.dart`'s `ensureData`**

Extend the `missing` set construction (currently `if (includeFocus && focusKind != null && !focusInstalled) focusKind!`) so that when `includeFocus` is true and `focusKind` is null (no trial yet) but `focusModelPreference != FocusModel.ezra`, it adds that preference's own int8 pack kind instead -- reuse the exact string values `focusKind`'s own switch already uses (`'priscilla-int8'`, `'apollos-int8'`, `'aquila-int8'`; Ezra needs no such fallback, since Ezra is always installable and was never the problem). Use the model's own `PackKind` (`PackKind.priscillaInt8.format`-style resolution is the WRONG value here -- `focusKind`'s strings are the pack-store `dirName`s used by `downloadAndInstall`'s dispatch switch and `checkHost`'s remote index, read that switch again before writing this to use the exact right string per model). Do not fetch anything for a model that is already installed (`_installedVariant(preference) != FocusVariant.none` guards this, mirroring `!focusInstalled`'s own intent for the trial-based path).

- [x] **Step 4: Run test to verify it passes**

Run: `flutter test test/app_controller_focus_notice_test.dart`
Expected: PASS.

- [x] **Step 5: Fix `offerPriscillaDefaultSetup`'s stale conditions**

```dart
/// Offered once, on a device that has nothing installed and has never had a model explicitly chosen -- see
/// focusModelPreference's own conditional default (Task 1). Stops being offered once dismissed, once anything
/// is installed (any model -- not just Priscilla: a reader who ends up on Ezra via the first-run fallback,
/// see home_screen.dart's own fallback notice, should not keep seeing this one too), or while focus is off.
bool get offerPriscillaDefaultSetup =>
    _root != null &&
    user.pref('focus_model_preference') == null &&
    FocusModel.values.every((m) => _installedVariant(m) == FocusVariant.none) &&
    focusMode != FocusMode.off &&
    user.pref('focus_declined') != '1';
```

- [x] **Step 6: Fix the notice's hardcoded "1.9 GB total" copy in `lib/features/home/home_screen.dart`**

The simplest correct fix: this notice (per Task 1/2's own narrowed conditions) now only ever shows while NOTHING is installed, so "Continue" always fetches both base data and the focus pack together in the same call -- the 1.9 GB figure is accurate in every state this notice can actually appear in. Confirm this reasoning holds (re-read `offerPriscillaDefaultSetup`'s final form against `missingData`/`focusInstalled`'s real behavior) before deciding whether the copy needs to change at all or whether finding #8 was actually a symptom of finding #1/#5 rather than its own bug -- if it's already correct once Tasks 1-2 land, say so in the ledger rather than making a needless change.

- [x] **Step 7: Run the full suite**

Run: `flutter test`
Expected: PASS. In particular, re-check the prior plan's own two widget tests in `test/widget_test.dart`'s `group('home', ...)` (`'a fresh install ... shows one combined notice'` and `'once the reader explicitly picks a model ... never shows again'`) -- per this plan's Review Focus, the first one's assertion must be strengthened from `app.lastRunIncludedFocus == true` to something that actually proves the Priscilla pack kind was requested (e.g. assert on the fake search service's recorded `checkHost`/download request, or on whatever seam Step 1-3 introduced) -- a passing assertion that doesn't prove the real behavior is exactly the gap finding #1 and finding #7 both named. Fix this test's assertion, not just the production code.

- [x] **Step 8: Commit**

```bash
git add lib/app_controller.dart lib/features/home/home_screen.dart test/app_controller_focus_notice_test.dart test/widget_test.dart
git commit -m "fix: ensureData fetches the preferred model before any trial has run"
```

---

### Task 3: First-run fallback notice on Home

**Files:**
- Modify: `lib/app_controller.dart` (small new state: whether the completed trial's result should be surfaced once)
- Modify: `lib/features/home/home_screen.dart` (new dialog, triggered once per completed `focusTrial` that fell back)
- Test: `test/widget_test.dart` (new tests in `group('home', ...)`), `test/app_controller_focus_notice_test.dart` (if new `AppController` state needs its own unit coverage)

**Interfaces:**
- Consumes: `AppController.focusTrial` (existing `Future<bool>?`, written by `_startEngineNow`/`_startEngine`'s own trial-trigger block, unchanged by this plan), `AppController.focusChoice`, `AppController.focusModelPreference` (Task 1's fix), `AppController.overrideAccepted`/`acceptOverride` (existing, model-generic, unchanged).
- Produces: nothing further tasks consume -- this task closes out the plan's own remaining Global Constraint (the lightweight Home warning) and Review Focus item (slow-device fresh install sees an explanation, not silence).

- [x] **Step 1: Decide and write the failing test for the trigger condition**

Read `_startEngineNow`'s real current body (`app_controller.dart:389-447`, confirmed this session) fresh before writing this -- `focusTrial` is set only inside `_startEngineNow`, which itself only runs once the search engine is actually ready (base data installed, library opened); on a true fresh install this means `focusTrial` stays `null` until the combined notice's own base-data download (Task 2) finishes and the engine starts. The Home screen's dialog trigger (Step 7) must tolerate `focusTrial == null` (nothing to react to yet -- same state as today) and must re-check once it becomes non-null (a rebuild driven by `AppController`'s own `notifyListeners()`, which `_startEngineNow` already calls before setting `focusTrial`, and `measureDevice()` already calls at the end of the trial -- confirm both call sites still notify after your Step 3 changes, don't add a new listener mechanism).

The dialog must fire only for a reader who (a) had `focusModelPreference` resolve to something other than Ezra by the new unset-pref default (i.e., Task 1's "nothing installed" case specifically -- an explicit non-Ezra pick already has its own Settings-level warning path and must NOT also get this one), and (b) whose trial's result (`focusChoice` after `focusTrial` completes) came back on a different model than `focusModelPreference`. Write the test against whatever small accessor/state you introduce in Step 2 -- name it, and write its test here, before implementing:

```dart
test('<name reflecting what you chose to expose, e.g. "focusFellBackFromDefault is true after a trial that could not fit the default">', () {
  // Arrange: AppController.fixed with nothing installed (so focusModelPreference resolves to Priscilla),
  // a FakeSearchService whose device_trial response makes choose() fall back to Ezra, then run the trial.
  // Assert the new accessor reflects the fallback.
});
```

- [x] **Step 2: Run test to verify it fails**

Run: `flutter test test/app_controller_focus_notice_test.dart`
Expected: FAIL -- the accessor from Step 1 doesn't exist yet.

- [x] **Step 3: Implement the small new state in `lib/app_controller.dart`**

The simplest correct shape: a getter computed from existing state (`focusChoice`, `focusModelPreference`, and whether the reader has ever seen/dismissed it -- reuse `overrideAccepted(focusModelPreference)`/`acceptOverride(focusModelPreference)` for the "seen it" bookkeeping rather than inventing a new pref key, since `acceptOverride`'s own doc comment already frames it as "the reader was warned X likely doesn't fit this device and chose to try it anyway", which is close enough in spirit to reuse -- or, if that framing doesn't actually fit this notice's own semantics on reflection, a new single pref key `home_fallback_seen_<model>` following the same naming convention `override_accepted_${m.name}` already uses. Make this call explicitly and say which you picked and why in the commit.

- [x] **Step 4: Run test to verify it passes**

Run: `flutter test test/app_controller_focus_notice_test.dart`
Expected: PASS.

- [x] **Step 5: Write the failing widget test for the dialog itself**

```dart
testWidgets('a fresh install on a slow device shows a one-time explanation when the trial falls back off Priscilla', (tester) async {
  // Arrange: AppController.fixed(root: ...) with a FakeSearchService whose device_trial response is slow enough
  // that choose() falls back to Ezra for the Priscilla preference. Pump the real ScripturesReaderApp and await
  // the engine's own automatic trial (focusTrial) the same way main.dart's own startup sequence does.
  await tester.pumpAndSettle();
  expect(find.textContaining('Ezra'), findsWidgets); // the dialog or an equivalent notice names what it fell back to
  // Dismiss it (however Step 3/6's shape dismisses), then rebuild: it must not reappear.
});
```

- [x] **Step 6: Run test to verify it fails**

Run: `flutter test test/widget_test.dart`
Expected: FAIL -- no such dialog exists yet.

- [x] **Step 7: Implement the dialog in `lib/features/home/home_screen.dart`**

Trigger it from a place that can `await` or react to `app.focusTrial` completing (e.g. a `FutureBuilder`/listener on `app.focusTrial`, or checking the new Step 3 accessor inside the existing `AnimatedBuilder`/`ListenableBuilder` this screen already rebuilds from -- read the screen's real current build structure around the existing notice chain before choosing). Content: name the model the reader was defaulted to (Priscilla) and what's running instead (Ezra), with a single acknowledge action that marks it seen (Step 3's bookkeeping) -- this is explicitly NOT required to offer a "try it anyway" override (that already exists in Settings for a reader who wants to revisit the choice later); keep it to one dismiss action, matching the plan's own "lightweight" framing from the Global Constraints.

- [x] **Step 8: Run test to verify it passes**

Run: `flutter test test/widget_test.dart`
Expected: PASS.

- [x] **Step 9: Run the full suite**

Run: `flutter test`
Expected: PASS, no regressions.

- [x] **Step 10: Commit**

```bash
git add lib/app_controller.dart lib/features/home/home_screen.dart test/app_controller_focus_notice_test.dart test/widget_test.dart
git commit -m "feat: explain a first-run fallback off Priscilla instead of leaving it silent"
```

## Execution record

Implemented on `priscilla-default-fresh-install` in commits `f338e09`, `e969e7b`, and `338c082`.

- Task 1: conditional default protects existing installed Ezra users; completed and independently reviewed.
- Task 2: pretrial download requests resolve the real preferred pack kind; completed and independently reviewed. Off, completed-none, installed-pack, and actual Continue-request cases are covered.
- Task 3: one-time Home fallback explanation, persisted automatic selection, and content-store handoff; completed and independently reviewed.
- Validation: full Flutter suite 348 passed, 46 skipped; 112 focused tests passed; changed-file analysis and whitespace checks clean. Native/artifact-dependent tests retain their existing skips.

Implementation decisions made against the current code:

1. Acknowledge with `home_fallback_seen_priscilla`, not `acceptOverride`, because the latter forces another model trial. This uses Task 3's explicit exception. Reversing it would require a small preference migration/removal.
2. Describe remaining base-data versus focus-only setup without a fixed total size; no installed focus model does not imply base data is absent. Reversing it is copy-only work.
3. Keep a separate `focus_automatic_model` for this fresh flow, with explicit Settings choices authoritative and unmarked existing installs retaining Ezra. Without it, installing Priscilla changes the conditional default to Ezra on restart. Reversing it would require a small preference migration and lifecycle revalidation.
4. Stop the combined setup offer after any completed trial choice, including none, then use the ordinary chosen-model offer. This follows Review Focus rather than the sample getter's omitted condition. Reversing it changes notice timing.

Final whole-branch review approved production behavior. Its one minor fixture-cleanup finding was fixed in `189f79f`; the affected widget test passed and scoped re-review found no outstanding issues. The branch is ready for integration review. Work remains on `priscilla-default-fresh-install`; no merge or push was performed.
