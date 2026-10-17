# Mathematical retrieval experiment: first results

2026-10-16. Research only; no application behavior or installed packs changed by
this experiment. Protocol: [MATHEMATICAL_RETRIEVAL_EXPERIMENT.md](MATHEMATICAL_RETRIEVAL_EXPERIMENT.md).

## Decision

Do not integrate a new algorithm yet. The strongest evidence is that adding
textual similarity to verse-to-verse ranking deserves further evaluation.
Learned fusion is promising, but it has not demonstrated a reliable advantage
over a simple dense-embedding baseline on the available human judgments.
Graph propagation and determinant-based diversity do not yet justify their
additional complexity. None of these tests establish 95–99% accuracy.

## Human-judged verse relevance

Used 827 existing judgments for 60 source verses. Five outer folds held source
chapters out of training; three inner folds selected regularization. All methods
ranked the same fully judged historical candidate pool. nDCG@8 measures ordering
quality; it is not percent accuracy.

| Method | nDCG@8 | Related-or-better among first eight |
|---|---:|---:|
| Current genome/topic ranking, volume balance on | 0.7944 | 88.96% |
| Dense embedding alone | 0.8539 | 89.79% |
| Learned dense + raw genome + sparse fusion | 0.8579 | 89.38% |
| Learned fusion + selected graph propagation | 0.8695 | 89.17% |
| Learned individual genome-dimension contributions | 0.7969 | 88.75% |

Learned fusion improves nDCG over the current baseline by 0.0635; the exploratory
paired 95% interval is [0.0232, 0.1039]. However, its gain over dense alone is only
0.0039 [-0.0120, 0.0198]. Graph propagation adds 0.0117 [-0.0027, 0.0260] over learned
fusion: encouraging, but inconclusive. Selected diversity adds -0.0010
[-0.0030, 0.0002]. The shuffled-label control performs substantially worse.

The main learned model uses three numerical similarities. It receives no book,
volume, named intent, or gene-family feature, and uses unweighted genomes. A
separate topic-assisted comparator scored 0.8709, but uses a curated topic index
and does not establish improvement beyond the simpler learned model.

Only 23.8% of the learned model's full-corpus top-eight passages already have
judgments. The improved closed-pool ranking cannot certify the new discoveries.
The dataset was previously used, has one reviewer, and contains only sources
covered by the topic index. These are component results, not adaptive Trails
accuracy or evidence of understanding unseen natural-language questions.

## Meaning-search proxy

Used 192 questions: eight phrasings of each of 24 intents. All phrasings and
translations of one intent stay in the same fold. The expected anchors were
assistant-authored and are incomplete; missing an anchor does not prove a result
is irrelevant. No ranker was trained by labeling unlisted passages as negatives.

| Method | At least one expected anchor in first ten |
|---|---:|
| Current Compass | 46.35% |
| Current Lantern (no ColBERT) | 45.31% |
| Compass with volume offset disabled | 50.52% |
| Equal dense/sparse/ColBERT/raw-genome fusion | 41.15% |
| Graph setting selected on other intents | 38.02% |
| Diversity setting selected on other intents | 41.15% |

Removing the volume offset improves this proxy by 4.17 percentage points
[1.04, 6.77]. That is a reason to include the unbalanced method in fresh review,
not a sufficient basis to change production. Graph and diversity operate on the
raw equal-fusion experiment, not on Compass, so this is not a universal rejection
of either technique. First-stage candidate sets contain an anchor for 83.33% of
queries currently, versus 84.38% with raw-genome candidates. Ranking is one
limitation; candidate coverage is another.

## Verification and next evidence

- 22 sampled ranked lists match the existing native library exactly: six similar
  verse lists and eight questions under each of Compass and Lantern.
- All ten engine-pack file hashes match the pack manifest; raw and packaged
  genome rows share the same 41,995 verse IDs.
- Numerical checks cover deterministic ties, graph mass conservation, and greedy
  determinant selection against a direct determinant calculation.
- Main model selection was fixed before looking at outer-fold results. Additional
  single-signal controls were recorded as a diagnostic amendment. Confidence
  intervals are exploratory, not corrected for multiple comparisons.
- Real sequential intent adaptation remains untested: scripted Likes/Skips
  would not validate what a reader intended.

Private detailed results, split assignments, parameters, manifests, and a blinded
review sheet are in `local-benchmarks/mathematical-retrieval-v1/`. The sheet tests
new candidate judgments on existing prompts; it is not a new-intent holdout.

Run the experiment:

```powershell
.venv/Scripts/python.exe -I tool/mathematical_retrieval_experiment.py
```

Score exported review judgments (only fully judged prompts are compared):

```powershell
.venv/Scripts/python.exe -I tool/mathematical_retrieval_experiment.py --score-review PATH_TO_EXPORTED_JSON
```

Next evidence required: independent search questions and source verses with
blinded judgments across current, dense-only, learned-fusion, and unbalanced
baselines; then actual sequential trail judgments. Evaluation judgments measure
reader relevance without becoming hardcoded verse-selection rules.
