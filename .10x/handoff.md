# Handoff

## merge-adjacent-verses: done, shipped-ready
Implementation complete and tested. Nothing further needed from any other
role before this can be committed/released. No migration, no new deploy
surface, no new permission/security surface (pure client-side display
grouping of data already being shown).

## segment-level-retrieval-study-reader: design handed to the owner
The design doc at `.10x/specs/2026-10-23-segment-retrieval-study-reader-design.md`
is the next thing to review. It is NOT ready for implementation -- it
explicitly recommends an evaluation step (measuring segment-retrieval
quality against the existing 36-question holdout from `docs/RETRIEVAL_V2_RESULTS.md`)
before any code gets written, matching that research's own stated bar for
shipping new retrieval methods. Whoever picks this up next should start by
reading that doc's "Evaluation gate" section, not by writing code.
