# Nemotron held-out confirmation: frozen protocol

2026-10-19. Record before inference. No application changes.

## Why

`docs/ANSWER_FOCUS_CHALLENGERS_RESULTS.md` found nvidia/llama-nemotron-rerank-1b-v2 clearly ahead of
today's shipped BGE reranker (direct P@5 0.550 vs 0.350, any-direct 1.000 vs 0.625, fewer false
promotions) -- but on the same 10 questions already reused across every earlier round in this research
line. That protocol explicitly said "do not claim a winner on independent data." This protocol runs the
same comparison on a genuinely fresh, never-before-used question set to confirm or disconfirm the gap.

## Scope

Compare the same five methods from the challengers round -- `compass_top5`, `answer_focus_today_bge10`
(today's shipped method), `bge_at200`, `qwen_at200`, `nemotron_at200` -- using the same pinned model
revisions (Qwen/Qwen3-Reranker-0.6B `e61197ed45024b0ed8a2d74b80b4d909f1255473`,
nvidia/llama-nemotron-rerank-1b-v2 `828765652b05bd439c9789d2a6d093db1caa1443`), the same official input
templates, the same 512-token limit, the same fixed-slot top-5 scoring with missing slots counted as 0.
No generation, no learned fusion, no filtering or calibration, no selection decision in this stage --
identical scope restrictions to the challengers protocol.

## Question set

24 new questions, authored by the engineering assistant, checked against all 94 previously used questions
(76 historical canonical questions in `local-benchmarks/reranker-stage2/rankings.json`, 8 calibration and
10 test questions in `tool/answer_focus_calibration_questions.json`) to avoid direct paraphrase. These
target narrow, specific-verse answers (matching the calibration/test question style), not broad doctrinal
topics (matching the historical-pool style) -- the style this whole research line measures.

- 20 answerable questions, each with one or a small number of specific intended-answer verses in mind at
  authoring time (used only to check the question has a real textual answer, never fed to any model or
  used as a scoring shortcut -- grading is blind, same as every prior round).
- 4 answer-absent control questions: no scripture passage answers them, used to check any-method false
  "answer" behavior, same role as `test-phone-model`/`test-rice-protein` in the prior round.
- Mostly English; at least 2 Spanish questions, matching the established language mix.

Frozen question list: `tool/answer_focus_nemotron_heldout_questions.json`.

## Procedure

1. Candidate generation: Compass retrieves the same 200-candidate pool per question as every prior round
   (reuses the existing pipeline, not reimplemented).
2. BGE int8 scores all 200 candidates per question (native engine, cached, same as prior rounds).
3. Qwen and Nemotron each score the same 200 candidates per question, offline, same procedure as
   `tool/answer_focus_challengers_kaggle.py` (GPU, BF16, official templates, 512-token limit, smoke test
   first, per-pair checkpointing).
4. Build the blind review packet: shuffled union of all five methods' top-5 results per question, hashed
   filenames, no method/rank/score visible to the reviewer.
5. Blind-grade every passage: 0 (non-answer), 1 (related/context-dependent), 2 (direct answer), explicit
   reason required. No grade inferred from model agreement; unjudged passages are never treated as
   negative.
6. Report fixed-slot direct/related P@5 on the 20 answerable questions, any-direct coverage, false
   promotions (graded-0 passages actually shown), and the 4 absent controls' result counts separately.

## Decision rule (frozen in advance)

The earlier round's gap was large: direct P@5 +0.200, any-direct +0.375, false promotions -7 (of ~18).
A real confirmation on this fresh set needs:
- Nemotron's direct P@5 to beat today's shipped method (`answer_focus_today_bge10`) by more than 0.10
  (half the previously observed gap -- a meaningful margin, not a coin-flip reproduction).
- Nemotron's any-direct rate not to regress below today's shipped method's rate on this fresh set.
- No new failure mode on the Spanish questions or the absent controls that the prior round didn't surface.

If the gap holds at roughly this size: proceed to calibration (Platt scaling + cutoff) as the next step,
not directly to shipping. If the gap shrinks to noise level or reverses: report that plainly, the same way
every negative/mixed result in this research line has been reported, and do not proceed to calibration.

Practicality (quantization, on-device runtime, memory) is explicitly out of scope for this round, exactly
as it was for the challengers round -- a separate question that only matters if ranking quality is
confirmed here first.
