# Scope profiles ("volume signals off across the canon, on inside their volume") Implementation Plan

> **Superseded** by `2026-10-14-volume-balance.md`: judged, not adopted, code removed.

> **For agentic workers:** execute task by task with test-first steps (superpowers:executing-plans). Keep the ledger at
> `.superpowers/sdd/2026-10-14-scope-profiles/progress.md`.

**Goal:** genes that mostly belong to one volume (Hebrew poetry and period genes to the Old Testament, Koine Greek and
Hellenistic-era genes to the New Testament, "voice of the Lord" to the Doctrine and Covenants, the Restoration period to the
modern volumes) must not steer results **across the canon**, and must **switch on** when the reader narrows the scope to that
volume. This applies to Similar verses, Trails **and meaning search** (the genome lane). The owner decides, by judging blind
sheets, whether it becomes the default.

**Revision note:** replaces the first plan (graded gene weights + book averages). The owner's design is simpler to explain and
matches how people think about scope; it was measured on the same proxies and works as well (see Evidence).

## Design (what the engine does)

Every gene has a **volume pull** = the share of its variance explained by which volume a verse is in (eta2, from the raw,
unweighted genome). Genes at or above a threshold `tau` are **volume signals**. Family Q (period and language) are volume
signals by nature: Koine Greek fires 5.3x its fair share in the New Testament, Restoration period 3.9x in the three modern
volumes, classical Hebrew is Old Testament only.

**One rule covers every scope, including combinations.** The scope is the **set of volumes** its filter touches. A gene is muted
when it **tells those volumes apart**, that is, when its volume pull *measured only inside the chosen volumes* is at or above
`tau`. With one volume nothing tells volumes apart, so nothing is muted. Family Q wakes up (weight 1) in any scope narrower
than the whole canon, unless it tells the chosen volumes apart.

| Scope (from the request's `filter`) | Genes muted at `tau` 0.03 | Notes |
|---|---|---|
| all five volumes, or no filter | 85 (+ Q stays off, as today) | volume signals of every volume, doctrinal, salvific and emotional protected |
| Old + New Testament ("Bible") | 35 | Hebrew and Greek, period genes |
| Old Testament + Book of Mormon | about 60 | Hebrew genes, Restoration period, covenant type |
| Old + New + Book of Mormon | about 80 | |
| Book of Mormon + D&C + Pearl of Great Price | about 85 | Q09 (Restoration) stays on: it is shared |
| one volume, one book, one chapter | 0 | family Q on |

Masks are computed per set of volumes (at most 31 sets) the first time a set is used and cached.

**Protected families.** The genes of the doctrinal (R), salvific (S) and emotional (D) families are never muted, even when they
lean toward a volume (13 doctrinal genes would otherwise be muted across the canon). The owner can change this list in the
overrides file. Measured across the canon: same-volume 0.623 (nothing protected) vs 0.641 (R, S, D protected); topical
agreement 0.0618 vs 0.0624.

Because rows are stored family-weighted and unit length, no new per-verse matrix is needed:

```
mask m (0/1 per gene, per profile), query q (unit, in the weighted gene space)
cos'(q, r) = ( v_r · (m ⊙ q) [+ Qtab_r · q_Q  in the volume profile] ) / ( |m ⊙ v_r| [or sqrt(1+|Qtab_r|^2)] · |m ⊙ q| )
```

`|m ⊙ v_r|` is precomputed once per profile at load (one pass over 42k rows). The only new data is the family Q table:
21 genes x 41,995 verses in half precision (1.8 MB), computed from `genome_vectors.f16.npy`, divided by each row's own
weighting norm so it lives in the same scale as the stored rows, and **embedded in the engine library**. No pack changes,
no re-upload.

**No switch for the user.** The scope menu already says **Across the canon**; choosing a scope is what selects the profile.
Whether the profiles are active is an engine configuration key `scope_profiles` (`false` until the owner has judged the
sheets, then set to the decision, per scope). A hidden request field `scope_profile` (`"raw"` | `"auto"`) exists only so the
review sheets and tests can ask for either behaviour; the app UI never sets it.
Search (`search`, `semantic`) applies the profile to the genome lane only: the predicted question genome is masked the same way
(and its Q part kept in the `volume` profile); Echo, Spark and Thread are untouched. Trails keep family energy for taste and
exploration on the raw rows.

## Evidence (proxies on 300 random verses; chance for same-volume is 37%)

| Across the canon | same book | same volume | topical agreement |
|---|---|---|---|
| today | 44% | 75% | 0.068 |
| mask volume signals, tau 0.08 (27 genes) | 42% | 73% | 0.070 |
| mask volume signals, tau 0.05 (52 genes) | 40% | 71% | 0.068 |
| mask volume signals, tau 0.03 (104 genes) | **37%** | **67%** | 0.067 |

Inside one volume, switching the volume's own signals on changes the neighbours toward the same era and genre (Old Testament
same-book 54% to 57-59%) and leaves topical agreement flat. That is the intended effect; whether it is **better** is for the
owner to judge. Default `tau` = 0.03; the table lets the owner pin any gene.

## Global constraints

