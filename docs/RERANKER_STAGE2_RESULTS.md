# Reranker test (stage 2): results

2026-10-17. Protocol frozen beforehand: [RERANKER_STAGE2_PROTOCOL.md](RERANKER_STAGE2_PROTOCOL.md) (commit `5ae2700`). Research
only; the app is unchanged.

## Decision

**Passes the predeclared bar, exactly at the line.** It is too slow to ship as tested.

On the 36 fresh questions with an answer in the scriptures, `BAAI/bge-reranker-v2-m3` reordering the app's own top 30
raised direct-answer precision at five from **29.4% to 39.4%** (+10.0 points; paired bootstrap 95% interval +2.8 to
+17.2). Related-or-better precision rose too (63.9% → 69.4%). The bar was +10 points with the interval above zero and no
more than 5 points lost on related results: all three hold, the first with no margin.

## Results

Direct P@5 is the share of the top five that answer the question; "any direct" is the share of questions with at least one.

| Questions | Method | Direct P@5 | Related P@5 | Any direct | nDCG@5 |
|---|---|---:|---:|---:|---:|
| Fresh (36) | A. Today | 29.4% | 63.9% | 66.7% | 0.624 |
| | B. Reranker, verse | **39.4%** | 69.4% | 77.8% | 0.657 |
| | C. Reranker, context | 36.7% | 67.8% | 75.0% | 0.657 |
| Spanish (4, within fresh) | A | 35.0% | 75.0% | 50.0% | 0.558 |
| | B | 60.0% | 90.0% | 100% | 0.834 |
| Development (36) | A | 48.3% | 96.7% | 83.3% | 0.807 |
| | B | 45.6% | 90.0% | 83.3% | 0.768 |
| | C | 44.4% | 89.4% | 77.8% | 0.748 |

Fresh questions, per question (B against A): 16 better, 4 worse, 16 unchanged. Clear gains on false premises, roles and
negation: "Is there any sin that will not be forgiven?" 1 → 4 direct of five; "Why does God look down on people who are
poor?" 1 → 3; "Is it ever right to be angry?" 3 → 5. Losses: fasting (4 → 1), care of elderly parents, a married
couple's arguments, God feeling far away.

## Read with care

- **Development questions disagree.** There the reranker is slightly worse. Those grades are mixed: the app's own results
  were graded earlier by ChatGPT, while the passages only the reranker brought in were graded here by Claude, who grades
  more strictly (for example, a verse that only names the topic is 1 here). That mix favours today's search. On fresh
  questions one judge graded every method alike, which is why the protocol decides on them. Still, it is a warning that
  the gain is not large or certain.
- **One judge, who also wrote the questions.** Blind to method, but not independent. 36 questions is a small sample; the
  interval is wide.
- **Verse alone beat verse with context** (B over C, chosen on development as frozen). Context did not help this model.
- **No answer is not detected.** For the four questions with no answer in the scriptures, the reranker's top scores
  (−3.7 to −9.5) overlap scores on answerable questions (as low as −9.2). Its score is not a confidence.
- **Speed.** Full precision on this desktop's CPU: median **30 s** per question for 30 passages (max 61 s), measured while
  other work was running. Even if that halves on an idle machine, it is far too slow for search. Shipping needs a much
  smaller or quantized model, fewer candidates, or both; that is the next measurement, not an assumption.

## Next

Per the protocol, a pass leads to the integration study. Given the speed, that study starts with cost, not quality:
measure int8 and smaller rerankers, and 10 or 15 candidates instead of 30, on these same questions, keeping today's
search as the yardstick. Trails need their own test.

## Reproduce

```powershell
.venv/Scripts/python.exe -I tool/reranker_stage2.py          # candidates, reranking, blind sheet
.venv/Scripts/python.exe -I tool/reranker_stage2.py --score  # with local-benchmarks/reranker-stage2/grades.json
```

Grades with reasons: `tool/reranker_stage2_key.json` (references only, no text). Model revision is recorded in
`local-benchmarks/reranker-stage2/report.json`.

## Cost test (2026-10-17, `tool/reranker_speed.py`, `tool/reranker_gpu.py`)

Same 72 questions and candidates, idle machine (Ryzen 5 5500U, built-in Radeon graphics, 4 threads). 97 passages that
the variants newly placed in a top five were graded blind with the same rubric (`local-benchmarks/reranker-speed`).

| Variant | Size | Median per search | Fresh direct P@5 (today 29.4%) | Gain, 95% interval | Development direct (today 48.3%) |
|---|---:|---:|---:|---|---:|
| PyTorch fp32, 30 | | 16.6 s | 39.4% | +10.0 [+2.8, +17.2] | 45.6% |
| ONNX fp32, 30 | 2.17 GB | 12.4 s | 39.4% | +10.0 [+2.8, +17.2] | 45.6% |
| ONNX int8 (CPU), 30 | 543 MB | 8.8 s | 40.0% | +10.6 [+3.3, +17.8] | 46.1% |
| ONNX int8 (CPU), 15 | 543 MB | 3.4 s | 38.3% | +8.9 [+2.8, +15.0] | 46.7% |
| ONNX int8 (CPU), 10 | 543 MB | 2.0 s | 37.2% | +7.8 [+2.8, +12.8] | 48.9% |
| ONNX fp16 (graphics, DirectML), 30 | 1.08 GB | 4.7 s | 39.4% | +10.0 [+2.8, +17.2] | 45.6% |
| ONNX fp16 (graphics, DirectML), 15 | 1.08 GB | 2.2 s | 37.8% | +8.3 [+2.2, +14.4] | 47.2% |
| ONNX fp16 (graphics, DirectML), 10 | 1.08 GB | 1.4 s | 36.1% | +6.7 [+1.7, +11.7] | 50.0% |

Compression costs nothing measurable: int8 and fp16 match fp32. Fewer candidates trade a little of the gain for speed
and stop the development regression (at 10 the reranker only reorders the engine's own top ten). **Gate (Answer focus
plan, Task 1): passed** — every variant keeps a gain with its interval above zero, and fp16 on this laptop's graphics
meets 1.5 s at 10 candidates. On this machine the CPU alone needs about 2 s at 10.
