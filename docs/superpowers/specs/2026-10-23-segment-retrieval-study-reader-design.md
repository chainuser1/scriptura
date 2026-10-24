# Segment-level retrieval and a study reader — Design

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:writing-plans
> to turn this design into an implementation plan before any code is
> written. **Also required, before that plan:** the evaluation step in
> "Evaluation gate" below must run and clear its bar first. Do not skip
> straight to implementation planning on the strength of this design alone.

## Intent and why

Two related problems, both rooted in the same cause: search results are
retrieved and scored one verse at a time, with no notion of a multi-verse
passage as a retrieval unit.

1. **Disconnected adjacent results** (already fixed, see
   `docs/superpowers/specs/` commit `11905c9` / ADR-001): two verses that
   both rank highly show as separate cards instead of one range. Fixed as a
   pure display-layer grouping on top of today's per-verse retrieval --
   does not touch what gets retrieved, only how already-retrieved verses are
   shown.
2. **Missing context, unsolved today**: a highly-relevant verse's necessary
   neighbor sometimes never gets retrieved at all, because it individually
   scores lower even though together the two verses read as one complete
   thought (e.g. Proverbs 3:5 "Trust in the LORD with all thine heart" alone,
   without 3:6 "and lean not unto thine own understanding"). This is **not
   a new observation** -- it is an already-named, unresolved blocker in
   `docs/RETRIEVAL_V2_RESULTS.md`'s findings table:

   > Missing context | Some verses are questions, continuations, or
   > historically specific instructions. Single-verse relevance may require
   > a passage window; window-level quality is not yet measured.

The owner's proposal: retrieve coherent multi-verse **segments** per chapter
as the actual unit (not verses, with post-hoc merging), rerank those
segments with the existing Ezra/Apollos models, and give the reader a new
**study reader** view when they open a result -- the matched segment in
place, the other results for the same query one tap away, and an "expand to
full chapter" escape hatch into the app's normal immersive reader.

## Why this is a design doc, not a plan

This repo's own prior research (`docs/RETRIEVAL_V2_RESULTS.md`, `docs/MATHEMATICAL_RETRIEVAL_RESULTS.md`,
`docs/RETRIEVAL_V2_PROTOCOL.md`) is unusually rigorous for a mobile app:
16 fixed and 4 learned retrieval configurations were tested against a
1,153-judgment, 36-question answer key before any of them were judged fit
to ship; several promising-looking learned methods (`"Learned linear, full
corpus"`, etc.) were explicitly **rejected** after measurement despite
intuitive appeal, and the "Device feasibility" blocker states: *"no new
method has demonstrated a relevance gain warranting phone integration or
profiling."* Segment-level retrieval is exactly this kind of new method. It
must clear the same bar before it reaches a phone, not be shipped on the
strength of the idea alone -- see **Evaluation gate** below.

## Current state (what exists today)

- **Retrieval unit is `verse_id`, globally.** `engine/src/search.rs`'s
  `Retrieval` struct holds one dense embedding row per verse
  (`verse_ids.npy` / `dense_embeddings.f16.npy`, loaded flat, looked up by
  `row_of(verse_id)` binary search). `Hit { verse_id, score, .. }` is the
  wire shape every search path returns.
- **Scoring is "Compass," not a single embedding-similarity pass.** Per
  `docs/RETRIEVAL_V2_RESULTS.md`, Compass (96.7% Related P@5, 46.7% Direct
  P@5) already beats every tested learned-fusion alternative by a wide
  margin on this corpus. Whatever segment-level retrieval becomes, it has to
  integrate with or deliberately replace Compass's logic in
  `engine/src/search.rs` -- not assume a generic "embed query, cosine
  against candidates" pipeline that doesn't reflect how this engine
  actually works today. **This design does NOT summarize what Compass's
  non-embedding signals actually are, or whether they operate at
  verse-granularity or something coarser.** That is a real unknown, not a
  decided fact being left out for brevity: the first task for whoever picks
  this up is reading `engine/src/search.rs`'s Compass implementation (and
  whatever of `docs/RETRIEVAL_V2_PROTOCOL.md`/`docs/MATHEMATICAL_RETRIEVAL_RESULTS.md`
  describes it) closely enough to answer "can Compass score a multi-verse
  window candidate as-is, or does scoring it require touching Compass's
  internals" -- before estimating how much work Option A actually is. If
  Compass's signals are verse-granular only, adapting it to windows could
  be the majority of this feature's engineering effort, not a footnote.
- **`Passage` (`lib/data/content/content_repository.dart`) is exactly one
  verse.** `verseId`, `chapter`, `verse` are all singular, non-range fields.
  No schema concept of a verse range exists anywhere in the Dart layer or
  the content DB.