- No gene family is removed from the model; the masks are a retrieval rule at query time.
- With `scope_profiles` false (the default) every response is unchanged (existing goldens must still pass).
- Deterministic; ties by ascending verse id; Rust ids equal the Python reference ids on every golden (scores within 1e-5).
- Speed within today's budgets (similar and trail 50 ms desktop, 100 ms phone; meaning search no more than +5%).
- Memory: no new per-verse float matrix; six norm vectors (about 1 MB) and the 1.8 MB Q table.
- Nothing user-visible is added: no setting, no switch. Behaviour follows the scope menu once the owner approves it.

## File structure

| File | Responsibility |
|---|---|
| `tool/make_scope_profile.py` | volume pull per gene, volume signals at `tau`, Q table; writes `engine/data/scope_profile.json`, `engine/data/scope_q.f16.bin`, and `local-benchmarks/scope-profile-table.md` |
| `engine/data/scope_overrides.json` | owner pins: `{"gene_id": "on" or "off"}`; empty by default |
| `tool/scope_profile.py` | dense Python reference (explicit masked matrices) |
| `test/scope_profile_check.py` | properties |
| `tool/make_scope_goldens.py`, `test/golden/scope.json` | similar, trail and search cases with reference answers |
| `engine/src/scope.rs` | profiles, norms, Q table, profile choice from a filter, masked scoring |
| `engine/src/search.rs`, `engine.rs`, `trails.rs` | `scope_profiles` config key and hidden `scope_profile` request field on `similar`, `trail_next`, `search`, `semantic`; identity includes the profile hash |
| `tool/scope_review_sheet.py` | blind A/B sheets: `local-benchmarks/scope-review-similar.html` and `scope-review-search.html`, keys beside them, scorer |

## Tasks

### Task 1: Generator, embedded data, visible table
- [ ] Failing test first (`test/scope_profile_check.py`): 568 genes classified; every family Q gene is a volume signal; masks
  contain no gene with volume pull below `tau`; the Q table has shape (41995, 21), finite, and non-negative; regenerating gives
  identical bytes; an override changes exactly its gene; verse ranges of the five volumes cover 1..41,995 without a gap.
- [ ] Implement the generator (volumes by the fixed verse-id ranges used everywhere else; home volume = highest share/n).
- [ ] The table lists gene, family, home volume, volume pull, mask yes/no, sorted by pull, so the owner can read and pin.
- [ ] Commit.

### Task 2: Python reference and goldens
- [ ] Failing properties: `scope_profile: raw` equals today's neighbours; `canon` lowers the same-volume rate by at least 4 points on
  200 verses and does not lower topical agreement by more than 0.003; `volume` never returns a verse outside the filter;
  masked genes have exactly zero influence (perturbing them changes no ranking); in `volume` the Q table changes rankings.
- [ ] Implement dense masked matrices, `similar`, trail vectors, and genome-lane scores for a predicted question genome.
- [ ] Goldens: 10 verses x (off, canon, OT, NT, BoM) for similar; 6 trails; 12 search queries with the genome lane masked.
- [ ] Commit.

### Task 3: Engine
- [ ] Failing tests in `engine/tests/engine_e2e.rs`: `scope_matches_python_goldens`, `scope_profiles_off_is_unchanged` (all existing
  goldens), `scope_profile_unknown_value_is_invalid_input`, `scope_disabled_on_layout_mismatch`.
- [ ] Implement `scope.rs` and wire it (`similar_with_topics`, `similar`, `trail_next`, `search`).
- [ ] Speed tests for similar, trail and search with `scope_profile: auto`.
- [ ] Commit.

### Task 4: Order of work: sheets before the engine
- [ ] Tasks 1, 2 and 5 are done **first**, so the owner can judge from the Python reference **before** any Rust is written.
- [ ] Only if a scope passes the decision rule do Task 3 and the config flip happen for that scope.
- [ ] No Dart or UI change at all.

### Task 5: Blind review sheets
- [ ] `tool/scope_review_sheet.py`: sheet 1, 60 verses (12 per volume) A/B lists for similar verses in **Across the canon**;
  sheet 2, 40 questions, A/B lists in Across the canon, 20 more inside Old Testament only and 20 inside New Testament only.
  A and B randomised, key saved apart, marks: A better / B better / same.
- [ ] Judgments are downloaded as `scope-judgments-similar.json` and `scope-judgments-search.json`; score with
  `.venv\Scripts\python.exe -I tool/scope_review_sheet.py --score FILE`: win share among decided pairs with a 95% Wilson interval,
  per sheet and per scope, and a plain sentence.
- [ ] **Decision rule (fixed now):** a scope's scoped behaviour becomes the default only if it wins at least 60% of the decided
  pairs and the lower bound is above 50%; otherwise it stays an opt-in switch for that scope.
- [ ] Commit.

### Task 6: Close-out
- [ ] `flutter analyze`, `flutter test`, Python checks, `cargo test --release`; Windows, installer, arm64 APK.
- [ ] DEVLOG and EXPERIENCE; report to the owner with the sheet paths and the gene table.

## Review focus

1. A filter spanning two volumes (Old plus New Testament): `canon`, never `volume`.
2. A filter inside one volume but only a few verses: the masked or scoped vector may be zero for some rows; fall back to the
   plain cosine, never divide by zero.
3. A request with `scope_profile: auto` and a verse that has no Q row: treated as zeros.
4. The verse layout differs from the embedded table: profile disabled, answers as `off`, and `info` says so.
5. Trails: `family_weights` identical with and without scope profiles.
6. Search: a person or reference question (handled before the genome lane) is unchanged.
