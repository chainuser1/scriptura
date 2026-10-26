# Chapter search results and reading context

Status: implemented and verified with the user-confirmed chapter grouping rule.

## Confirmed behavior

After retrieval and Answer Focus finish, put **every returned match from the same
book and chapter into one card**, regardless of rank distance or whether Answer
Focus evaluated that particular hit. Different chapters always have different
cards. This supersedes the original ten-position window and reranking boundary.

For example, Revelation 12:7 joins Revelation 12:3-4, 13-17 even when it appears
much farther down the ranked list. Revelation 17:18 remains in a separate card.
Only returned verses belong to the match set; do not invent matches in the gaps.

Each chapter card keeps the position of its strongest returned match. The passage
containing that match has the checkmark **by default**, and the reader opens at the
start of that passage. Clicking another passage moves the checkmark and reader.
The checkmark describes the current selection, not a permanent best-match badge.

## Ranking and presentation

- Group after final ranking, including any successful Answer Focus reranking.
  The first occurrence of each chapter determines its card position and anchor.
- Do not compare retrieval scores with reranker scores. Preserve the final order
  supplied by the existing ranking pipeline; grouping changes presentation only.
- Deduplicate verse IDs, then organize all chapter members into canonical runs.
  Every returned verse appears exactly once, including the unevaluated tail.
- Meaning, similar-verse, and exact-phrase results use the same chapter grouping.
  Explicit reference navigation retains its existing behavior.
- `Show matches separately` restores the ranked verse list without another model
  call. Counts distinguish verse matches from result cards; truncation stays visible.
- Do not change candidate counts, ranking models, or inference budgets.

## One collection across the UI

`PassageSelection` carries exact members, canonical runs, ranking anchor, and the
active run. The ranking anchor remains fixed when the active passage changes.

- A card, desktop preview, and full reader show the same exact citation.
- If verse 17 is strongest within 13-17, open at 13 and check the 13-17 shortcut.
- Mark all matched verses; use a stronger marker for the active run. Unmatched
  verses remain ordinary readable context, and saved highlights remain intact.
- Scroll only when opening or explicitly jumping to a passage. A navigation
  revision prevents preference changes and other rebuilds from snapping back.
- A new query or chapter clears stale group context. Returning to results preserves
  the card, active passage, expansion state, and result scroll position.
- Returning from the reader must not restore an obsolete collection after the user
  has switched the grouped/individual display.

## Cards and passage controls

Collapsed cards show the exact citation, passage/match counts, a bounded excerpt
from the anchor passage, and passage shortcuts. Label the excerpt with its range.
Expanded cards show numbered verses and explicit gaps between runs.

Passage shortcuts scroll horizontally on narrow surfaces. Preview and reader offer
previous/next passage controls and position text. Their checkmark follows the
active passage, initially the anchor's run.

Use opaque chip fills derived from the app accent and actual reading surface.
Selected chips use the app primary/on-primary pair, including their checkmark.
The surrounding dark app theme must not force a dark chip background behind the
light reading page's dark text. Keep labels and checkmarks legible in both light
and dark reading themes; explicitly show the selected checkmark.

The existing bounded chapter-column rendering remains sufficient for direct jumps
with variable text heights. No new scrolling dependency is needed.

## Actions and scope

- `Copy matched passages` copies all exact runs with references, numbered verses,
  and omission separators. Changing the active shortcut does not narrow copy scope.
- Single-verse bookmark, similar, and trail actions name their anchor reference.
  Individual verse menus continue to act on their own verse.
- Do not imply that a single-verse bookmark saves the whole chapter collection.

## Acceptance checks

1. All returned Revelation 12 verses share one card, including a hit beyond the old
   ten-position cutoff. Revelation 17:18 and other books remain separate.
2. A partially reranked set still has one card per chapter; every unique hit appears
   once, and card order follows the first occurrence of each chapter in final ranks.
3. Answer Focus's strongest passage is checked initially even when it comes later
   in scripture order. Clicking another passage moves the checkmark and reader
   without altering the anchor, card rank, match set, or making another model call.
4. Discontinuous matches retain exact citations and copied gaps. Adjacent members
   form display runs without swallowing unmatched verses.
5. Desktop and phone navigation carry the full selection. Saved highlights,
   bookmarks, manual reader scroll, expansion, and search scroll remain intact.
6. Chip colors override a conflicting inherited app chip theme, are opaque against
   the reading surface, and preserve at least 4.5:1 label contrast for paper/night.
7. Grouped and separate display remain reversible; explicit references and new-query
   cancellation/error behavior continue to work.

## Validation record

The original implementation passed 362 tests with 46 environment-dependent skips.
This refinement replaces tests that enforced the superseded rank window/boundary,
adds an Answer Focus default-selection regression, and adds a conflicting-theme
chip contrast regression.

- Targeted grouping, navigation, search-screen, search-scroll, and existing widget
  tests: **71 passed, zero failures**.
- Analysis of all seven changed/new Dart implementation and test files: no issues.
- Windows trial installer built: **1.0.9 (build 10)**. Verified the installer and
  application version metadata and bundled native runtime files.

## Deferred

No generated theological summaries, cross-chapter automatic merging, similarity
percentages, whole-collection bookmarks, collection deep links, or model changes.


## Selection theme refinement

Preview and reader selection now share the app accent: a soft tinted background,
a thinner accent outline, and a solid accent on the selected passage chip. The
active run retains stronger emphasis. Saved highlight colors take priority over
the temporary tint; chapter context remains on the chosen reading surface.

`PassageColors` adapts the accent marker toward the page ink only when needed to
keep it visible on an independently chosen light or dark reading page. This avoids
hard-coded gray outlines and preserves each app theme's accent.

Validation includes all app styles, both brightness settings, and every reading
surface: selected-chip text and verse text retain 4.5:1 contrast, and selection
markers retain 3:1 against the page. Windows trial build: 1.0.10 (build 11).


Theme refinement verification: 21 targeted checks passed, including desktop and
phone render inspection; analysis of all five affected Dart files passed. Built
the Windows installer and verified version 1.0.10, app build 1.0.10+11, and the
bundled runtime files. No release was published.