- **Answer Focus rerank cost is real and newly measured.** Apollos int8/CPU:
  `_apollosCpuFactor ~= 0.994` (~14x Ezra's per-candidate cost), measured
  2026-10-19 on a real Android phone: ~12.6s for 10 single-verse candidates
  at a device trial `cpu_ms` of ~1267. Segments longer than one verse mean
  longer token sequences per candidate -- cost scales with segment length,
  not just candidate count. (Partially mitigated same night by fixing a
  hardcoded thread-count bug -- `lib/services/engine/engine_pack.dart`'s
  `threads` field now uses `Platform.numberOfProcessors` instead of a
  guessed constant -- but this does not change the fundamental per-token
  cost, only parallelism within one run.)
- **No pericope/paragraph boundary data is confirmed to exist** across this
  app's text sources (KJV and others). This design assumes none exists
  unless the implementer finds otherwise; see "Segment boundary strategy"
  below for what that means for scope.
- **The reader already has multi-verse UI precedent.** `lib/app/verse_tools.dart`'s
  `citationFor`/`formatForCopy` already format a verse range
  ("Alma 32:21-23") from a `List<Passage>`, used today by the reader's
  manual verse-selection/copy flow (`lib/features/read/read_screen.dart`).
  The study reader's "show this segment in place" view can likely reuse
  this formatting, and possibly adapt the reader screen's existing
  "surrounding context" rendering (`search_screen.dart`'s preview pane
  already renders `for (final p in around)` -- a chapter's worth of verses
  with the matched one highlighted) rather than building new UI from
  scratch.

## Goals

- Retrieve passages (not individual verses) as the search unit, so a
  multi-verse thought that spans e.g. Proverbs 3:5-6 is one retrieval
  candidate from the start, not an artifact of post-hoc verse merging.
- Preserve or improve retrieval quality against the existing 36-question
  evaluation set -- never ship a regression against Compass's current
  96.7%/46.7%/0.636 (Related P@5 / Direct P@5 / Pooled nDCG@5) baseline.
- Give the reader a focused "study" view of the matched segment, with easy
  access to the other results and a clear path to the full chapter.

## Non-goals

- Replacing or retraining Compass's scoring logic. Segments are a candidate
  *shape* change; Compass (or whatever scores segments) can be adapted,
  not necessarily rewritten.
- Solving "missing context" for every conceivable case (a segment window is
  a mitigation, not a guarantee of perfect context -- some verses need a
  whole chapter, which is already one tap away via "expand to chapter").
- Changing Ezra's or Apollos's model weights, tokenization, or budget
  constants (`kFocusBudgetMs`, `kApollosBudgetMs`) -- segment length is the
  lever to manage rerank cost, not the budget constants themselves, though
  the budget math will need to account for longer per-candidate token
  counts once segment length is chosen.

## Anti-goals (would make this a failure even if it technically works)

- Shipping a method to real users' phones without the same kind of measured
  evidence this repo's own prior research required of every other retrieval
  change (see Evaluation gate).
- A "study reader" that duplicates or forks the existing immersive reader's
  rendering logic wholesale instead of reusing it (`read_screen.dart`'s
  existing verse-rendering, highlighting, and navigation should be the
  base, with the study view as a focused variant/overlay, not a parallel
  implementation to maintain forever).
- Segments so long that Apollos's rerank cost becomes impractical even at
  its already-raised 40s budget, silently pushing most real users into
  constant fallback/timeout.

## Segment boundary strategy

Three options, in increasing cost and increasing faithfulness to the text's
actual structure:

| Option | What it is | Cost | Risk |
|---|---|---|---|
| **A. Fixed-size sliding windows (recommended starting point)** | Every chapter is split into overlapping windows of N verses (e.g. N=3, stride 1: verses [1-3], [2-4], [3-5], ...). Each window becomes a retrieval candidate, embedded independently offline. | Cheap, mechanical, no new data needed, runs today with the existing offline embedding pipeline's pattern. | Many overlapping/redundant candidates per chapter inflate the retrieval index size and candidate pool; a window can still split a thought across its boundary (just less often than single verses do). |
| **B. Real pericope/paragraph data** | Use existing paragraph markers if any licensed text source in this app's corpus actually encodes them (some translations' source data does; KJV commonly does not in plain-text form). | Free at runtime if the data already exists; otherwise requires a new one-time data acquisition/licensing question before any engineering starts. | **Unconfirmed whether this app's actual text sources have this data at all** -- first task for whoever picks this up is checking `docs/check_data_sources.py`'s output / the raw source files before assuming either way. |
| **C. One-time offline LLM segmentation** | Run an LLM once, offline, over the whole corpus to propose segment boundaries (e.g. "this chapter's natural thought-breaks are at verses 3, 6, 9..."), cache the result as a build artifact. | More faithful than fixed windows, still a one-time offline cost (no runtime LLM calls). | New offline tooling, new review step (LLM segmentation needs spot-checking against a sample, same rigor this repo already applies to everything else), real cost/time to run over the full corpus once. |

