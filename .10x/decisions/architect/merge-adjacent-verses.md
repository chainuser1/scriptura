# Architect: merge-adjacent-verses

## Problem
Search results are per-verse (`Passage` = exactly one verse, confirmed in
`lib/data/content/content_repository.dart`). When two or more verses that are
canonically adjacent (same book+chapter, consecutive `verse` numbers) both
rank highly for a query, they show as separate, disconnected list entries
instead of reading as one passage (e.g. "Proverbs 3:5" and "Proverbs 3:6"
instead of "Proverbs 3:5-6").

## Decision
Pure display-layer grouping in `search_screen.dart`, after `_resolve()` /
`app.focus()` have produced the final, already-ranked `_passages` list. No
change to retrieval, ranking, the `Passage` model, the content DB, or the
Rust engine.

**Adjacency rule:** two passages merge into one displayed group when
`a.bookId == b.bookId && a.chapter == b.chapter && (a.verse - b.verse).abs() == 1`.
`verseId` is a global sequential ID across the whole canon (confirmed), so a
raw `verseId` diff of 1 is not sufficient on its own at a book/chapter
boundary (verse 31 of ch. N, verse 1 of ch. N+1 are numerically adjacent
`verseId`s but not the same passage) -- the explicit `bookId`+`chapter` check
guards that.

**Order-independence:** `_passages` is rank-ordered (by Ezra/Apollos rerank
or base engine score), NOT canonical-order. Two adjacent verses are not
necessarily adjacent *in the list*. The grouping pass must scan the full
reranked list, union-find style or simple pairwise adjacency check across
all pairs present, then render each resulting group at the position of its
highest-ranked (first-occurring in `_passages`) member -- never reorder the
list, never introduce a verse that wasn't already a hit in its own right.
A chain of 3+ (e.g. verses 5, 6, 7 of the same chapter, all independently
ranked) merges into one "5-7" group, not two overlapping pairs.

**Group data shape:** a small new helper type (NOT a new model class touching
the content DB), e.g. `_ResultGroup { List<Passage> passages; }` computed
locally in `search_screen.dart` from `_passages`, with `.reference` combining
to a range string (book + chapter + first "-" last verse number) and
`.text` joining each passage's text (same style as the existing single-verse
subtitle, newline or space joined per member).

**Per-group actions (open/similar/trail/copy/bookmark):** target the group's
FIRST member (highest-ranked, which is also always the lowest verse number
in a merged range given how ranges form) -- i.e. exactly today's single-
`Passage` action, just on `group.passages.first`. No new multi-verse action
semantics invented. `startTrail`'s `extraSeeds` (built from `_passages.take(3)`)
stays on the underlying ungrouped `_passages` list, unaffected.

## Alternatives considered
| Alternative | Why not |
|---|---|
| Do the merge in the Rust engine / SearchResponse | Would require teaching the engine a new "grouped hit" wire shape and touch `Hit`/scoring code for a pure display concern -- violates "no retrieval/ranking changes" scope the owner explicitly asked for tonight. |
| Merge in `ContentRepository.getPassage` | Wrong layer -- `getPassage` is "give me verse X", used by many callers (reader screens, trails, bookmarks) that must keep getting single verses. Grouping is a *results-list* presentation concern only. |
| New `PassageGroup` model shared across the app | Overkill for one screen's one list. `_ResultGroup` stays local/private to `search_screen.dart` until (if ever) another screen needs the same grouping. |

## Risks
- A user could see "Proverbs 3:5-6" but tapping "Read in context" opens at
  3:5 (not a range view) -- acceptable for tonight's scope (the reader
  screen already shows surrounding verses once opened); flagged as a
  natural seed for the Problem-B study-reader design, not solved here.
- `_snippet`'s phrase-highlighting (exact-phrase mode) only highlights within
  a single passage's text today; for a merged group it should run per-member
  text, not one concatenated string, so the existing highlight-position
  logic still works unmodified per verse.
