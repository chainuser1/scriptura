# Grouped search results and reading context

Status: implemented and verified on `grouped-search-results`.

## Intended experience

After ranking, closely ranked matches from one chapter can appear as one result:
`Revelation 12:3–4, 11, 13–17`, followed by another result such as `Zechariah 5:7`.
The result represents the exact eight matched verses, organized into three passages.
Selecting it carries that complete collection into both the desktop preview and the
full reader. The app remains a reader of the original text; it does not invent a
summary or claim that every verse in the chapter answers the query.

## Self-review findings

- Current `_groupAdjacent` merges consecutive returned verses but cannot combine
  separated runs. It already places a group at its best-ranked member's position.
- `_selected`, `_Preview`, `_open`, and `NavState.verse` carry one passage/verse.
  The screenshot's card/preview mismatch is a data-flow problem, not just styling.
- `citationFor` labels any same-chapter collection with its first and last verse.
  Reusing it unchanged would turn `3–4, 11, 13–17` into the false citation `3–17`.
  `formatForCopy` also joins all text without showing omissions.
- `_resolve` discards retrieval scores and `_focus` returns a sorted list without
  retaining its scores. Only a prefix may be reranked. Raw retrieval scores and
  reranker scores must not be compared as if they share a scale.
- The existing reader's navigation marker is separate from saved highlights, but
  represents one verse. Automatic scrolling currently runs during rebuilds while
  that marker exists; group navigation must not repeatedly pull the user back.
- Search normally requests 20 verse hits. Grouping can legitimately produce fewer
  cards. It must not silently increase reranker work just to fill the screen.

## Decisions and constraints

### Ranking and grouping

1. Group only after retrieval and any successful Answer focus reranking complete.
2. Deduplicate verse IDs and keep their final rank and ranking provenance. Start
   each group from the highest-ranked remaining hit.
3. Consider additional hits only within the same book and chapter and a bounded
   neighborhood of that anchor. Compare each candidate to the anchor; never use
   transitive chaining or verse adjacency alone to absorb distant weak matches.
   After membership is settled, form consecutive display runs from those members.
4. Use conservative rank proximity for the initial policy, retaining which hits
   were reranked. Do not use an invented percentage similarity threshold or mix
   unrelated score scales. A reranked anchor must not automatically pull an
   unevaluated tail match into its group.
5. Choose the precise neighborhood width using representative ranked fixtures and
   manual query review before enabling separated-run grouping. Required outcomes:
   the supplied Revelation example groups when its passages are close in rank;
   a weak same-chapter tail hit remains separate; stronger results from other
   chapters retain their relative order. Do not hard-code a query-specific rule.
6. A group inherits its best member's position, with deterministic ties. Additional
   members do not provide a rank bonus. Every returned hit appears exactly once.
7. Order members and passage shortcuts canonically within a card. Do not insert
   missing verses into the match set to make a continuous range.
8. Treat search modes explicitly: meaning and similar-verse search can use rank
   proximity; exact-phrase search has no comparable relevance signal and should
   retain its canonical ordering and existing adjacent grouping initially. Explicit
   reference navigation preserves the requested reference rather than clustering it.
9. Report match counts separately from card counts, and retain truncation notices.
   Do not request more model evaluations merely because 20 hits become fewer cards.

### One collection across the UI

Represent the exact matched verse IDs, their ordered runs, the ranking anchor,
and the active reading passage together. The exact accessor/class shape is an
implementation choice; these distinctions and behaviors are required.

- **Ranking anchor:** the best-ranked verse determines placement and any explicitly
  verse-specific action.
- **Reading entry point:** opening the card starts at the first verse of the run
  containing that anchor. If verse 17 ranks highest in 13–17, begin reading at 13.
- **Matched set:** every included verse receives a temporary search marker in the
  preview and reader. Unmatched verses remain ordinary context.
- **Active passage:** a stronger border/marker identifies the current run without
  relying solely on color. Preserve saved highlights and manual text selection.
