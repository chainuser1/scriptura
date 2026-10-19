# Answer Focus: wider-pool investigation

2026-10-18. Exploratory offline work under the
[recorded protocol](ANSWER_FOCUS_WIDE_POOL_PROTOCOL.md). No production changes.

## Completed: mean-cutoff audit of saved 30-candidate scores

This calculation reuses the original stage-2 fp32 verse-only reranker scores.
It does not represent a new int8 inference run or independent evaluation.

On the 72 previously evaluated answerable questions:

| Measurement | Count |
|---|---:|
| Question-passage candidates | 2,160 |
| Retained strictly above each question's mean score | 1,044 |
| Already-judged direct answers before filtering | 356 |
| Already-judged direct answers retained | 284 |
| Already-judged direct answers discarded | 72 |
| Retained candidates with a prior judgment | 736 |
| Retained candidates already judged nonanswers | 157 |

The mean cutoff removed 20.2% of known direct answers available in these pools.
It also retained 5, 6, 7 and 14 passages respectively across the four absent-answer
probes. Thus the cutoff neither preserves all known answers nor establishes
absence of an answer. It should not be adopted as a relevance guarantee.

The 308 retained but unjudged candidates remain unknown. The reviewed subset was
selected by earlier retrieval experiments, not random sampling. Consequently these
counts must not be presented as whole-list precision, exhaustive recall, or reader
accuracy. Existing grades mix assistant reviewers and retain their limitations.

Detailed per-question counts, the historical judgment snapshot (including unknowns)
and input hashes are preserved in
`local-benchmarks/answer-focus-wide-pool/existing-30-audit-frozen.json`. This audit
preceded the pilot reviews. Rerunning the general audit after adding judgments can
change its conditional counts; that is additional labeling, not a retrieval gain.

## Wider candidate experiment

### Completed: known-positive coverage on the older 36 questions

The cached query representations and exact ColBERT scores reproduce all 36
previous Compass top-20 lists. Holding the first-stage scoring unchanged:

| Candidate depth | Known direct answers included, out of 384 |
|---|---:|
| 10 | 133 (34.6%) |
| 15 | 159 (41.4%) |
| 20 | 180 (46.9%) |
| 30 | 197 (51.3%) |
| 60 | 248 (64.6%) |
| 120 | 279 (72.7%) |
| 200 | 293 (76.3%) |
| Full retrieved union | 316 (82.3%) |

These are micro-averaged coverage counts of previously judged question-passage
pairs, not corpus-wide recall or an accuracy estimate. The old judgments are
selection-biased and incomplete. Wider pools provide access to more known answers
but do not guarantee that a reranker will place them correctly. Sixty-eight known
direct answers still fall outside the current candidate union.

Reproduce with `tool/answer_focus_candidate_coverage.py`. Per-question counts,
macro averages and source hashes are in
`local-benchmarks/answer-focus-wide-pool/candidate-coverage.json`.

### Full-pool reranker pilot

A ten-question pilot is complete: four development questions,
three previously evaluated English questions, one Spanish question and two
absent-answer questions, selected by the protocol's deterministic hash order.
Candidate depths are 10, 15, 20, 30, 60, 120, 200 and the full retrieved union.

Scored **5,365 query-passage pairs**, one at a time using the installed int8 CPU
model. All ten reconstructed top-200 lists exactly matched the native semantic
engine, and all ten top-30 lists matched the old stage-2 candidate lists. The native
comparison excludes reference routing and entity promotion. It does not validate
every route through the search screen.

Thirty-four new top-five passages were explicitly reviewed with method, score and
rank hidden, with the focal verse and its neighbors visible. Every top-five result
in every compared configuration now has a judgment. Earlier judgments were kept,
so the combined labels mix assistant reviewers. The review is not independent,
and the questions have been used before. Results are descriptive pilot evidence.

For the eight answerable questions, Compass alone has 42.5% direct P@5 and 85.0%
related-or-better P@5. It is unchanged by depth because its first five stay fixed.

| Candidate depth | BGE direct P@5 | BGE related P@5 | Fixed blend direct P@5 | Fixed blend related P@5 |
|---|---:|---:|---:|---:|
| 10 | 52.5% | 95.0% | 50.0% | 90.0% |
| 15 | 52.5% | 87.5% | 50.0% | 87.5% |
| 20 | 52.5% | 85.0% | 52.5% | 87.5% |
| 30 | 47.5% | 80.0% | 47.5% | 87.5% |
| 60 | 47.5% | 80.0% | 50.0% | 87.5% |
| 120 | 52.5% | 82.5% | 52.5% | 92.5% |
| 200 | 52.5% | 80.0% | 52.5% | 92.5% |
| Full union | 50.0% | 72.5% | 55.0% | 85.0% |

