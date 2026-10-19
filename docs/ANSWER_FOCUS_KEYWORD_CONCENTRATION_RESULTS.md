# Keyword Concentration Experiment: Results

Protocol: `docs/ANSWER_FOCUS_KEYWORD_CONCENTRATION_PROTOCOL.md` (frozen before this run).

## Decision rule (frozen in advance)

A real win needs ALL of:
1. CV log loss improvement > 0.01 vs. the 5-feature richer-inputs baseline (0.6268).
2. Final-test direct P@5 improvement > 0.125 vs. the 2-feature baseline (0.350) -- more than one
   question's worth out of 8, not a 1-question swing.
3. No regression on any-direct rate or on correctly abstaining for the two answer-absent test
   questions.

## Result: fails the bar at the first gate

**CV log loss got slightly worse, not better.**

| Model | CV log loss |
|---|---|
| 2-feature baseline | 0.6280 |
| 5-feature richer-inputs | 0.6268 |
| **6-feature + concentration** | **0.6280** |

Adding concentration moved CV log loss from 0.6268 to 0.6280 -- a regression of 0.0012. The
required bar was an *improvement* greater than 0.01. This alone is enough to stop: the frozen
protocol said the CV check comes first, and it was not met.

The fitted weight on concentration was **-0.0447** (unconstrained, since the protocol deliberately
made no sign assumption for this feature). The model found a small negative association, not a
useful positive one, and the other five weights barely moved (`dense` 0.029, `sparse` 0.0,
`colbert` 0.056, `genome` 0.241, `bge_logit` 0.432 -- almost identical to the richer-inputs run).
Concentration is not carrying new information the other five signals didn't already have.

Ran the full pipeline anyway, per the decision to complete all steps and report honestly:

**Calibration (120-row sample, same grades as every prior round):**

| Model | F1 at cutoff |
|---|---|
| 5-feature richer-inputs | 0.2857 |
| 6-feature + concentration | 0.2857 (no change) |

**Final test (10 held-out questions, 1 new passage graded blind):**

| Method | direct P@5 | related P@5 | any-direct | mean shown | absent-question results |
|---|---|---|---|---|---|
| 2-feature + cutoff (current best) | 0.350 | 0.550 | 0.750 | -- | 0, 0 |
| 5-feature richer-inputs (unfiltered) | 0.375 | 0.600 | 0.625 | -- | 0, 0 |
| **6-feature + concentration (unfiltered)** | **0.350** | 0.575 | 0.625 | 5.0 | 5, 5 |
| **6-feature + concentration + cutoff** | **0.350** | 0.525 | 0.625 | 4.4 | 0, 0 |

The new passage graded blind, `test-teacher-factions:25461` (Luke 12:1, Jesus warning disciples
about Pharisaical hypocrisy), was graded 0 -- not an answer to "What does Paul say about believers
dividing themselves into groups named after different teachers?" (which is 1 Corinthians
territory). It did not change the outcome either way.

Direct P@5 stayed flat at 0.350 -- identical to the 2-feature baseline and worse than the
5-feature richer-inputs result (0.375). The required improvement was more than 0.125 over 0.350;
the actual change was 0.000. Any-direct rate also did not recover to the 2-feature-plus-cutoff
baseline's 0.750 -- it sits at 0.625, same as richer-inputs, still behind the current best method.

## Verdict

**This does not clear the bar.** Keyword concentration, added as a sixth input to the same
monotonic-logistic architecture, produced no real gain on any of the three pre-agreed measures and
a small CV regression. This is consistent with the richer-inputs result: the architecture (a tiny
linear combiner) is the limiting factor, not the absence of this particular input. The free
`concentration` feature, now captured by the engine's opt-in `concentration` flag, remains
available for a future experiment that changes the combiner itself, but is not adopted for
production, and nothing shipped in this phase touches app behavior.

## Standing comparison table (all experiments to date)

| Method | CV log loss | Calibration F1 | direct P@5 | related P@5 | any-direct | abstains correctly |
|---|---|---|---|---|---|---|
| Today's shipped Answer Focus | -- | -- | 0.350 | 0.550 | 0.625 | no, no |
| 2-feature learned + cutoff | 0.628 | 0.358 | 0.350 | 0.550 | 0.750 | yes, yes |
| 5-feature richer-inputs (unfiltered) | 0.6268 | 0.286 | 0.375 | 0.600 | 0.625 | yes, yes |
| 5-feature richer-inputs + cutoff | 0.6268 | 0.286 | 0.375 | 0.550 | 0.625 | yes, yes |
| **6-feature + concentration (unfiltered)** | **0.6280** | 0.2857 | 0.350 | 0.575 | 0.625 | no, no |
| **6-feature + concentration + cutoff** | **0.6280** | 0.2857 | 0.350 | 0.525 | 0.625 | yes, yes |

The 2-feature learned + cutoff model remains the best-evidenced candidate for a future shipped
improvement over today's Answer Focus: it ties on direct-answer rate, beats on any-direct rate,
and is the only method so far that correctly abstains on both answer-absent test questions while
also winning on related-answer rate. Nothing in this phase changes that recommendation.
