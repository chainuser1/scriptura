# Search intelligence: expanded anchors and completed offline tests

2026-10-16. Application behavior and installed packs are unchanged.

## Outcome

Completed the finite benchmark's anchor and passage-review work without requiring
the user to review passages. Tested 16 fixed retrieval configurations and four
learned configurations. None established an improvement that warrants integration.
The 95–99% intent-accuracy goal has **not** been achieved or certified.

The central finding is a gap between topical relation and answering the question.
Compass scored 96.1% related-or-better P@5 but only 48.3% direct P@5 on this
assistant-reviewed set. Those are different measurements; the former must not be
marketed as 96.1% accurate understanding. These are provisional model judgments,
not independent reader judgments.

## Completed evidence

- 36 query-specific answer keys: 24 existing canonical questions and 12 challenge
  questions written before the new retrieval runs.
- 975 passages pooled from every fixed method's top five plus original anchors.
- 51 additional candidates independently nominated from scripture knowledge and
  checked against the actual corpus text. These were nominated after pool review,
  before aggregate metrics, and did not alter retrieval results.
- 127 additional passages from the learned follow-up, also fully reviewed.
- **1,153 judgments: 384 direct, 432 related/context-dependent, 337 nonanswers.**
  Every judgment has a reason. Every evaluated top-five result has a judgment.
- The portable key is `tool/search_anchors_v2.json`. It contains references,
  grades, and reasons, not scripture text. It is evaluation data, never a runtime
  list of preferred verses. Unlisted verses remain unjudged.
- `tool/query_robustness_audit.json` flags 21 changes of intent within the old
  phrasing set and excludes single-word/topic probes from strict-paraphrase claims.
  Translations remain assistant-authored and not independently language-validated.

Review order hid method names, scores, and ranks. The same assistant designed the
experiments and reviewed the text: this is method-blinded review, not independent
assessment. The 36 questions and finite pools do not exhaust the corpus or the
possible needs of readers. Some judgments require surrounding narrative context.

Completing labels is not an engine improvement: on the same 24 canonical questions,
Compass's top-five positive-anchor hit rate changes from 54.2% with the old key to
100% with the expanded related-or-better key. The ranked passages did not change.
This is exactly why positive-anchor hit rate alone cannot establish intelligence.

## Fixed mathematical comparisons

All 36 questions, five results per question. P@5 is the average fraction of those
five results receiving the relevant grade. Pooled nDCG uses grades 0/1/2 with
gains 0/1/3 and measures ordering relative to the reviewed pool.

| Method | Related P@5 | Direct P@5 | Pooled nDCG@5 |
|---|---:|---:|---:|
| Current Compass | 96.1% | 48.3% | 0.642 |
| Current Lantern | 93.9% | 48.9% | 0.637 |
| Compass without volume offsets | 97.2% | 50.0% | 0.651 |
| Dense alone | 77.2% | 26.7% | 0.432 |
| Sparse alone | 62.2% | 24.4% | 0.377 |
| Raw genome alone | 81.1% | 36.1% | 0.515 |
| Exact full-corpus ColBERT | 76.7% | 27.8% | 0.447 |
| Equal raw-signal fusion with ColBERT candidates | 91.1% | 41.1% | 0.587 |
| Dense centering | 67.8% | 21.1% | 0.364 |
| Partial shrinkage whitening | 67.2% | 24.4% | 0.386 |
| Passage local-density correction | 66.1% | 18.9% | 0.340 |
| Balanced token transport | 70.0% | 18.3% | 0.355 |
| Unbalanced token transport | 70.6% | 18.3% | 0.358 |

Adding independent ColBERT candidates, graph neighbors, or matched deeper
first-stage candidates to Compass with frozen score calibration did not change
its top five on these questions. The mean per-query coverage of **reviewed direct
positives** rose from 79.6% to 80.8% with ColBERT expansion. This is conditional
coverage of known positives, not exhaustive corpus recall. The existing scoring
still kept the new candidates below the top five.

The no-volume-offset nDCG difference is +0.009, with an exploratory paired 95%
interval of [-0.009, +0.028]. It is inconclusive. No thresholds or parameters were
tuned on the challenge results. Negative outcomes concern these implementations
and fixed settings, not every possible use of the cited research methods.

Earlier dense-only success was on human-reviewed **verse-to-verse** ranking in a
historical candidate pool. This experiment evaluates **natural-language search**.
They are different tasks and neither result should be substituted for the other.

## Learning and generalization

The follow-up trained pairwise logistic rankers on only the 24 development
intents. Inputs were four numerical signals: dense, sparse, exact ColBERT, and
raw genome. Models received no book identity, verse ID, named intent, family
weight, volume offset, or behavioral event. Parameters were fixed in advance of
fitting; the previously inspected challenge baselines make this exploratory.

The full-corpus linear model learned a negative dense coefficient and produced
severe off-topic extrapolation. A nonlinear interaction model also failed to
beat Compass. A diagnostic restricted the same fitted models to the original
candidate pool, with no retraining. Both failures and restrictions are retained.

