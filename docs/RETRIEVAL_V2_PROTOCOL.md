# Retrieval v2: expanded evidence and offline experiments

Recorded before new algorithm rankings or judgments, 2026-10-16.

The user delegated completion of anchors and investigation of the remaining
intelligence bottlenecks. This work changes research tools and evaluation data,
not production behavior. Assistant judgments are explicitly synthetic judgments,
never relabeled as independent reader feedback or human accuracy.

## Fixed scope

- Review the 24 existing canonical search intents and 12 newly authored challenge
  intents. Freeze challenge text before encoding or inspecting results.
- Pool the first five passages of every fixed method, plus original anchors.
  Hide method names, scores, and ranks during passage review. Read actual corpus
  text. Grade every pooled item: 2 directly answers/supports the expressed need;
  1 meaningfully related but incomplete/context-dependent; 0 does not address it.
  Record a brief reason and provenance. Do not mark an unreviewed item 0.
- Expanded anchors contain reviewed grades 1 and 2 separately. The finite pool
  can be completed; exhaustive relevance across all 41,995 verses is not claimed.
- Canonical questions receive query-specific judgments. The old eight wordings
  are not assumed equivalent: single words and changed needs are audited.
- Newly authored challenges are unseen by previous retrieval experiments, but
  still assistant-authored and judged. No parameter tuning on these challenges.

## Fixed experiments

Compare production Compass/Lantern, volume offsets disabled, full-corpus dense,
sparse and raw genome, exact full-corpus ColBERT, independent ColBERT candidate
expansion, graph neighbor expansion, equal raw-signal fusion, dense centering,
partial shrinkage whitening, passage-density correction, and token transport.

Exact ColBERT is a candidate-discovery reference, not a mobile deployment design.
Graph expansion uses 16 neighbors per view from eight initial seeds, up to 256
new candidates, and original-query scores. A matched extra-candidate control
uses deeper first-stage retrieval. Freeze score calibration on initial candidates
for expansion comparisons. No relevance labels enter candidate generation.

Whitening uses corpus covariance, shrinkage 0.1 times mean eigenvalue and exponent
beta=0.5. Density correction uses the mean of ten nearest passage vectors among
8,192 fixed reference passages, excluding self. This is passage local scaling,
not original two-domain CSLS. Keep these fixed rather than choosing on results.

Transport reranks the same top 20 exact-ColBERT passages. Compare balanced and
unbalanced entropic transport (epsilon=0.05; unbalanced mass penalty=0.5), with
convergence checks and equal initialization. Preserve a MaxSim comparator on the
same candidates. A more complex scorer is not presumed better.

## Reporting and safeguards

- Pooled P@5 (related and direct), pooled nDCG@5, judgment coverage and per-query
  failures. All evaluated top-five items must be judged for point estimates.
- Compare legacy positive-only anchors separately before and after expansion.
  A higher hit rate caused by more labels is benchmark coverage, not an algorithm gain.
- Paired intent-bootstrap intervals are exploratory and not multiplicity-corrected.
  Report the complete method set; do not cherry-pick a winning query subset.
- Freeze inputs and hashes, deterministic ties, baseline cache/native parity,
  exact token-scorer parity, transport convergence and marginal residuals.
- Timing is desktop experiment timing. Mobile speed, actual reader satisfaction,
  confidence calibration, and sequential trail intent remain unmeasured unless
  corresponding evidence is actually collected.
- No training gate/query adapter on the same synthetic review used to report its
  quality. No fabricated clicks, skips, likes, reader labels or accuracy claims.
