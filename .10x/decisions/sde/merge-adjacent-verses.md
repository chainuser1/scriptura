# SDE: merge-adjacent-verses

## What was built
`lib/features/search/search_screen.dart`:
- `_groupAdjacent(List<Passage>)`: groups canonically adjacent verses (same
  `bookId`+`chapter`, consecutive `verse` numbers) from the already-ranked
  `_passages` list into `_Group`s. Scans all pairs (not just list-neighbors)
  since reranking can separate canonically adjacent verses in display order.
  Returns groups in canonical (verse-number) order for display, plus the
  group's `anchor` (the actually-highest-ranked member, which is not
  guaranteed to be the lowest verse number).
- `_Group` (new tiny private class): `passages` (canonical order) + `anchor`.
- `_results()`'s render loop now iterates `_groupAdjacent(_passages)` instead
  of `_passages` directly. Reused `citationFor()` (already existed in
  `lib/app/verse_tools.dart`, built for the reader's multi-verse selection)
  for the merged range reference string -- no new formatting code written.
  `formatForCopy(group.passages)` for "Copy with reference" now copies the
  whole range's text, not just the anchor's.
- Snippet rendering: `Column` of one `_snippet(...)` call per group member
  (not one call on a concatenated string), so exact-phrase highlighting
  still finds its match position correctly per-verse.

## Deviations from plan
None of substance. The ADR's claim that the anchor "is always the lowest
verse number in a merged range" was wrong and caught during implementation
(a later verse in a range can outrank an earlier one) -- fixed by having
`_groupAdjacent` return the real anchor separately from canonical display
order, rather than assuming `group.first` is always both.

## Tech debt / follow-ups
None created. This is intentionally the full, final implementation for
Problem A -- no "merge later" deferred pieces.

## Test changes required by this feature
`test/widget_test.dart`'s pre-existing "Answer focus" test group used
fixture verse IDs `[2, 5, 6, 7]` -- verses 6 and 7 are canonically adjacent
in the fixture DB (`Beta Book 1:1` / `1:2`), so they now correctly merge
into one card, breaking those tests' `ValueKey('hit-6')` / `ValueKey('hit-7')`
assumptions (4 independently-addressable list positions). Swapped `7` -> `8`
(not adjacent to 6) throughout that test group and two related tests outside
it, preserving each test's actual intent (verifying rerank order) without
weakening the new merge behavior. 5 new tests added for the merge behavior
itself (merge pair, merge chain-of-3, no-merge across chapter boundary,
merge independent of list order, action targets the real anchor).
