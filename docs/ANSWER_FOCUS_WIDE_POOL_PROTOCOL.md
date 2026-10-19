# Answer Focus: wider candidate pools and result filtering

2026-10-18. Offline exploratory follow-up. Production code and packs are unchanged.

## Question

Does allowing BGE to examine more of Compass's candidate union recover useful
passages excluded by the screen's 20-result request and its 10/15-candidate focus
prefix? Can variable-length results improve precision without discarding direct
answers? See [the BGE research plan](BGE_RERANKER_DISTILLATION_RESEARCH.md).

## Current implementation

Dense, sparse and genome each nominate up to 200 verses. Compass ranks their
deduplicated union with its existing fusion, including ColBERT. The screen requests
20 results; Answer Focus only sorts its configured prefix (10, 15 or 30, effectively
at most 20). Unscored tail results remain. GPU selection starts at 10 and adaptation
never increases it. Focus has a three-second screen timeout. No final relevance
filter or Compass-plus-focus score is implemented.

## First bounded experiment

1. Audit the saved stage-2 results at 30 candidates without new inference. Measure
   mean-cutoff retention, labeled-answer losses and behavior on absent-answer
   questions. Unjudged passages remain unknown, never negative.
2. Select a reproducible pilot before inference: four development questions,
   three previously evaluated fresh English questions, one Spanish question and
   two absent-answer questions. Within each group choose by SHA-256 of
   `20261018:<question-id>`. This selection does not inspect method performance.
   These are reused questions, not a new holdout. Ten questions cannot establish
   generalization or a production decision.
3. Reconstruct the full existing candidate union in the offline reference. Require
   its first 200 ranked IDs to match the native semantic engine before reranking.
   Compare existing stage-2 top 30 as a further drift check. The native comparison
   omits reference routing and entity promotion, as did the stage-2 harness; it is
   not a test of every UI search route. No production API limit is changed.
4. Score the full pilot union using the installed int8 BGE pack on CPU, one pair at
   a time, matching the production CPU batching policy. Record exact model/input
   hashes, passage text hashes, backend and timing. Checkpoint after each small
   batch, including partial scores, so progress can be inspected and resumed.
5. Compare nested depths 10, 15, 20, 30, 60, 120, 200 and the full union. These are
   candidate budgets, not proposed final display limits. Reuse identical pair
   scores across depths so dynamic-quantization batch effects do not masquerade
   as candidate-depth effects.

## Ranking and filtering controls

- Compass ordering at each depth.
- BGE-only ordering at each depth.
- A fixed exploratory blend: `0.5*z(Compass) + 0.5*z(BGE)`, standardized within
  the depth's candidate set. No weight fitting or claim of optimality; this blend
  is intentionally a control for score combination. Candidate-dependent scaling
  must be reported. Do not add incompatible raw scores.
- Keep-all and strictly-above-mean filtering for BGE and the blend. No minimum
  output count is forced. Equal scores may produce an empty filtered set.
- Report when adding candidates changes retention of previously scored passages.
  Sorting itself does not affect the mean. Above-mean is not a confidence measure.

Calibrated cutoffs and fitted score combination are a subsequent stage requiring
adequate training labels, grouped validation and new held-out questions. They are
not trained from sparse pilot labels or claimed to be validated by this run.

## Judgments and reporting

Preserve existing grades and their provenance. Pool all methods' top-five results
across depths; blind-review novel passages with their context visible using the
existing 0/1/2 rubric. Do not inspect rankings before completing new reviews. The
same assistant can author the code and review results, so this is not independent
evaluation. Grade the focal verse, since the current UI displays a single verse.

For fully judged top fives report direct P@5, related P@5 and any-direct@5. Missing
top-five grades block complete quality metrics. For variable-length filtered sets,
report counts, judgment coverage and conditional statistics on reviewed passages
only. Do not present these conditional statistics as whole-list precision or
exhaustive recall. Report known direct answers discarded by a cutoff and known
direct answers outside each candidate depth. A defensible whole-list filter
comparison needs additional complete or probability-sampled review.

Absent-answer queries are reported separately. Reranker logits and their sigmoid
are not calibrated answer probabilities. Do not infer correctness from score sign.

Timing includes the offline scorer's actual work; prefix times reused from a full
run are diagnostics, not independent cold-start phone benchmarks. Wider scoring
will exceed today's UI timeout on many devices. Do not integrate by merely raising
`topK`; retrieval depth, processing budget, cancellation and display policy need
separate design and device validation.

## Reproduction and next decision

```powershell
.venv/Scripts/python.exe -I tool/answer_focus_wide_pool.py audit
.venv/Scripts/python.exe -I tool/answer_focus_wide_pool.py run
.venv/Scripts/python.exe -I tool/answer_focus_wide_pool.py review
.venv/Scripts/python.exe -I tool/answer_focus_wide_pool.py report
```

Private scores/text live in `local-benchmarks/answer-focus-wide-pool/`. A run resumes
only when its recorded identities match. Review generation must not overwrite
completed judgments. The outcome determines whether to extend to all questions
and build a new holdout. No app behavior changes are authorized by a pilot result
alone, and no 95-99% accuracy claim follows from it.
