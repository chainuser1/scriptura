# Richer inputs for the Compass/BGE combination: results

2026-10-19. Protocol: [ANSWER_FOCUS_RICHER_INPUTS_PROTOCOL.md](ANSWER_FOCUS_RICHER_INPUTS_PROTOCOL.md), frozen before
any new inference, fitting or label. Offline only; the opt-in `lanes` engine flag is the only code change, and it is
a no-op unless a caller explicitly asks for it (three engine tests prove this: `engine/tests/lanes_e2e.rs`). No
application behavior, model pack or reader preference changed.

## Decision

**Neither new input (the 3 extra raw lanes) nor the new model family (gradient boosting) clearly beats the frozen
2-feature baseline.** The 5-input logistic model is statistically indistinguishable from the 2-feature one on
cross-validation (0.627 vs. 0.628 log loss) and scores worse on the calibration-sample F1 (0.286 vs. 0.358). It does
edge out the baseline on the final test's direct-answer rate (0.375 vs. 0.350), but on a sample this small (8
questions) that is not evidence of a real improvement -- see "How much to trust this" below. Gradient boosting is
worse on every measure tried and is additionally disqualified from ranking use by its own result: it is
non-monotonic on all 5 inputs, meaning it would sometimes reward a *lower* retrieval score, the exact failure the
monotonic constraint exists to prevent.

