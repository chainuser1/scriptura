# Learned Compass/BGE combination and relevance calibration

2026-10-18. Protocol recorded before this experiment's fresh inference or labels.
Offline only; no change to the application, reader preferences or installed packs.

## Scope and separation

The [wide-pool pilot](ANSWER_FOCUS_WIDE_POOL_RESULTS.md) found additional known
answers but also high-scoring nonanswers. This experiment learns a score combination
and tests a variable-length cutoff against Answer Focus at ten candidates.

Use a fixed **200-candidate Compass pool**, supported by the existing native API.
This bounds research cost; it is not a proposed display cap. Nothing here validates
a cutoff for the entire corpus or the larger candidate union.

- **Training:** the 72 historical answerable questions. Use existing 0/1/2 labels
  for candidates in their native top 200. Unjudged candidates remain unjudged.
  Reuse the verified pilot's native int8 pair scores where identical; score the
  remaining labeled candidates with the same installed model and CPU policy.
- **Calibration:** eight newly authored questions (six answerable, two absent).
- **Final test:** ten additional new questions (eight answerable, two absent).
  Keep their labels and method metrics unopened until model and cutoff are frozen.

The fresh questions are in `tool/answer_focus_calibration_questions.json`. Exact
question and ID overlaps are rejected. Direct paraphrases were checked manually
against the historical questions; broader topics and scripture passages can still
overlap. The questions and new labels are assistant-authored, not independent
reader evidence. One Spanish question per fresh split is diagnostic only.

## Learned combination

Inputs are the native Compass score and native BGE int8 raw logit. No verse or book
identity, doctrinal category, behavioral event, query text or preferred-verse key
is a model feature. Fit global feature standardization on training data only.

Fit a two-feature logistic model for `grade == 2` with nonnegative slopes and an
unrestricted intercept. This predeclared monotonic constraint prevents rewarding
a lower retrieval score solely through a negative coefficient, an extrapolation
failure observed in earlier scalar experiments. It is a modeling assumption,
not a theorem of relevance. Use L2 penalty 1 on the slopes, summed log loss with
each training question having total weight one, and no hyperparameter search.

Report five-fold validation grouped by question, refitting the scaler and model
inside each fold. This diagnostic is conditional on historically selected labels;
it cannot establish whole-pool calibration. No test labels select coefficients.

## Representative calibration review

After the ranking model is fitted, sample five candidates without replacement in
each of its rank bands 1-10, 11-50 and 51-200 for each calibration question. Save
the random seed, band and inclusion probability. All candidates have nonzero
probability of selection. These 120 passage reviews provide a probability sample
of the 1,600 calibration candidates, rather than another top-five-only sample.

Review with method, rank and score hidden, using the existing focal-verse rubric:
2 directly answers/supports the question; 1 related or dependent on context;
0 nonanswer. Challenging a premise can be direct. Adjacent verses are visible.
Absent-answer controls are still reviewed explicitly; never infer grades from a
low score. Save a reason and bind judgments to the review-sheet hash.

Fit a monotonic Platt sigmoid (nonnegative slope, free intercept) to the frozen
ranking logits using calibration labels with inverse inclusion-probability
weights, normalized so each question has total weight one. This estimates direct
relevance within this experimental candidate/query mixture, not scriptural truth
or universal confidence.

Choose a cutoff on that calibration sample by maximizing inverse-probability
weighted F1 for direct answers over thresholds 0.00, 0.01, ..., 1.00; ties choose
the higher threshold. F1 makes the precision/recall tradeoff explicit. It is a
research selection criterion, not proof of the owner's 95-99% ambition. No minimum
or maximum result count is imposed after the cutoff. Freeze coefficients, cutoff,
feature scaling, label hashes and selection counts before final-test review.

Fitting calibration and choosing a cutoff on this small shared set can overfit.
Only the untouched final-test outcomes measure transfer. Do not retune on them.

## Final test and controls

Compare:

1. Current Answer Focus: BGE sorts the first ten Compass candidates; the untouched
   Compass tail through position 20 remains as in the UI.
