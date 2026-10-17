# Mathematical retrieval experiment — protocol, 2026-10-16

Scope: offline experiments only. Do not change Flutter, Rust, installed packs,
release configuration, or the production application. New research code lives in
`tool/mathematical_retrieval_experiment.py`; private results and review passages
live under `local-benchmarks/mathematical-retrieval-v1/`.

This protocol is recorded before examining experiment results.

## Questions and baselines

1. Can a regularized pairwise ranker learn useful relevance from dense embeddings,
   unweighted genomes, and sparse token vectors without hand-assigned gene-family
   importance, volume offsets, entity rules, or named intent categories?
2. Does local graph diffusion improve relevance beyond direct vector matching?
3. Can determinant-based selection reduce repetition while retaining relevance?

Baselines reproduce the current local engine configuration: Compass and Lantern
meaning search, and genome/topic similar verses, with volume balance 0.75.
Unbalanced baselines are reported as ablations. Similar verses is a component
experiment, not a measurement of adaptive multi-step Trails.

## Available evidence and limitations

- Human judgments: the existing 60-source topic review. Its pooled candidates
  were selected by older genome/topic methods. It is a small, previously used,
  single-reviewer dataset restricted to topic-covered sources.
- Search: 24 authored intents with eight phrasings each. Anchors are incomplete,
  assistant-authored proxy targets, not exhaustive human relevance judgments.
- No completed meaning-search or multi-step trail judgments were found.
- Existing genome/model training predates this experiment. We cannot certify
  that these evaluation examples were absent from that historical training.

## Evaluation rules

- Five outer folds for human data; hold source chapters together. Three inner
  folds select regularization, separately inside each outer training set.
- Learned models: pairwise logistic ranking using three scalar similarities;
  additionally test a model using all 568 genome elementwise products. A
  topic-assisted model is a comparator, clearly marked as using a curated index.
- Pair labels come only from unequal human grades (0, 1, 2). Equal total training
  weight per source; no IDs, books, volumes, gene-family names, or source labels
  enter the learned feature vectors.
- Human primary metric: nDCG@8 in the fully judged pool. Also report related-or-
  better and strongly-related precision, diversity, and source-cluster bootstrap
  intervals. This is reranking evidence, not full-corpus retrieval accuracy.
- Full-corpus output: report judgment coverage and relevance bounds; do not
  silently treat unjudged discoveries as incorrect or correct. Create a blinded
  review sheet for missing judgments.
- Search proxy parameters are selected using other intents only. All paraphrases
  and translations of an intent stay together. Report anchor hit@5/10, MRR@10,
  candidate anchor coverage, and phrasing stability. Do not train a relevance
  classifier treating unlisted passages as human-labeled negatives.
- Graph diffusion and determinant diversity include a no-change setting. Report
  the individual variants as well as cross-validated selection; no retuning after
  inspecting outer-fold results.
- Bootstrap resamples source chapters for human data and whole intents for
  search. Intervals are exploratory and not adjusted for multiple comparisons.
- Verify baseline rankings against the existing native library. Record versions,
  source hashes, split assignments, parameters, timing, and numerical checks.

## Decision

No app integration based on proxy improvements alone. A candidate is promising
if its held-out human nDCG improvement has a paired interval above zero without
loss of related-or-better precision. Full-corpus discoveries still require fresh
judgments. No 95–99% accuracy certification from this experiment.

Probabilistic intent adaptation is deferred until actual sequential relevance
feedback exists. Scripted Likes/Skips cannot validate a model of reader intent.

## Diagnostic amendment after the first human run

Add dense-only, raw-genome-only, sparse-only, and equal-similarity baselines to the
same judged pool. These determine whether the learned fusion improves on its
individual inputs; they do not change folds, training, selection, or the original
production-baseline comparison. Add paired comparisons of graph/diversity against
learned fusion itself. The first run had no reciprocal duplicate judged pairs.