| Method, 12 held-out challenge intents | Related P@5 | Direct P@5 | Pooled nDCG@5 |
|---|---:|---:|---:|
| Compass | 96.7% | 46.7% | 0.636 |
| Learned linear, full corpus | 31.7% | 0.0% | 0.119 |
| Learned linear, original candidate pool | 41.7% | 0.0% | 0.156 |
| Learned interactions, full corpus | 70.0% | 25.0% | 0.419 |
| Learned interactions, original candidate pool | 78.3% | 28.3% | 0.454 |

Restricting candidate scope reduces some extrapolation but does not rescue these
models. Synthetic reviewed pools are useful development evidence; they are not
sufficient grounds for deploying a learned gate or trusting an unconstrained
score outside its training distribution.

## Remaining intelligence blockers, with concrete evidence

| Blocker | Evidence and status |
|---|---|
| Incomplete evaluation anchors | Resolved for the finite reviewed benchmark; all 1,153 labels are explicit. Corpus-wide completeness is not claimed. |
| False paraphrase equivalence | Audited in a machine-readable file; canonical search judgments are separate from topic probes. |
| Candidate exclusion | Full-corpus token reference and graph/deeper expansion tested. Some additional known positives found, no top-five gain with fixed Compass scoring. |
| Matching a topic instead of answering | Only 30/36 Compass questions have any direct result in the top five; average direct P@5 is 48.3%. Still unresolved. |
| Roles, senses, and multiple constraints | Concrete failures include receiving versus granting forgiveness, grace greetings versus definitions, physical versus spiritual rebirth, and rest versus diligence. New answer keys distinguish these. |
| Missing context | Some verses are questions, continuations, or historically specific instructions. Single-verse relevance may require a passage window; window-level quality is not yet measured. |
| Learned-score extrapolation | Detected and tested with candidate restrictions; rejected models remain research-only. |
| Unsupported answer confidence | Native semantic search returns five passages for all eight probes whose factual answer is absent from the corpus. Its z-score fusion is a ranking score, not a calibrated correctness probability. This probe does not test app-level routing. |
| Trails assume a skip is negative | `engine/src/trails.rs` uses skip reward -0.2 in both family learning and target-vector adjustment. Why a reader skipped is not observed. No real sequential evidence validates that interpretation. |
| Trails steer exploration | Fixed novelty, mood coefficients, family exclusions, and exploration cadence remain in production. They are design choices, not inference established by these tests. |
| Real reader and language generalization | Still unmeasured by this assistant review. No reader actions or independent labels were fabricated. |
| Device feasibility | Exact corpus scans ran on this desktop; no new method has demonstrated a relevance gain warranting phone integration or profiling. |

The next research requirement is a representation or scoring objective that
distinguishes answer support, roles, scope, and passage context. More scalar
fusion, density corrections, or uncalibrated confidence formulas have not solved
that requirement in these tests. The expanded key now makes those errors
observable and provides development examples. A future model needs a new test
set: these 36 questions have now been inspected and must not be presented as an
untouched final holdout.

## Verification

- Ten engine-pack files rehashed against the manifest.
- All 72 native Compass/Lantern top-ten rankings match the offline baselines.
- Exact full-corpus ColBERT checked against the existing scorer on 61 sampled
  passages for all 36 questions; maximum absolute difference 1.20e-7.
- 1,440 transport computations converged; maximum balanced marginal residual
  1.33e-8. Numerical convergence did not translate into better relevance.
- Review validators reject missing grades, duplicate judgments, stale pool
  hashes, and train/test intent overlap. Portable keys have 36 questions and
  1,153 unique within-question references.
- The exact token scan took about 24.8 seconds for all 36 queries in this batched
  desktop experiment. This is not cold-start latency or a mobile estimate.

## Reproduce

All tools are offline research tools. The application does not load their keys
or model parameters. Full text, cached vectors, detailed rankings, explicit
review decisions, and parameter files stay under `local-benchmarks/retrieval-v2/`.

Generate a fresh reproduction without mixing caches from changed code:

```powershell
.venv/Scripts/python.exe -I tool/retrieval_v2.py --out local-benchmarks/retrieval-v2-reproduction
```

Revalidate and score the existing frozen review, then append the learned review:

```powershell
.venv/Scripts/python.exe -I tool/retrieval_v2_review.py --compile
.venv/Scripts/python.exe -I tool/retrieval_v2.py --score
.venv/Scripts/python.exe -I tool/retrieval_v2_learn_score.py
.venv/Scripts/python.exe -I tool/retrieval_v2_verify.py
.venv/Scripts/python.exe -I tool/retrieval_v2_boundary.py
```

The first scoring command exports the initial answer key; the learned scoring
command extends it to all 1,153 judgments. To repeat fitting on the frozen
development labels, run `tool/retrieval_v2_learn.py` before its scorer. Protocols
are `docs/RETRIEVAL_V2_PROTOCOL.md` and `docs/RETRIEVAL_V2_LEARNING_PROTOCOL.md`.
