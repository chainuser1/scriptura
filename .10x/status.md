# Project status

## Feature: merge-adjacent-verses
**Phase:** Complete (small fix -- implementation + QA, scaled down per the
skill's "small fix" rules: no CTO/PM/full-architect ceremony needed for a
display-only grouping change with no new infra/security/deploy surface).

- [x] Design (ADR-001 written, `.10x/adrs/001-merge-adjacent-verse-results.md`)
- [x] Implementation (`lib/features/search/search_screen.dart`)
- [x] Tests (5 new, all passing; 4 pre-existing tests fixed for a real
      fixture-data interaction the new feature correctly exposed)
- [x] Full suite green: 293 passed, 0 failed

## Feature: segment-level-retrieval-study-reader
**Phase:** Design only (explicitly NOT implemented tonight -- see
`.10x/specs/2026-10-23-segment-retrieval-study-reader-design.md`). This is
a real architecture change against a mature, rigorously-evaluated retrieval
system (`docs/RETRIEVAL_V2_RESULTS.md`); the owner's own prior research
already flags "no new method ships to the phone without a measured
relevance gain" -- this spec is written to be evaluated against that bar
before any implementation starts, not built blind under tonight's time
pressure.