- **Navigation:** scroll only on an explicit open/jump event, not on every rebuild.
  Changing query or chapter clears stale match context; returning to the same search
  restores its card selection, expansion state, and scroll position.

### Result card and reader

The collapsed card shows the exact citation, an optional useful count such as
`3 passages · 8 matching verses`, a short excerpt from the anchor's passage, and
shortcuts `3–4`, `11`, `13–17`. The excerpt carries its own range label so readers
know which part of the group they are seeing. Expanded content shows each passage
separately with verse numbers and visible gap separators.

The reader and desktop preview share the same selection behavior. Both show the
group citation and a compact passage navigator. On a phone, long citations wrap
and the navigator can scroll horizontally. Desktop keyboard navigation has clear
focus targets and accessible names; it must not steal the reader's chapter keys.
The desktop preview must support the full chapter, using lazy rendering where
needed, rather than the current fixed six-verses-either-side slice: every passage
shortcut must be reachable even when the matches are far apart.

Passage shortcuts jump directly to their runs. `Previous passage` / `Next passage`
move among matched runs, with position text such as `Passage 2 of 3`. Nearby chapter
text remains available. `Back to results` restores the exact search location.
Respect reduced motion and keep search markers legible across reading themes and
large-text settings.

Provide a per-search `Show matches separately` option in the result menu. It offers
a straightforward way to inspect the ranked verse list without adding a permanent
settings panel or changing the ranking engine.

### Actions must describe their scope

- `Copy matched passages` includes all selected runs, preserving verse boundaries,
  gap separators and exact references. It does not imply continuous quotation.
- Existing one-verse bookmark, similar-verse, and trail actions remain verse-specific
  and identify their target reference. Do not silently represent a single-verse
  bookmark as a saved passage collection.
- A passage shortcut only navigates; it does not secretly change the scope of the
  group copy action. A separate verse menu continues to act on its own verse.
- Saving complete collections to Study, sharing collection deep links, and running
  Similar verses over a collection need further persistence/retrieval design. Defer
  them instead of attaching misleading behavior to current single-verse APIs.

## Implementation sequence

1. **Exact citations and collection state.** Add gap-aware range formatting and copy
   formatting. Introduce the minimal shared selection representation. Preserve
   existing single-verse/reference callers and source verse IDs.
2. **Fix the existing multi-verse navigation defect.** Carry existing adjacent groups
   through desktop preview, mobile opening and full reader. Separate rank anchor
   from reading entry point; mark every matched verse and make explicit jumps stable.
3. **Add conservative separated-run grouping and compact cards.** Preserve final
   ranks/provenance, settle the neighborhood policy against representative queries,
   add passage shortcuts/expansion and the per-search ungrouped view. Keep engine
   scoring and candidate budgets unchanged.
4. **Finish the reading flow and verify.** Add passage stepping, accurate action
   labels and return-to-results restoration. Check keyboard, screen-reader, contrast,
   large-text and narrow-screen behavior; simplify any controls that compete.

## Acceptance checks

- Exact matches `{3,4,11,13,14,15,16,17}` format as `12:3–4, 11, 13–17`; neither
  citation nor copied text falsely includes verses 5–10 or 12.
- Anchor 17 in run 13–17 preserves rank but opens at 13; all eight members are marked
  in the group example. Tapping 11 focuses that run and preserves the full group.
- Weak distant hits and hits across book/chapter boundaries remain separate. Ties,
  duplicate IDs, focus-off/failure, and a partially reranked result set behave
  deterministically with no lost or duplicated hits.
- The main card, desktop preview and full reader agree on the exact citation and
  copy scope. Single-verse results, bookmarks and explicit references still work.
- Manual reading scroll is not undone by rebuilds; saved highlights remain intact;
  a different query/chapter cannot inherit stale group markers.
- Returning from the reader restores the selected card and search scroll position.
  Collapsing/expanding or switching grouped/individual view does not lose matches.