**Recommendation: start with Option A for the evaluation step below.** It is
the only option cheap enough to produce an evaluable candidate index without
first resolving B's data-availability question or committing to C's tooling
cost. If A clears the evaluation gate with a real quality gain, B or C
become justified follow-up investment to improve segment quality further --
not prerequisites to finding out whether the whole approach is worth it.

## Rerank cost implications

Segment length directly multiplies Apollos/Ezra's per-candidate token count,
which was already the night's other real finding (Apollos ~14x Ezra's
per-candidate cost, now budgeted at 40s rather than the original 1.5s-scale
assumption). A 3-verse segment is roughly 3x one verse's tokens; rerank
`k` (how many candidates get reordered) and segment length trade off
against the same budget. Concretely: whoever implements this must re-run
the same kind of on-device timing measurement done 2026-10-19 (device trial
`cpu_ms` + real `session.run()` time) for the actual segment length chosen,
not assume the existing `_apollosCpuFactor`/`_cpuFactor` constants (measured
for single-verse candidates) hold at a different candcandidate size.

## Schema / pipeline impact (if Option A ships)

- **Offline embedding build** (wherever `dense_embeddings.f16.npy` is
  actually generated -- not conclusively identified in this session; the
  implementer's first task is finding that script, not assuming
  `tool/build_engine_pack.py`, which is packaging-only): needs a sliding-
  window pass over each chapter's verses, embedding each window instead of
  (or alongside) each verse.
- **`verse_ids.npy` equivalent**: becomes a window-id index instead of (or
  alongside) a verse-id index -- needs a stable encoding (e.g. `(first_verse_id,
  last_verse_id)` pairs, or a separate window-id space with a lookup table
  back to its verse range).
- **`engine/src/search.rs`'s `Hit`**: needs a verse-range shape, not a
  single `verse_id` -- this is the actual architecture change ADR-001
  deliberately avoided for Problem A; Track 2 is where it belongs if the
  evaluation gate clears.
- **Dart `Passage`**: likely needs a new type (not a mutation of the
  existing single-verse `Passage`, which many other screens/features
  depend on exactly as it is) representing a resolved segment -- a list of
  `Passage`s plus the combined reference, similar in shape to this
  session's `_Group` from ADR-001 but engine-driven rather than a display-
  only grouping of independently-retrieved verses.
- **Content DB**: likely unaffected -- segments are a retrieval/ranking
  concept, not a new way to store scripture text. `Passage`s underlying a
  segment can still be fetched one verse at a time via today's
  `ContentRepository.getPassage`.

## Runtime behavior: fallback and overlapping-window dedup

**Budget fallback:** reuse the existing warn-and-override pattern from the
Apollos int8/Ezra work (`lib/services/engine/answer_focus.dart`'s
`choose()`/`forceApollos`, and the Settings picker's warn-before-override
dialog), rather than inventing a second fallback mechanism. Concretely: if
a device's measured per-candidate cost at the chosen segment length would
blow the relevant budget, the same "device doesn't fit, offer to proceed
anyway or fall back" decision applies -- segment length is just another
factor multiplying into the existing `cpuMs * costFactor * k` budget math,
not a new axis needing its own UI.

**Overlapping-window dedup (Option A specifically):** sliding windows with
stride 1 WILL return near-duplicate overlapping candidates for the same
underlying passage (e.g. `[1-3]`, `[2-4]`, `[3-5]` all scoring well for one
real hit). This must be resolved before results reach the UI or the
evaluation step, not left as a display-layer afterthought: generalize
ADR-001's adjacency-merge logic (today, it merges independently-retrieved
*single-verse* hits that happen to be adjacent) into an overlap-resolution
step that also collapses overlapping *multi-verse window* hits into their
best-scoring union, keeping only the highest-scoring window per connected
overlapping group rather than showing 3 near-identical cards. This is new
logic, not a reuse of ADR-001's code as-is -- adjacency (verse N and N+1)
and overlap (ranges that share verses) are related but distinct conditions.
Unresolved, this also risks inflating the evaluation step's own P@5 numbers
by letting overlapping windows count as independent hits for the same gold
verse (see "Scoring rule for window-shaped hits" above, which already
closes off the specific inflation risk of wide-window-happens-to-contain-
the-answer; this is the complementary risk of the *same* answer being
counted multiple times via overlapping windows).

## Study reader UI (sketch, not final)

- Entry point: tapping a search result opens the study reader instead of
  the normal immersive reader, showing the matched segment's verses in
  place (reusing `read_screen.dart`'s verse rendering where possible, not a
  new rendering implementation).
