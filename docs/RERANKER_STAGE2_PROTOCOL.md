# Reranker test (stage 2): frozen protocol

2026-10-17. Written and committed before any reranker output existed. Plan:
[BGE_RERANKER_DISTILLATION_RESEARCH.md](BGE_RERANKER_DISTILLATION_RESEARCH.md). Research only; the app is unchanged.

## Question

Does `BAAI/bge-reranker-v2-m3`, reordering the passages the app already finds, put more passages that **directly
answer** the question in the top five?

## Questions

- **Fresh:** `tool/reranker_fresh_set.json`, 40 questions written for this test before any run: roles, negation,
  conditions, several requirements, false premises, narrative context, less obvious needs, 4 Spanish questions, and 4
  factual questions whose answer is not in the scriptures (reported separately, not scored for relevance).
- **Development:** the 36 questions of the v2 evaluation (`tool/search_anchors_v2.json`). Already inspected; used only to
  choose between the two reranker inputs below.

## Methods (same candidates for all)

Candidates: the app's own engine (`scripture_engine.dll`, `search` request, Compass profile, volume balance 0.75, the
question's language), top 30.

- **A. Today:** the engine's own top five.
- **B. Reranker, verse:** the reranker scores (question, verse text) for the 30 candidates; top five by that score.
- **C. Reranker, context:** as B, but the passage is the previous verse, the verse and the next verse of the same chapter.
  The result shown is still the single verse.

Model: `BAAI/bge-reranker-v2-m3`, revision recorded at run time, full precision on the CPU, pairs truncated at 512 tokens.
Ties keep the engine's order. Text is in the question's language. Nothing is tuned on fresh questions.

## Judging

The top fives of A, B and C are pooled per question, shuffled with a fixed seed, and shown without method, score or rank.
Each verse is graded with its neighbouring verses visible:

- **2 direct:** the verse itself answers or directly supports what was asked.
- **1 related:** on topic, but incomplete or only meaningful with its context.
- **0 not an answer.**

A passage that challenges the question's premise can be direct. Every grade has a one-line reason. On development
questions, grades already in `tool/search_anchors_v2.json` (ChatGPT's) are kept; only passages it never graded are newly
judged. On fresh questions the engineering assistant (Claude) grades everything. Claude wrote the fresh questions too:
this is a blinded review, not independent reader judgment.

## Measures and decision

Primary: direct precision at five (P@5) on the 36 fresh questions with an answer in the scriptures. Secondary: share of
those questions with at least one direct answer in the top five; related-or-better P@5; nDCG@5 with gains 0/1/3; the
same measures on the four Spanish questions as their own slice; reranker time per question on this desktop.

1. **Choose B or C** on the development questions by direct P@5 (C if tied). Only the chosen one is compared on fresh
   questions.
2. **Pass** when, on fresh questions, the chosen reranker beats A in direct P@5 by **at least 10 percentage points**, the
   lower end of a paired 95% bootstrap interval (10,000 resamples of questions, seed 20261017) is **above 0**, and
   related-or-better P@5 is **no more than 5 points below** A.
3. **Pass:** proceed to the integration study (Windows first, phone student later). **Fail:** record it and stop this
   branch.

Factual questions with no answer in the scriptures: report what each method returns. Reranker scores are not a
confidence and are not used to decide "no answer" here.

Amendments, if any, are added below with their reason and date, never by editing the text above.

## Amendments

None.
