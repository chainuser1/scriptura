# Keyword concentration: a 6th input for the learned combination

2026-10-19. Written before any new inference, fitting or label beyond what
[ANSWER_FOCUS_RICHER_INPUTS_RESULTS.md](ANSWER_FOCUS_RICHER_INPUTS_RESULTS.md) already opened. Offline only; no
production code, model pack or reader preference changes until a result here earns that separately.

## Why

Reading the calibration-sample grading reasons (120 blind judgments,
[ANSWER_FOCUS_RICHER_INPUTS_RESULTS.md](ANSWER_FOCUS_RICHER_INPUTS_RESULTS.md)) shows a repeated pattern: a verse
graded "related, not direct" because it shares one topical word with the question ("witness", "permitted") without
making the specific claim the question asks about. Example: for "Can an accusation be established by only one
witness?", several verses using the word "witness" in an unrelated sense (an eyewitness account, a devotional
"bearing witness", witnesses "by which the world shall be judged") were graded related, while the two verses stating
the actual two-or-three-witness legal standard were graded direct. Today's sparse (keyword) lane sums every matching
word's contribution into one number; a verse that matches broadly across several relevant words and a verse that
matches narrowly on one topical word currently produce indistinguishable-looking sparse scores if their sums happen
to be similar. The distribution of the match (concentrated in one word vs. spread across several) is computed
internally and discarded before it reaches any lane score.

This protocol adds one more derived number -- not a new retrieval pass, not a wider candidate pool, not a different
model family -- to the same 5-input logistic model from the richer-inputs stage.

## The new input

In `Index::sparse_scores` (`engine/src/search.rs`), the per-term contributions `self.csr.data[k] * dense_q[...]` are
summed into `s` and the per-term values discarded. This adds, alongside the existing sum, the single largest
per-term contribution `max_term`. The new feature for the learned model is
**`concentration = max_term / s`** (defined as 0 when `s <= 0`, since there is nothing to concentrate): close to 1
means the sparse score came almost entirely from one word; closer to 0 means it was spread across several.

**Engineering, opt-in, same pattern as the `lanes` flag:** a `"concentration": true` request flag on `search`/
`semantic`. Absent or `false`: response unchanged (tested). Present: each hit's `lanes` object gains a `concentration`
field. Costs one extra running max alongside the existing sum in `sparse_scores`; no new pass over the data.

Test first (`engine/tests/`): without the flag, byte-identical to today (including with `lanes: true` alone, which
must not gain a `concentration` field unless separately requested). With the flag: `concentration` is in `[0, 1]`
for every hit; a synthetic single-term match (one shared word only) gives `concentration` close to 1; reconstructing
`max_term` as `concentration * sparse_lane_score` from the response and comparing against a value computed
independently in the test (same formula, different code path) matches within float tolerance.

## Reused data, reused splits, reused rule

Same train (72) / calibration (8) / test (10) questions, same grades, same models.json/calibration.json chosen-model
convention as [ANSWER_FOCUS_RICHER_INPUTS_PROTOCOL.md](ANSWER_FOCUS_RICHER_INPUTS_PROTOCOL.md). Only the 5-input
monotonic logistic is extended to 6 inputs (`dense, sparse, colbert, genome, bge_logit, concentration`); gradient
boosting is not retried here -- it already failed independently of input count (non-monotonic on all 5 inputs, worse
CV loss), and adding one more feature does not address either problem.

**Monotonicity direction:** concentration gets no sign assumption baked in before fitting (unlike the other 5
inputs, there is no obvious a priori reason higher concentration should mean more or less likely to be a direct
answer -- a one-word match could be the single decisive legal term, or could be an accidental overlap). The
nonnegative-slope constraint used for the other 5 features is **not** applied to this one; its fitted sign is itself
part of what this experiment reports, not assumed.

## Models compared

1. **Frozen 5-feature baseline (recorded):** CV log loss 0.627, calibration F1 0.286, final test direct P@5 0.375 /
   0.375 (unfiltered / cutoff) -- from ANSWER_FOCUS_RICHER_INPUTS_RESULTS.md, not recomputed.
2. **6-feature monotonic-except-concentration logistic:** same fitting method (sum of weighted log loss + L2=1,
   standardized features, question-weighted, grouped 5-fold CV), 5 slopes constrained nonnegative, the 6th
   (concentration) unconstrained.

## Decision rule (frozen before any result)

Report the CV log loss change versus the 5-feature baseline's recorded 0.627, the calibration-sample F1 versus
0.286, and the final-test direct P@5 versus 0.375 (both unfiltered and cutoff variants), exactly as
ANSWER_FOCUS_RICHER_INPUTS_RESULTS.md did.

**What would count as a real improvement, agreed with the owner before this runs:**
- CV log loss improves by more than 0.01 (the richer-inputs experiment's 0.0005 gap was explicitly too small to
  trust; this sets a real bar).
- Final-test direct P@5 improves by more than one question's worth (> 0.125 would be one question on 8; a smaller
  gap is not treated as a win, per the owner's standing instruction not to call a 1-question swing a success).
- No regression on any-direct rate or on correct abstention for the 2 absent-answer test questions.

A result that does not clear this bar is reported in full as a negative or inconclusive finding, not re-tuned or
reframed. This is the same discipline as every prior stage in this research line.

## Reproduce

```powershell
cargo test --manifest-path engine/Cargo.toml --test concentration_e2e
.venv/Scripts/python.exe -I tool/answer_focus_concentration_infer.py train|calibration|test
.venv/Scripts/python.exe -I tool/answer_focus_concentration_run.py fit
.venv/Scripts/python.exe -I tool/answer_focus_concentration_run.py calibrate
.venv/Scripts/python.exe -I tool/answer_focus_concentration_run.py test-new-items
.venv/Scripts/python.exe -I tool/answer_focus_concentration_run.py test-report
```