This is a negative-to-mixed result on the specific question asked ("does exposing dense/sparse/colbert alongside
genome+BGE, and/or a non-linear model, help a straight-line combination that was stuck on 2 features"). It is
preserved here in full, not re-tuned to look better, per the standing rule in every protocol in this research line.

## Engineering: opt-in lane exposure (built, tested, unused by the app)

`search`/`semantic` now accepts `"lanes": true`. Absent or `false`: byte-identical response to today (tested).
Present: each hit gains `"lanes": {"dense", "sparse", "colbert", "genome"}`, the same z-scored values already
computed to build `score` -- verified to reconstruct `score` exactly (within 1e-6) under the request's own profile
weights, for both a ColBERT-enabled profile (Compass) and a ColBERT-disabled one (Lantern, where the colbert lane is
confirmed 0.0). Full engine suite remains green (45/45 across 9 test files) after the change.

## Cross-validation (train split, 72 questions, 1,220 labeled candidates, grouped 5-fold)

| Model | CV log loss (mean) | Per-fold range |
|---|---:|---|
| Frozen 2-feature baseline (recorded) | 0.628 | 0.583 - 0.661 |
| 5-feature monotonic logistic | 0.627 | 0.578 - 0.658 |
| 5-feature HistGradientBoostingClassifier | **0.694** | 0.638 - 0.753 |

The 5-feature logistic model is a rounding-level improvement over the 2-feature one (0.0005), well inside the spread
already seen between CV folds of the *same* model (up to 0.08). Gradient boosting is clearly worse, consistent with
overfitting on ~1,000 training rows per fold -- too little for a tree ensemble with this few total examples to
generalize, even at the protocol's capped `max_depth=3`. **Chosen model: 5-feature logistic**, per the frozen rule
(boosted lost outright, not a near-tie).

**Boosted model monotonicity check (protocol requirement, not skipped):** non-monotonic on all 5 features
(`dense, sparse, colbert, genome, bge_logit`) -- confirmed on real data, and also reproduced on a synthetic sanity
check during development (a feature with a strong *true* positive effect still came out non-monotonic in the
unconstrained fit). This independently disqualifies gradient boosting for ranking here, on top of its worse CV loss.

## Calibration (same 120-row probability sample and grades as the frozen baseline; no new review)

| | Platt slope | Cutoff | F1 at cutoff |
|---|---:|---:|---:|
| Frozen 2-feature baseline (recorded) | 2.572 | 0.11 | 0.358 |
| 5-feature logistic | 2.629 | 0.13 | **0.286** |

The 5-feature model's calibration-sample F1 is lower than the 2-feature baseline's. Combined with the near-zero CV
gain, this is a second independent signal that the 3 extra lanes did not meaningfully help separate direct answers
from related/nonanswer on this labeled set.

## Final test (same 10 held-out questions, 8 answerable + 2 absent, as the frozen baseline)

8 new top-5 passages the unfiltered 5-feature ranking surfaced (not in the baseline's already-graded set) were
pooled and blind-reviewed before scoring, per protocol; all 8 graded 0 or 1, none direct. The cutoff-filtered variant
needed no additional review (it only ever removes candidates from the unfiltered ranking, verified programmatically
before scoring, never adds one).

| Method | Direct P@5 | Related P@5 | Any-direct | Mean shown | Absent-question results |
|---|---:|---:|---:|---:|---|
| Answer Focus today (baseline) | 0.350 | 0.550 | 0.625 | 5.0 | 5, 5 |
| 2-feature learned, unfiltered (baseline) | 0.350 | 0.625 | **0.750** | 5.0 | 5, 5 |
| 2-feature learned + cutoff (baseline) | 0.350 | 0.550 | **0.750** | 4.5 | **0, 0** |
| **5-feature learned, unfiltered** | **0.375** | 0.600 | 0.625 | 5.0 | 5, 5 |
| **5-feature learned + cutoff** | **0.375** | 0.550 | 0.625 | 4.4 | **0, 0** |

The 5-feature model has the single highest direct-P@5 of any method tested across this and the prior stage (0.375),
and its cutoff variant still abstains correctly on both absent-answer questions, matching the 2-feature cutoff
variant's best-in-class behavior there. But it loses ground on any-direct (0.625 vs. 0.750): the 2-feature model
finds *at least one* real answer for more questions, even where it finds fewer per question; the 5-feature model's
gain is concentrated, not spread. Related-P@5 also does not improve over the 2-feature model.

## How much to trust this

**Not very, on its own.** n=8 answerable test questions; a one-question swing changes direct-P@5 by 0.125. The gap
between 0.350 and 0.375 is one question's worth of difference. Combined with a near-zero CV gain and a *worse*
calibration-sample F1, the most defensible reading is: **this experiment did not find clear evidence that the 3
extra lanes help**, and the final-test uptick is more likely sampling noise than a real signal, though it cannot be
ruled out with what has been reviewed so far. The protocol's own whole-list probability sample (still not run for
either the 2-feature or 5-feature model) is the step that would actually quantify this uncertainty rather than
leave it as a one-line caveat.

## What this does and does not rule out

- It does not mean the lane scores carry *no* information the 2 blended numbers lack -- see the CV diagnostic in
  `docs/ANSWER_FOCUS_RICHER_INPUTS_PROTOCOL.md`'s own reasoning for why this was worth testing cheaply. It means a
  straight-line combination of them, on 1,220 labeled training rows, could not extract a meaningfully larger gain
  than the 2-feature version already captures from the single blended Compass score.
- It does not test B (context windows), which remains out of scope here per the frozen protocol, with its own
  earlier negative result still standing.
- It does not test whether more labeled training data (beyond the historical 72-question set) would let either
  model, especially gradient boosting, separate the signals better -- 1,220 rows is a small training set for 5
  features, and the boosted model's failure here is consistent with needing more data, not necessarily with the
  idea itself being wrong.

## Reproduce

```powershell
cargo test --release --manifest-path engine/Cargo.toml --test lanes_e2e
.venv/Scripts/python.exe -I tool/answer_focus_richer_inputs_infer.py train|calibration|test
.venv/Scripts/python.exe -I tool/answer_focus_richer_inputs_run.py fit
.venv/Scripts/python.exe -I tool/answer_focus_richer_inputs_run.py calibrate
.venv/Scripts/python.exe -I tool/answer_focus_richer_inputs_run.py test-new-items   # lists passages needing a blind grade
.venv/Scripts/python.exe -I tool/answer_focus_richer_inputs_run.py test-report
```

Private run folder: `local-benchmarks/answer-focus-richer-inputs/` (hash-bound provenance chain; a stale artifact
refuses to proceed rather than silently reusing it, same as the calibration stage).
