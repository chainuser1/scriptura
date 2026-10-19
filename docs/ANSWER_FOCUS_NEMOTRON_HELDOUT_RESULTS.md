# Nemotron held-out confirmation: results

Protocol: `docs/ANSWER_FOCUS_NEMOTRON_HELDOUT_PROTOCOL.md` (frozen before inference). 26 genuinely fresh
questions (22 answerable, 4 answer-absent controls), never used in any earlier round of this research
line. 343 passages graded blind (question + verse text only, no method/rank/score visible).

## The frozen decision rule, checked exactly

> Nemotron's direct P@5 to beat today's shipped method by more than 0.10.

| Method | direct P@5 | related P@5 | any-direct | false promotions |
|---|---|---|---|---|
| `compass_top5` | 0.182 | 0.373 | 0.636 | 69 |
| `answer_focus_today_bge10` (shipped) | **0.200** | 0.446 | 0.636 | 61 |
| `bge_at200` | 0.227 | 0.509 | 0.682 | 54 |
| `qwen_at200` | 0.236 | 0.509 | 0.727 | 54 |
| **`nemotron_at200`** | **0.300** | **0.591** | **0.909** | **45** |

The exact gap (unrounded, 22 answerable questions): **0.10000000000000003** -- to the limits of
floating-point, exactly 0.10, not more than 0.10. **By the letter of the rule set in advance, this is a
tie at the threshold, not a confirmed pass.** It does not clear the bar I set specifically to avoid
rationalizing a marginal result into a claimed win.

## What else the data shows, honestly

The headline number lands exactly on the line, but the rest of the picture is not ambiguous:

- **Any-direct coverage**: Nemotron found at least one direct answer on **20 of 22** answerable questions
  (0.909). Today's shipped method found one on only **14 of 22** (0.636). That is a 6-question gap, not a
  boundary case -- the largest, clearest margin of any measure in this comparison.
- **False promotions**: Nemotron wrongly promoted 45 non-answer passages into its displayed top-5, versus
  61 for today's shipped method -- 16 fewer wrong results shown to a user, across 22 questions.
- **Related P@5**: 0.591 vs 0.446, also a clear, non-boundary gap.
- This is the same direction and a similar relative size to the original challengers-round result
  (direct P@5 gap +0.200 there vs +0.100 here; any-direct gap +0.375 there vs +0.273 here). The absolute
  size shrank on fresh data, which is expected and is exactly why this confirmation round was worth
  running -- but the direction held, and did not reverse or flatten to zero.

Both absent-control counts are unchanged at 5/5 for every method, same as every prior round: no ranker
here has a calibrated cutoff, so none of them abstain yet.

## Verdict

**Mixed, reported plainly, not reframed.** The single pre-committed pass/fail number (direct P@5 gap > 0.10)
does not pass -- it ties the threshold exactly. Declaring victory on that technicality would repeat the
exact mistake this whole protocol was designed to prevent. At the same time, dismissing Nemotron as "no
better" would misrepresent the any-direct and false-promotion numbers, which show a real, large,
non-boundary advantage that held up on data it had never seen.

**Conclusion: Nemotron is still the most promising candidate in this research line, but it has not yet
cleared the explicit bar for moving to calibration.** The direct-P@5 metric specifically needs a larger or
differently-measured confirmation before that step, not an immediate green light.

## Recommended next step

Given the result is genuinely mixed rather than a clean pass or fail, worth deciding explicitly with the
user: either (a) run one more, larger confirmation batch to resolve whether the direct-P@5 gap is reliably
above or below the line, since 22 questions gives each one almost 4.5% of weight and a single question's
grade can move the gap by that much; or (b) treat the any-direct and false-promotion evidence as
sufficient on its own to proceed to calibration, explicitly overriding the single direct-P@5 threshold as
too narrow a test given everything else measured. Both are defensible; neither should be assumed without
asking.