- A way to browse the other results for the same query without leaving
  this mode -- e.g. a bottom sheet or side list of the remaining result
  segments, consistent with how the existing search screen's live preview
  pane already works on wide layouts.
- An explicit "expand to full chapter" action that hands off to the
  existing immersive reader at this segment's position -- this is the
  normal reader, unchanged, just entered from a different place.
- Open question for whoever builds this: does the study reader replace the
  existing live-preview pane (today's wide-layout search screen already
  shows a passage-in-context pane beside the results list) or sit
  alongside it as a separate mode? This needs a product call, not an
  architecture one -- flag it to the owner before implementation.

## Evaluation gate (must clear before any of this reaches a device)

Before writing engine code: build Option A's window index over a subset or
the full corpus, run it through the **same** evaluation protocol as
`docs/RETRIEVAL_V2_RESULTS.md` (Related/Direct P@5, Pooled nDCG@5 against
`tool/search_anchors_v2.json`), and compare directly against Compass's
existing 96.7%/46.7%/0.636 baseline.

**Pre-registered pass bar (fixed before results come in, not chosen after
seeing them):** segment-level retrieval ships only if it beats Compass's
baseline on **all three** metrics by **at least +5 percentage points on
Related/Direct P@5 and +0.03 on Pooled nDCG@5**. This margin exists
specifically because N=36 is a small held-out set where a +1-2 point swing
is plausibly noise, not signal -- the original research's own rejections
(e.g. "Learned interactions, original candidate pool": 78.3%/28.3%/0.454,
clearly worse than Compass on two of three metrics) make this kind of
multi-metric, non-trivial-margin comparison the project's existing norm,
just not previously written down as a numeric rule. A result that clears
one or two metrics but not all three does not pass -- document it as a
partial/negative result the same way existing rejected methods are
documented, per the paragraph below.

**Scoring rule for window-shaped hits against a verse-level answer key:**
a window `[first_verse_id, last_verse_id]` counts as a match for a gold
verse only if the gold verse falls strictly inside that range AND the
window's independently-computed relevance score would place it at the same
rank position a single matching verse would have occupied under Compass
today. Do not award credit merely because a wide window happens to contain
the right verse somewhere inside it -- a 10-verse window "containing" the
answer is not the same claim as a 1-2 verse window answering it, and
scoring them identically would mechanically favor wider windows regardless
of whether segmentation actually helped. (This is a pre-registered choice,
specifically to close off the failure mode the builder-check review
flagged: wider windows catching more gold verses "almost by construction.")

**Fresh vs. reused question set -- owner's call, not resolved here:**
whoever runs this evaluation must get an explicit answer from the app's
owner on whether reusing the existing (now-inspected) 36-question set with
disclosure is acceptable, or whether a fresh, independently-judged question
set is required first. The two options differ by roughly the same order of
magnitude of work as the original 1,153-judgment exercise if a fresh set is
required -- this is a real scheduling decision, not a detail a builder
should default on silently.

**Only if segment-level retrieval clears the pre-registered bar above**
does this move to an implementation plan (`superpowers:writing-plans`). If
it does not clear this bar, the correct outcome is: do not ship it, and
document why in a results doc the same way `docs/RETRIEVAL_V2_RESULTS.md`
documents the rejected learned-fusion attempts -- that is a successful
research outcome in this project's own established practice, not a
failure.

## What's left to the builder

- **First task, before anything else:** read Compass's actual scoring logic
  in `engine/src/search.rs` and determine whether it can score a
  multi-verse window candidate as-is or requires internal changes (see
  "Current state" above) -- this materially changes the size of the whole
  effort and should inform, not follow, time estimation.
- Locate the actual offline embedding generation script (not firmly
  identified this session) before writing any new embedding code.
- Resolve the Option B data-availability question (does any real text
  source here actually carry paragraph/pericope boundaries) before
  dismissing it in favor of Option A long-term, even though A is the right
  starting point for the evaluation step.
- Choose segment length (window size N) empirically from the evaluation
  step's results, not a priori -- this design deliberately does not fix N.
- Implement overlapping-window dedup (see "Runtime behavior" above) as part
  of the evaluation step itself, not after -- an un-deduped candidate pool
  would distort the pre-registered P@5/nDCG@5 numbers the pass bar depends
  on.
- Decide the study-reader-vs-existing-preview-pane UX question above with
  the owner before building UI.
- Re-measure rerank timing at whatever segment length the evaluation step
  settles on; do not assume today's single-verse `_apollosCpuFactor`/
  `_cpuFactor` constants.

## Owner decisions still needed (cannot be settled by a builder)

1. **Fresh vs. reused evaluation question set** (see "Evaluation gate"):
   whether reusing the existing, now-inspected 36-question set with
   disclosure is acceptable, or a fresh independently-judged set is
   required first -- a real scheduling/cost decision, not a technical one.
