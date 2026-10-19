# Richer inputs for the Compass/BGE combination: frozen protocol

2026-10-19. Written before any new inference, model fitting, or label beyond what
[ANSWER_FOCUS_CALIBRATION_RESULTS.md](ANSWER_FOCUS_CALIBRATION_RESULTS.md) already opened. Offline only; no production
code, model pack or reader preference changes until a result here earns that separately.

## Why

The frozen 2-feature model (standardized Compass score, standardized BGE logit) showed real but weak separation: in
the 120-row calibration sample, mean predicted probability for direct(2) vs. related(1) vs. nonanswer(0) differed by
only a few hundredths within any rank band (e.g. top band: 0.384 / 0.342 / 0.288). The two inputs are each already a
blend or a single-verse judgment; neither carries enough information on its own for a straight-line combination to
separate the three grades well. The owner chose **richer inputs / a different architecture** over fitting harder on
the same two numbers.

This protocol covers two changes made together, as agreed:

- **A. Unblend what the engine already computes.** `Index::search_balanced` (`engine/src/search.rs`) computes four
  z-scored lane values (`zd` dense/meaning, `zs` sparse/keyword, `zc` ColBERT/thread, `zg` genome) and collapses them
  into one `fused` score before building `Hit`. The per-lane values exist in scope at that point and are discarded.
  This surfaces them, opt-in only (see Engineering below): no engine change to the values the production app computes
  or receives unless it asks for them.
- **C. A model family that can use interactions.** The frozen model was `sigmoid(w1*x1 + w2*x2 + b)`, which cannot
  express "BGE only matters when dense is already high" or similar conditional patterns. With 5 inputs
  (`dense, sparse, colbert, genome, bge_logit`) a straight line is a worse fit than it was for 2; this protocol
  compares it against `HistGradientBoostingClassifier` (already available via the installed scikit-learn; no new
  dependency), a small tree-ensemble that can express interactions while still taking only these 5 scalar inputs —
  no verse, book, or doctrinal-category feature, same constraint as the frozen model.

**B (context windows) is explicitly out of scope here.** It already has one negative result (verse-alone beat
verse+context in the stage-2 test) and needs its own frozen protocol and test if revisited. This experiment must not
silently fold context-window scoring in through a side door.

## Engineering: opt-in lane exposure

Add a `"lanes": true` request flag to the `search`/`semantic` ops. When absent (every existing caller, including the
shipped app), the response is byte-identical to today. When present, each hit additionally carries
`"lanes": {"dense": zd[i], "sparse": zs[i], "colbert": zc[i], "genome": zg[i]}` — the same z-scored values already
used to build `fused`, not a new computation. Thread/ColBERT is 0.0 for every candidate when the profile's `thread`
weight is 0 or the ColBERT pack is absent, matching how `zc` already behaves in `search_balanced` today.

Test first (`engine/tests/`): a request without `lanes` is byte-identical to the current golden response; a request
with `lanes: true` returns 4 lane values per hit that reconstruct the existing `score` under the request's own
profile weights (`w.echo*dense + w.spark*sparse + w.thread*colbert + w.root*genome == score`, within float tolerance)
for both a Thread-enabled and a Thread-disabled profile.

## Reused data, reused splits

Same train (72) / calibration (8) / test (10) questions as
[ANSWER_FOCUS_CALIBRATION_PROTOCOL.md](ANSWER_FOCUS_CALIBRATION_PROTOCOL.md), same labels already compiled there
(`local-benchmarks/answer-focus-calibration/review-v2/grades.json`,
`test-topfive-grades.json`). No new question authoring, no new blind review of previously-graded passages. New
inference is needed only to capture the 4 lane values per candidate (the BGE logits are already scored and reused
unchanged). Candidates whose lane values cannot be captured because they fall outside what was already scored for a
split (the 30-candidate historical pool for `train`, the 200-candidate pool for `calibration`/`test`) are recorded as
unavailable for the 5-input model and excluded from its training/evaluation rows only; the frozen 2-input baseline's
numbers from ANSWER_FOCUS_CALIBRATION_RESULTS.md are unaffected and serve as the comparison baseline throughout.

