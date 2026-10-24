# ADR-001: Merge adjacent verse search results at display time only

**Status:** Accepted
**Date:** 2026-10-23
**Feature:** merge-adjacent-verses
**Author:** 10x-Team (Architect + Staff Engineer)

## Context
Search results are per-verse. Two canonically adjacent verses that both
rank highly for a query (e.g. Proverbs 3:5 and 3:6) show as two separate,
disconnected list entries instead of reading as one passage. The app's
retrieval/ranking layer (Compass scoring, Ezra/Apollos rerank; see
`docs/RETRIEVAL_V2_RESULTS.md`) is mature and rigorously evaluated --
changing it carries real risk and is out of scope for a same-night fix.

## Decision
Group adjacent verses into one displayed result card, purely in
`lib/features/search/search_screen.dart`'s results-rendering path, computed
from the already-ranked `_passages` list. No changes to `Passage`, the
content DB, the Rust engine, or any ranking/scoring code.

## Alternatives Considered
| Alternative | Pros | Cons | Why Not |
|---|---|---|---|
| Engine-level grouped hits | Single source of truth for grouping | Touches scoring/`Hit` wire shape for a pure display concern; the retrieval layer is explicitly flagged in prior research as something new methods must prove before touching | Scope and risk mismatch for tonight |
| New shared `PassageGroup` model | Reusable if another screen needs it later | No second consumer exists yet; premature abstraction | YAGNI -- add when a second caller needs it |

## Consequences

### Positive
- Fixes the reported awkwardness with zero risk to retrieval/ranking quality.
- No new persisted data, no migration, no engine rebuild.

### Negative
- Per-group actions (open/similar/trail/bookmark) target only the group's
  first verse, not a true "view this whole range" experience -- a shallower
  fix than the full study-reader idea (tracked separately, ADR-002 scope).

### Risks
- Phrase-highlight snippet logic must run per-member text inside a group,
  not on a naively concatenated string, or exact-phrase mode's highlight
  position breaks for multi-verse groups. Mitigated by keeping `_snippet`
  called once per member inside the group's rendering, not once per group.

## Dependencies
- None. Does not block or require ADR-002 (segment-level retrieval).
