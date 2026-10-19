# Calibration implementation review

Reviewed 2026-10-18. Offline research only. No app changes or commits.

The original 120-row packet was ungraded. Review found implementation differences
from the frozen [protocol](ANSWER_FOCUS_CALIBRATION_PROTOCOL.md), so grading that
packet should not proceed. Its files remain intact for audit. The corrected run is
in `local-benchmarks/answer-focus-calibration/review-v2/`.

## Corrections before labeling

- **Training objective:** the original implementation averaged question-weighted
  loss. The protocol specifies a sum, with each question totaling weight one,
  plus L2 penalty 1 on the slopes. Averaging made regularization effectively 72
  times stronger in the final 72-question fit. The corrected objective uses the
  weighted sum, stable logistic loss, analytic gradients, and convergence checks.
- **Sampling order:** the original sampler never loaded the learned model; it
  sampled Compass ranks. The replacement samples learned ranks 1–10, 11–50 and
  51–200, five per band per question. Score lookup follows candidate identity
  after sorting. Seeds and inclusion probabilities are retained.
- **Review integrity:** a shuffled reviewer view contains only item ID, question,
  reference and passage context. Separate bookkeeping retains ranks and scores.
  Hashes bind the model, source data, sheet, reviewer view and judgments.
  Compilation rejects missing, duplicate, extra, invalid and stale decisions.
  Existing outputs cannot silently be replaced.
- **Calibration weights:** inverse-inclusion weights now sum to one per question.
  The original weights summed to 200/15 for each full question. This common factor
  would not change an unregularized Platt fit or F1 on these equally sized pools,
  but contradicted the documented normalization.
- **Null diagnostic:** the intercept-only comparison now estimates prevalence in
  each training fold using question weights, then evaluates the held-out fold.
  The previous null used the full dataset's unweighted prevalence.

## Verification and current evidence

Both `test/answer_focus_calibration_fit_check.py` and
`test/answer_focus_calibration_sample_check.py` pass. Regression checks include an
independently solved scalar optimum that distinguishes summed from averaged loss,
weight-preserving row duplication, reversed retrieval/reranker orders, grouped
fold separation, stale hashes and invalid reviews. The actual replacement packet
was checked for 120 unique items, five items per learned-rank band, correct score
joins, inclusion weights, hidden ranking fields and intact provenance. Compiling
the ungraded packet correctly fails without creating grades.

All 72 training, eight calibration and ten final-test inference files are complete.
Their recorded input hashes were verified before fitting. No new inference was
needed. Final-test inference completion is not final-test evaluation.

The corrected model's mean grouped validation log loss is **0.6284**, compared
with **0.6558** for the fold-fitted intercept-only baseline. Standardized score
coefficients are Compass **0.1817**, BGE **0.3893**, intercept **−0.6595**.
These are diagnostics on selected historical labels, not whole-pool precision,
95–99% accuracy, calibrated confidence, or a deployment recommendation.

## Independent review handoff

Give the reviewer only these two files from `review-v2/`:

1. `blind-view.json`: all 120 passages in shuffled order, with adjacent context.
2. `review-decisions.json`: matching empty decisions and provenance hashes.

Grade the focal verse against the question: **2** directly answers/supports it;
**1** related or dependent on context; **0** does not answer. A response that
challenges the question's premise can be direct. Do not transfer an adjacent
verse's answer to the focal verse. Write a reason for every judgment, including
absent-answer controls, and fill in reviewer identity and review type. Do not
expose the bookkeeping sheet, learned rankings, or model outputs to the reviewer.

The present assistant participated in the experiment design and implementation
review. It has not graded this packet and cannot supply the independent review
requested in the handoff. The protocol permits exploratory assistant labels but
reserves stronger claims and integration for broader independent evaluation;
these two evidence levels must remain distinct.

After completed review, run `answer_focus_calibration_run.py compile`, then
`calibrate`. Both commands operate on `review-v2/` and fail closed on missing or
stale inputs. The calibration artifact freezes coefficients, scaling, cutoff,
label hashes and calibration selection counts. No cutoff has yet been fitted.
Final-test review and reporting remain outstanding; the current orchestration
script does not implement that evaluator. Keep final-test judgments unavailable
until the calibration artifact is frozen. Nothing in this review authorizes
shipping or implies that the learned method has passed evaluation.
