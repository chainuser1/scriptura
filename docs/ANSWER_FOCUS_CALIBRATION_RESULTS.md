# Learned Compass/BGE combination: results

2026-10-19. Protocol: [ANSWER_FOCUS_CALIBRATION_PROTOCOL.md](ANSWER_FOCUS_CALIBRATION_PROTOCOL.md), frozen before this
experiment's fresh inference or labels. Offline only; no production code, model pack or reader preference changed.

## What this measures and what it does not

A two-feature (standardized Compass score, standardized BGE int8 logit) logistic combination with nonnegative
slopes, trained on the 72-question historical label set, calibrated on 8 fresh questions, and tested once on 10
further fresh questions whose labels were opened only after the model and cutoff were frozen. All grading was a
single exploratory AI (Claude) pass, blind to method/rank/score; it is not independent review. **n = 8 answerable
test questions.** Every gap below is small enough that it should be read as indicative, not confirmatory; the
protocol's own text anticipated this ("the estimates may be very imprecise").

## A bug found and fixed before any grading

The first implementation had two defects, caught and corrected before the 120-item calibration sample was graded:
(1) the rank-band sampler banded candidates by Compass's own order instead of the fitted model's order, which would
have sampled the wrong population entirely; (2) the training objective used mean loss against a fixed-scale L2
penalty, making the penalty roughly 72x stronger than the protocol's specified "L2 = 1" and crushing both slopes
toward zero (CV log loss 0.649 vs. null 0.653 -- indistinguishable from doing nothing). Fixed objective: sum of
weighted losses (each question still totaling weight one) plus the stated penalty. Preserved in
`local-benchmarks/answer-focus-calibration/review-v2/` (original artifacts never overwritten); the corrected run is
reported below.

## Cross-validation diagnostic (train split, 72 questions, 1,220 labeled candidates)

5-fold grouped-by-question CV, scaler and model refit inside each fold:

| | Mean log loss | Per-fold range |
|---|---:|---|
| Null (always predict base rate) | 0.656 | -- |
| Fitted (L2=1) | 0.628 | 0.583 - 0.661 |

Final model (fit once on all of train): `w_compass=0.182, w_bge=0.389, intercept=-0.659`. Raw single-feature
correlations with the direct-answer label were weak on their own (Compass 0.14, BGE 0.23); the combination improves
on either alone but remains a blunt two-feature linear model by design -- no verse, book, or doctrinal-category
feature is used.

## Calibration (120-row probability sample, rank bands 1-10/11-50/51-200, 8 fresh questions)

Platt scaling: `slope=2.572` (positive, confirming the ranking logit tracks the graded outcome), `intercept=0.287`.
Cutoff selected by inverse-probability-weighted F1 over the grid 0.00-1.00: **0.11**, F1 = **0.358**. Label
distribution in the sample: 75 non-answer, 27 related, 18 direct (15.0% direct rate). F1 0.358 beats the naive
"always predict direct" baseline (0.261 at this base rate), so this is real signal, not a base-rate artifact -- but
0.358 is a modest classifier, not a strong one, and is reported as such.

## Final test (10 held-out questions: 8 answerable, 2 absent; 90 pooled top-5-union passages, fully reviewed)

Fixed-slot P@5 (a missing or abstained slot counts as zero, per protocol):

| Method | Direct P@5 | Related P@5 | Any-direct rate | Mean shown | Absent-question results |
|---|---:|---:|---:|---:|---|
| 1. Answer Focus today (BGE sorts Compass top 10) | 0.350 | 0.550 | 0.625 | 5.0 | 5, 5 |
| 2. BGE over the full 200-candidate pool, unfiltered | 0.300 | 0.525 | 0.625 | 5.0 | 5, 5 |
| 3. Learned combination, unfiltered | 0.350 | 0.625 | 0.750 | 5.0 | 5, 5 |
| 4. Learned combination + frozen cutoff | 0.350 | 0.550 | 0.750 | 4.5 | **0, 0** |
| 5. BGE-above-mean (diagnostic control) | 0.300 | 0.525 | 0.625 | 5.0 | 5, 5 |

**No method clearly beats today's shipped Answer Focus on direct P@5 at this sample size** (methods 1, 3 and 4 tie
at 0.350; methods 2 and 5 are lower, consistent with the wide-pool pilot's earlier finding that unfiltered wider
pools do not help). The learned combination's advantage is on the softer measures: related P@5 rises from 0.550 to
0.625 (method 3) and any-direct rises from 0.625 to 0.750 (methods 3 and 4) -- more questions get at least one real
answer somewhere in the top five, even where they do not get more of them.

**Method 4 is the only method tested anywhere in this research line that abstains correctly on both absent-answer
questions** (0 results shown for "what is the model number of the phone I am using" and "how many grams of protein
are in 100 grams of cooked rice", against 5 results from every other method including today's shipped behavior).
That is a real result on 2 questions, not a validated abstention mechanism -- two questions cannot establish a false
non-response rate. The cutoff's cost shows on `test-other-side` ("what should I do with a report about someone
before I have heard the other side"): it trims from 5 shown (1 related) down to 1 shown (0 related), over-trimming a
question with a real but weak signal rather than reserving abstention for the truly empty cases. That is the
predictable trade-off of a single frozen threshold, not a defect unique to this fit.

Per-question direct P@5 (all eight answerable test questions, all five methods) is in
`local-benchmarks/answer-focus-calibration/review-v2/test-report.json`; three questions move in opposite directions
across methods (`test-leper-returned` recovers under the learned combination where plain full-pool BGE loses it
entirely; `test-own-faults` drops under every wider-pool method including the learned one; `test-es-tomorrow` is
missed by today's Compass-top-10 constraint entirely and found by every wider method), which is why the aggregate
numbers alone understate how much the five methods actually disagree question to question.

## Not yet done

The protocol's whole-list probability sample (independent rank-band draws per method, for precision/recall/Brier/
log-loss population estimates with proper uncertainty) has not been run. The top-five comparison above is a
purposive sample by construction (it pools only each method's own top five) and should not be read as a whole-list
precision estimate. Running it is the next step before any integration decision, per the protocol's own gate.

## Reproduce

```powershell
.venv/Scripts/python.exe -I tool/answer_focus_calibration_infer.py train|calibration|test
.venv/Scripts/python.exe -I tool/answer_focus_calibration_run.py fit
.venv/Scripts/python.exe -I tool/answer_focus_calibration_run.py sample      # then grade review-decisions.json
.venv/Scripts/python.exe -I tool/answer_focus_calibration_run.py compile
.venv/Scripts/python.exe -I tool/answer_focus_calibration_run.py calibrate
.venv/Scripts/python.exe -I tool/answer_focus_calibration_run.py test-topfive   # opens test-split labels for the first time
.venv/Scripts/python.exe -I tool/answer_focus_calibration_run.py test-compile
.venv/Scripts/python.exe -I tool/answer_focus_calibration_run.py test-report
.venv/Scripts/python.exe -I tool/answer_focus_calibration_run.py test-whole-list   # built, not yet run or graded
```

Private run folder: `local-benchmarks/answer-focus-calibration/review-v2/` (hash-bound provenance chain at every
step via `source_sha256`; a stale or mismatched artifact refuses to proceed rather than silently reusing it).