The blend is the protocol's fixed diagnostic control, equal weights on
within-pool standardized Compass and BGE scores. It is not a fitted or calibrated
model and is not proposed for deployment.

Widening BGE alone from 10 to the full pool changes direct answers from 21 to 20
out of 40 top-five slots, and related-or-better answers from 38 to 29. The full-pool
blend has 22 direct and 34 related-or-better results: one more direct answer than
BGE-at-10, but four fewer related results. Eight selected questions and mixed
assistant judgments do not establish a reliable improvement. Do not choose a
production depth or weight from the apparent best cell in this table.

### Concrete recoveries and failures

- For envy of others' success, full-pool BGE surfaced **Alma 29:16**, originally
  Compass rank **384**, a direct example of rejoicing in other people's success.
  It also promoted Ezekiel 16:42, a different situation involving divine jealousy,
  which does not answer the question.
- For correcting someone lovingly, full-pool BGE surfaced **Proverbs 27:5** from
  Compass rank **398**, contrasting open rebuke with concealed love.
- For repairing theft, it recovered Luke 19:8 from rank 71 and Judges 17:2 from
  rank 258, but also promoted unrelated passages such as Job 4:12 and Jacob 7:14.
- For caring for widows and orphans in Spanish, full-pool BGE promoted Galatians
  4:30, which mentions what scripture says but does not address that care.

These examples support broader candidate access as a research direction while
showing that the present reranker still confuses lexical overlap, roles and scope.
A broader pool can expose both hidden answers and high-scoring nonanswers.

### Filtering and cost

For the full-pool BGE results, above-mean filtering retained **1,588 passages**
across eight answerable questions. Only **155** of those had judgments; 31 of those
reviewed retained passages were nonanswers. It discarded three of the 58 known
direct answers in the full pools. These conditional counts cannot establish
whole-list precision because 1,433 retained passages were unjudged.

For the two absent-answer probes, full-pool above-mean filtering still retained
**88 passages** for water's boiling temperature and **45** for the year the
American Civil War ended. Relative score filtering does not detect absence of
an answer, and widening the pool does not cure that limitation.

Full-pool CPU scoring took a median **84.3 seconds** across ten questions (range
66.6-103.5 seconds; pools of 464-579 passages). These are observed batch-call
times, not complete application latency or controlled idle-device benchmarks;
other read-only audits ran during parts of the experiment. They do not establish
phone performance. They exceed the current screen's three-second focus timeout.

## Decision and remaining work

Do **not** deploy a larger unfiltered pool, equal-weight score blend or mean cutoff
based on this pilot. Early truncation demonstrably excludes known useful passages,
but simply giving this reranker everything did not improve top-five quality here.

The next experimental stage should separate broader candidate access from the
decision to promote or retain a passage. Compare a fitted score combination and
calibrated relevance cutoff against BGE-at-10, using sufficient training judgments,
grouped validation and a new untouched test set. Include role/scope errors and
absent-answer queries. No calibrated cutoff or learned combination was trained in
this pilot; it would be premature to claim one solves the observed failures.

Any eventual integration also needs an explicit latency strategy, cancellation and
device measurements. Candidate-processing budgets and displayed-result counts
must remain separate. No production code, model pack or reader preference changed.

## Verification and reproduction

All 97 current engine, ColBERT and int8 Answer Focus pack files passed manifest
size/hash verification; details are in `pack-verification.json` in the run folder.
Filter checks cover competitor-dependent means, equal-score empty results, and
preserving unknown judgments rather than treating them as negatives.

```powershell
.venv/Scripts/python.exe -I tool/answer_focus_candidate_coverage.py
.venv/Scripts/python.exe -I tool/answer_focus_wide_pool.py run
.venv/Scripts/python.exe -I tool/answer_focus_wide_review.py
# Supply explicit decisions in early-decisions.json before compiling:
.venv/Scripts/python.exe -I tool/answer_focus_wide_review.py --compile
.venv/Scripts/python.exe -I tool/answer_focus_wide_pool.py report
.venv/Scripts/python.exe -I tool/answer_focus_wide_summary.py
```

The private run folder contains the selected questions, frozen input identities,
per-question checkpointed scores and timings, original blind review, explicit
reasons, compiled grades, detailed report and summary. No unjudged top-five result
is silently assigned a grade. Full result lists remain only partially judged.