- A long chapter with many hits does not produce an enormous default card. Counts
  distinguish hits from groups, and truncation is still disclosed.
- Verify desktop split view and phone layouts, large text, keyboard and screen reader
  navigation, and multiple reading themes. No additional model calls are introduced.

## Deliberately deferred

No generated theological summaries, inferred narrative headings, cross-chapter
automatic merging, similarity percentages, or chapter-length background reranking.
The first version should excel at accurate grouping, smooth navigation and faithful
context before adding new interpretation or storage features.


## Implementation review (2026-10-25)

- Added one immutable `PassageSelection` for exact members, canonical runs, ranking
  anchor, and active run. Reader jumps use a navigation revision, so unrelated
  rebuilds do not move the reading position. Return synchronization only accepts
  the same current collection; regrouping cannot restore an obsolete collection.
- Grouping uses ten final rank positions including the anchor, never chains through
  later members, and never crosses the successful reranking boundary. Exact phrase
  results retain adjacent-only grouping. No engine changes or extra model calls.
- Cards remain compact by default, with explicitly labelled excerpts, passage
  shortcuts, expansion, separate match/result counts, and reversible individual
  display. Shortcuts scroll horizontally on constrained widths.
- Preview and reader outline every matched verse, use a stronger outline for the
  active run, and retain saved highlights. Copying includes all runs with exact
  references, numbered verses, and explicit omission separators. Single-verse
  bookmark, similar, and trail actions name their reference.
- Retained the existing chapter-column rendering approach. Chapters are bounded,
  and direct widget targets permit reliable jumps with variable text heights;
  no extra scrolling package or chapter-index machinery was introduced.

### Rank-window review

Reviewed the supplied Revelation fixture and four cached query rankings from
`local-benchmarks/reranker-stage2/rankings.json`, mapping verse IDs through the
installed catalog. These historical rankings validate presentation behavior; they
are not a new benchmark of the current production model.

| Query | Outcome with a ten-position anchor window |
| --- | --- |
| What is faith? | Hebrews 11:1, 6 at ranks 1/3 group; Ether 12:11 and 16 at ranks 4/20 remain separate. |
| What is the Atonement of Jesus Christ? | Jacob 4:11 and 12 at ranks 1/14 remain separate despite adjacency. Leviticus 16:16, 30 at ranks 17/18 group. |
| What is repentance and how do I repent? | Doctrine and Covenants 33:10-11 at ranks 9/11 group; Mormon 7:8 and 3 at ranks 4/18 remain separate. |
| I took something that was not mine. What should I do to put it right? | Mosiah 4:22, 28 at ranks 5/12 group; other chapter anchors retain their relative order. |

The policy bounds promotion by rank; it does not claim that rank proximity proves
semantic equivalence. The individual-results option exposes the underlying order.

### Validation

- Unit coverage includes the exact Revelation citation and run-entry behavior,
  nontransitive rank boundaries, deduplication, cross-chapter separation, partial
  reranking, phrase behavior, gap-preserving copy, and navigation reset.
- Widget coverage includes desktop and phone opening, all-member semantics, saved
  highlights/bookmarks, complete copy scope, passage jumps, expansion, display
  toggles, stale-state prevention, manual reader scroll, result scroll restoration,
  large reading text, and paper/sepia/night/high-contrast themes.
- Updated existing ranking tests to use the individual-results view and range
  expectations to include the complete preview citation.
- Rendered and inspected the supplied Revelation example with installed scripture
  content in desktop split view and the phone reader. Test renders check layout;
  they do not substitute for a packaged Windows/Android device smoke test.
- Targeted analysis of all ten changed Dart files: no issues. Repository-wide
  analysis also reports four pre-existing findings in unchanged tests (one const
  suggestion and three unused variables).
- Final complete Flutter suite: **362 passed, 46 skipped, zero failures**.
  The skipped checks require unavailable external models, staged hosting, or other
  integration prerequisites. Desktop/phone render smoke test also passed.
- No packaged installers or store/release assets were built or published in this
  implementation step.
