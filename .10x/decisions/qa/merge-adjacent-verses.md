# QA: merge-adjacent-verses

## Test strategy
Widget-level tests against the real `search_screen.dart` rendering path,
using the existing fixture content DB (`test/fixtures/content_v2_mini.db`)
rather than mocks, so grouping logic runs against real `Passage` data with
real `bookId`/`chapter`/`verse` values.

## Coverage
- Pair merge (verses 1-2, same chapter) -> one "Alpha Book 1:1–2" card.
- Chain-of-3 merge (verses 1-2-3) -> one "Alpha Book 1:1–3" card.
- Chapter-boundary non-merge (verse 3 end-of-ch.1, verse 4 start-of-ch.2;
  numerically adjacent verseIds but different chapters) -> stay separate.
- Order-independence: hits arrive as `[2, 6, 1]` (not in canonical order) ->
  1 and 2 still merge correctly regardless of their position in the ranked
  list.
- Action correctness: tapping a merged group's `ValueKey('hit-<anchor>')`
  opens the reader at the group's actual anchor verse.

## Regression found and fixed
Four pre-existing "Answer focus" tests broke because their fixture verse
set `[2, 5, 6, 7]` happened to include two canonically adjacent verses (6,
7) that the new merge logic correctly merges -- collapsing what those tests
assumed were 4 independently-positioned list items into 3. This was a
genuine interaction the tests had never been exercised against, not a false
positive: the fix was to change the fixture data each test uses (swap verse
7 for verse 8, not adjacent to 6), not to special-case the merge logic for
answer-focus-chosen results. Verified no other test in the suite depends on
verses 6/7's specific adjacency or any other adjacent pair in the fixture.

## Quality gate
Full suite run clean: 293 passed (3 pre-existing skips unrelated to this
feature), 0 failures, after the fixture-id fix above.

## Not covered (explicitly out of scope for this fix)
- No test exercises a 3-way interaction of merge + Answer Focus reordering
  landing exactly on an adjacent pair inside the reordered top-K (the fix
  above specifically avoided this combination by using non-adjacent IDs).
  If Answer Focus's own candidate set naturally contains adjacent verses in
  real usage, the merge still applies correctly by construction (it runs on
  whatever `_passages` holds, post-reorder) -- just not independently proven
  by a dedicated test. Low risk: the merge function only reads already-
  resolved `Passage` fields, has no awareness of Answer Focus history, and
  is covered for the order-independence case already.
