# BGE, Qwen and Nemotron: Results

Protocol: `docs/ANSWER_FOCUS_CHALLENGERS_PROTOCOL.md` (frozen before inference).

## Important caveat, stated up front (per the frozen protocol)

This reuses the same 10 questions already used in every earlier calibration/richer-inputs/concentration
experiment in this research line. The protocol explicitly calls these "exploratory development data, not
a fresh held-out test" and says **"do not claim a winner on independent data."** This result identifies a
promising candidate worth a real, independent evaluation -- it does not itself prove that candidate wins.

## What was compared

Five methods' top-5 results, fixed-slot scored (missing slots count as 0), on the 10 reused test
questions (8 answerable, 2 answer-absent controls: `test-phone-model`, `test-rice-protein`):

| Method | What it is |
|---|---|
| `compass_top5` | The engine's own 4-lane fusion ranking, no reranker at all |
| `answer_focus_today_bge10` | Today's shipped Answer Focus: BGE reranks Compass's top 10 |
| `bge_at200` | BGE reranks Compass's top 200 (does widening the pool alone help?) |
| `qwen_at200` | Qwen3-Reranker-0.6B reranks Compass's top 200 |
| `nemotron_at200` | nvidia/llama-nemotron-rerank-1b-v2 reranks Compass's top 200 |

152 unique passages across all five methods' result sets were graded blind (question + verse text only,
no method/rank/score visible): 92 reused from prior rounds' grades, 60 newly graded for this round.

## Result

| Method | direct P@5 | related P@5 | any-direct | false promotions | absent-control results |
|---|---|---|---|---|---|
| `compass_top5` | 0.350 | 0.550 | 0.750 | 18 | 5, 5 |
| `answer_focus_today_bge10` (shipped) | 0.350 | 0.550 | 0.625 | 18 | 5, 5 |
| `bge_at200` | 0.300 | 0.525 | 0.625 | 19 | 5, 5 |
| `qwen_at200` | 0.325 | 0.575 | 0.750 | 17 | 5, 5 |
| **`nemotron_at200`** | **0.550** | **0.725** | **1.000** | **11** | 5, 5 |

**Nemotron is a clear standout on this data.** It beats today's shipped Answer Focus on every measure:
direct-answer rate (0.550 vs 0.350, a 0.200 gap -- larger than any gain seen anywhere else in this
research line), related-answer rate (0.725 vs 0.550), any-direct coverage (1.000 vs 0.625 -- it found a
direct answer on all 8 answerable questions, the only method so far to do that), and fewer wrong
passages promoted into the displayed top-5 (11 vs 18).

Qwen is roughly on par with today's shipped method -- slightly worse direct P@5 (0.325 vs 0.350), slightly
better related P@5 and any-direct. Not a clear win either way.

Widening BGE's own pool from 10 to 200 candidates (`bge_at200`) made things slightly worse, not better --
consistent with the earlier wide-pool experiment's finding that candidate depth alone isn't the lever.

**No ranker here was given a calibrated cutoff.** Per the protocol, all five still return 5 results on the
2 answer-absent control questions (5, 5 each) -- raw reranker scores are not calibrated probabilities, so
none of these numbers reflect what a cutoff-filtered, abstaining version of any of these methods would do.
That calibration step is exactly what made the current best-evidenced 2-feature model correctly abstain on
both absent questions in earlier rounds, and would need to be redone for whichever reranker is carried
forward.

## What this does and doesn't establish

- **Does establish:** on this specific set of 10 questions and their specific 200-candidate pools, Nemotron's
  reranking produces noticeably better fixed-slot results than BGE's, by a margin much larger than any
  difference seen between input-engineering variants of BGE scoring in this research line so far.
- **Does not establish:** that Nemotron wins in general, that it would hold up on fresh questions, that it
  is practical on a phone (precision/runtime/memory were explicitly out of scope this round per the
  protocol -- this ran BF16 on a Kaggle T4 GPU, CPU-only phone deployment is a separate question entirely),
  or that it should replace BGE in production. The protocol is explicit: "any model selection requires a
  new frozen held-out set."

## Recommended next step

Given the size of the gap, Nemotron is worth pursuing further -- but correctly, not by skipping straight to
shipping it:
1. A fresh, genuinely held-out set of questions (not reused from prior rounds) to confirm this isn't an
   artifact of these particular 10 questions.
2. If confirmed, the same calibration (Platt scaling + cutoff) this research line has applied to every
   other candidate, so it can correctly abstain on answer-absent questions instead of always returning 5.
3. Separately, and only after ranking quality is confirmed: practicality on the actual target device
   (quantization, runtime, memory) -- nvidia/llama-nemotron-rerank-1b-v2 is a larger and differently-shaped
   model than BGE-reranker-v2-m3, so this is not a given even if ranking quality holds up.

Nothing in this phase changes production. `docs/ANSWER_FOCUS_CHALLENGERS_PROTOCOL.md`'s frozen scope
(no generation, no learned fusion, no filtering or calibration, no selection decision) was followed as
written.