2. BGE ordering of all 200 candidates, without filtering.
3. Learned combination of all 200, without filtering.
4. Learned combination followed by the frozen calibrated cutoff, with variable
   result count and the possibility of no results.
5. BGE-above-mean filtering as a diagnostic control.

Review the union of each method's top five completely. For fixed-slot P@5, missing
results count as zero; also report precision among displayed results and answer
coverage so abstention cannot create a misleading perfect score.

For whole-list evaluation, independently sample five passages in each **final-test
learned-rank band** 1-10, 11-50, 51-200, plus top-five review items. Only the random
sample (with inverse-probability weights) estimates full-list precision, direct
answer retention, Brier score and log loss. Do not mix extra purposive top-five
reviews into those population estimates. Report sample sizes, effective sample
sizes and query-level uncertainty; the estimates may be very imprecise.

Report absent-answer result counts separately. Report false promotions and known
direct answers removed. All meaningful quality metrics include the denominators
and whether they are exact reviewed counts or sampling estimates. No sigmoid
value is interpreted as verified answer confidence without evidence.

## Engineering and decision

Use existing native semantic retrieval and CPU int8 focus, one pair at a time.
Save candidate IDs, both scores, input/model hashes, timings and checkpoint after
each batch. Preserve historical outputs. The native harness omits UI reference
routing and entity promotion; disclose that scope. Runtime and quantization are
held fixed. This is not a mobile latency benchmark.

Passage identities, not labels, may be known to the inference process; final-test
judgments must not enter training, calibration or threshold selection. Reject
incomplete review, stale hashes, duplicate judgments and split overlap.

An apparent gain on eight synthetic answerable questions is not a deployment pass.
Report whether the learned methods improve direct answers, introduce nonanswers,
or merely return fewer results. A failure is a valid result: preserve it, do not
silently loosen the cutoff or tune on the test. Device validation and a broader
independent evaluation are required before any app integration.

## Addendum (2026-10-19): non-Compass profile transfer

Every Answer Focus measurement to date — stage-2, the wide-pool pilot, and this
calibration protocol's own train/calibration/test splits — reranks candidates
from the **Compass** profile only. The app offers seven selectable profiles
(`lib/app/search_styles.dart`), all mixing the same four signals in different
ratios; Answer Focus applies uniformly regardless of which is active
(`search_screen.dart` calls focus after resolving results, independent of
`app.searchProfile`). Whether the measured gain transfers to the other six is
untested, and the two structurally furthest from Compass's weights
`[echo, spark, thread, root] = [0.1, 0.1, 0.2, 0.6]` are the ones most likely to
differ:

- **Lantern** `[0.25, 0.15, 0.0, 0.6]` — zero weight on the word-level (ColBERT)
  signal; this is also Compass's own fallback when the optional index is absent.
- **Gemini** `[0.0, 0.0, 0.15, 0.85]` — near-pure gene fusion, the closest
  configured profile to theme-matching without a semantic-meaning or exact-word
  component.

`tool/answer_focus_profile_transfer.py` (`run` then `report`) scores BGE-at-10
— the depth already shipped, no blend, no learned combination, no cutoff — on
Compass, Lantern and Gemini candidate pools for the same frozen 10-question
final-test split used above. This is **descriptive only**: it does not select or
validate a profile policy, and it does not gate the calibration decision above.
Because Lantern's and Gemini's top-5 slots were never part of any prior labeled
pool, most results there will be unjudged on the first run; `report` separates
`direct_rate_judged_only` (computed only over slots with an existing grade) from
the count of slots still needing a blind review, and explicitly refuses to call
the judged-only rate a full P@5. Unjudged slots must go through the same
blind-review process as every other stage before being cited as a result.

This check exists to catch a gain that is actually Compass-specific before the
feature's effect size is described as applying to the app as a whole. It is not
a substitute for a dedicated per-profile evaluation, which would need its own
frozen question set per profile and is out of scope here.