## Models compared

1. **Baseline (frozen, unchanged):** 2-input monotonic logistic, `w_compass=0.182, w_bge=0.389, intercept=-0.659`,
   from the prior stage. Its calibration (Platt + cutoff 0.11) and test-report numbers are not recomputed.
2. **5-input monotonic logistic:** same fitting method (sum of weighted log loss + L2=1 on slopes, all 5 slopes
   constrained nonnegative, standardized features, question-weighted, grouped 5-fold CV diagnostic) as the frozen
   model, extended to 5 inputs. Nonnegativity here means "no input may be rewarded for being lower" for any of the
   5 — the same anti-extrapolation reasoning as before, applied to each lane independently.
3. **5-input HistGradientBoostingClassifier:** scikit-learn defaults except `max_depth` capped at 3 (keeps the model
   simple enough to inspect; deeper trees are not justified by 1,220 labeled training rows) and `random_state=0`.
   No verse/book identity feature. Monotonic constraints are not available in the installed scikit-learn version for
   this estimator; if the fitted model's partial dependence on any input is net negative, that is reported as a
   finding, not silently accepted — a negative partial dependence on a retrieval signal is exactly the extrapolation
   failure the monotonic constraint exists to prevent, and must be flagged before this model is used for ranking.

Report 5-fold grouped CV log loss for both new models alongside the frozen baseline's recorded 0.628 (model 1) /
0.656 (null), on the same fold-generation function and seed so the comparison is apples to apples.

## Calibration and cutoff

Refit Platt scaling and re-select the cutoff (same 120-row probability-sampled calibration set, same existing
grades, no new review) independently for whichever of models 2/3 is carried forward to the final test — only the one
with the better CV log loss, decided before looking at calibration-sample performance. If models 2 and 3 tie within
0.01 log loss, prefer model 2 (fewer assumptions, directly comparable to the frozen baseline's monotonicity
guarantee).

## Final test

Reuse the existing 10-question test split and its compiled grades
(`test-topfive-grades.json`) for the top-5 comparison. The frozen model's test-report numbers
(direct P@5 0.350, related P@5 0.550, any-direct 0.625, abstains correctly on 0/2 absent questions under cutoff) are
the fixed comparison point; they are not rerun. Add the 5-input model (whichever variant was calibrated) as method 6
in the test-report table, scored with the same `score_method` fixed-slot logic (missing/abstained = 0).

**New top-5 passages this candidate set did not already produce** (if the 5-input ranking promotes any verse that
was not in any of the original 5 methods' top-5 unions) must be pooled into their own blind-review packet before
scoring — reusing the existing `test-topfive-grades.json` as-is for a ranking that surfaces different passages would
silently treat unjudged passages as nonanswers, which the existing `score_method`/`validate_decisions` machinery
already refuses to do by construction (unjudged = excluded from the denominator in `direct_of_displayed`, counted
as 0 only in the fixed-slot P@5 per the protocol's own explicit rule) — but the *set of passages needing a grade*
must be re-derived, not assumed to match the prior run.

## What would justify moving further (e.g. toward B, or toward app integration)

- CV log loss meaningfully below the frozen model's 0.628 (a > 0.02 absolute improvement, chosen as a threshold
  before seeing any result, roughly twice the spread already seen between CV folds on the frozen model).
- No new false-promotion pattern on the final test beyond what the frozen model already showed.
- Correct abstention preserved or improved on the 2 absent-answer test questions under the refit cutoff.

A result that fails any of these is still reported in full, per the standing rule in every prior protocol here: a
negative or mixed finding is preserved, not hidden or re-tuned until it looks better.

## Reproduce

```powershell
# after the engine change and its tests pass:
cargo test --manifest-path engine/Cargo.toml lanes
.venv/Scripts/python.exe -I tool/answer_focus_richer_inputs_infer.py train|calibration|test
.venv/Scripts/python.exe -I tool/answer_focus_richer_inputs_run.py fit
.venv/Scripts/python.exe -I tool/answer_focus_richer_inputs_run.py calibrate
.venv/Scripts/python.exe -I tool/answer_focus_richer_inputs_run.py test-report
```
