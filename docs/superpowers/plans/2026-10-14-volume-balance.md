# Volume balance ("no volume wins just for being itself") Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> Ledger: `.superpowers/sdd/2026-10-14-volume-balance/progress.md`.

**Goal:** when two or more volumes are in the scope, results for Similar verses, meaning search and Trails must not lean to one
volume only because of its style, language or era. Genes are never switched off. The fix is applied where the volumes compete.

**Architecture:** for each request and each lane, the engine computes each volume's **baseline** (the mean of that volume's best
scores for this verse or question). It subtracts a fraction (`strength`) of that baseline from the volume's scores before
candidates are picked. A volume that scores high everywhere loses that advantage. Real matches still rise above their own
volume. With one volume in scope nothing changes. The Python reference in `tool/volume_balance.py` is the authority, and the Rust
port in `engine/src/balance.rs` is pinned to it with goldens. The dormant scope-profile code is removed.

**Tech Stack:** Python 3 + numpy (reference, measurement), Rust engine (`engine/`), Flutter (`lib/services/engine/engine_pack.dart`).

**Spec:** the design approved in chat on 2026-10-14 ("offset at the output", reproduced under Design). The plan is the written
form of it. Rulings made without a separate spec file are recorded in the ledger.

## Report for the owner (simple English)

**What you will get.** Across the canon, and in any mix of volumes, the lists stop filling up with verses from one volume just
because that volume "sounds like" the verse you started from. Example from the test on the genome lane alone: today about 79
of every 100 similar verses come from the same volume. With half strength it was about 60, and the average similarity of the
results stayed almost the same (0.726 → 0.715). In the app the topic lane is fused in as well, and a first look at three
verses showed a much smaller change (two verses replaced in one list, small reorders in the others). Task 1 measures the
real, end-to-end effect, and the rule decides.

**What you will not see.** No new switch, no new setting, no screen change. Choosing "Across the canon" or several volumes in
the scope menu is enough. One volume, one book or one chapter works exactly as today.

**What is removed.** The scope-profile code that was parked (gene masks, family Q table, about 1.8 MB) is deleted. Nothing
stays dormant.

**What I need from you.** Nothing during the build. The settings are picked by fixed rules written below, before I measure.
At the end I make one blind sheet (40 similar items + 40 search items). Judging it is optional. If you judge it and the new
lists lose (less than 45% of the decided pairs), I switch the feature off and tell you.

**Risk.** Some leaning is real content (the Book of Mormon really talks about Nephites). That is why the strength is a fraction,
not a full removal, and why the rules forbid pushing any volume below its fair share.

## Design (what the engine does)

```
for one lane's score vector s over all verses, eligible rows E, volume of each row vol(r):
  P   = volumes with at least one eligible row
  if strength == 0 or |P| < 2: return s unchanged
  for k in P with n_k = |E ∩ volume k| >= MIN_ROWS:
      base_k = mean of the best ceil(TOP_FRAC * n_k) scores of volume k among E
  for k in P with n_k < MIN_ROWS: base_k = mean of the computed base_k   (small parts are not punished)
  if no base_k was computed: return s unchanged
  s'(r) = s(r) - strength * base_{vol(r)}
```

- **Where it is applied.** Similar verses: the genome lane and the topic lane, before candidates are picked. Meaning search:
  dense (Echo), sparse (Spark) and genome (Root) lanes, before the 200-per-lane candidate pick. Thread (ColBERT) scores only the
  candidates and is left alone. Trails: the taste cosine (`cos_t`), the pool cosine (`cos_p`) and topic overlap. Novelty,
  mood and the dislike check use raw cosines, as today.
- **Volumes** come from `engine/data/volumes.json` (five verse-id ranges, written from `catalog.db` by the reference tool,
  embedded in the engine and checked against the index at load. If they do not match, balance is off).
- **Strength.** The engine config key is `volume_balance` (number, default `0.0` = off, so every existing golden still holds).
  The app passes the chosen value. A hidden request field `volume_balance` (number 0..1) overrides it, for tests and sheets
  only. The UI never sets it.
- **Constants** `TOP_FRAC` and `MIN_ROWS` live in both `tool/volume_balance.py` and `engine/src/balance.rs`. Task 1 picks
  them and the strength by the rule below.

## Global Constraints

- No gene is muted, no family is singled out. The balance works on scores only.
- One volume in scope ⇒ results and scores identical to `volume_balance = 0`.
- `volume_balance = 0` ⇒ every existing golden (`fusion_*`, `topics_similar.json`, `trails.json`, entity cases) unchanged.
- No new Settings item. The app passes one config number.
- Commits carry no Co-Authored-By or other assistant attribution (owner's standing rule).
- Simple English in every owner-facing text.

## Decision rule (fixed before measuring)

Measured on 3,000 random source verses (seed 7) for Similar verses end to end (genome + topic lane, top 10), and on 300 seed
verses for the first Trails batch (k = 10):

1. same-volume share drops by **at least 8 points** versus today;
2. average raw genome similarity of the returned verses drops by **at most 2%**;
3. **no overshoot:** for every volume, its same-volume share stays at or above its size share (OT 55%, NT 19%, BoM 16%, D&C
   9%, PGP 1.5%);
4. **no flooding:** no volume's share of all returned verses rises above 1.5× its share today.

Grid: strength ∈ {0.25, 0.5, 0.75, 1.0} × TOP_FRAC ∈ {0.005, 0.01, 0.03, 0.10}, MIN_ROWS = 50. The passing setting with the
largest drop wins. Ties go to the lower strength. If nothing passes, stop and report to the owner. Do not loosen the rule.

Meaning search (Task 4) uses the engine: 200 questions from `review_sheet.load_queries`. Bias = average share of the top 10
held by the single most frequent volume. The same setting must lower it by ≥ 5 points and keep ≥ 60% of today's top 10. If
not, search gets its own strength from the same grid by the same rule, recorded in the ledger.

## Review Focus

- A filter that touches a volume by only a few verses (e.g. Malachi 4 + Matthew 1): the small part must not be pushed down
  (MIN_ROWS rule). Test in Task 1 and Task 3.
- A filter inside one book: scores identical to today. Test in Task 3.
- Empty filter result / unknown verse: same errors as today. Covered by existing e2e tests.
- Speed: one partial sort per volume per lane, under 1 ms per lane. The existing speed-budget test must still pass.
- Trails with a filter across two volumes: the dislike "near" check is unchanged. Golden case in Task 3.

---

### Task 1: Reference, measurement, settings

**Files:**
- Create: `tool/volume_balance.py` (primitive, `volumes.json` writer, `--measure`)
- Create: `engine/data/volumes.json`
- Create: `test/volume_balance_check.py`
- Modify: `tool/similar_verses.py` (`similar_with_topics(..., volume_balance=0.0)`), `tool/trails.py` (`trail_next` reads
  `req.get('volume_balance', 0.0)`)
- Output (gitignored): `local-benchmarks/volume-balance-report.md`

**Interfaces:**
- Produces: `balance(scores, vol, eligible, strength, top_frac=TOP_FRAC, min_rows=MIN_ROWS) -> np.ndarray`,
  `volume_of_rows(verse_ids) -> np.ndarray[int]`, constants `TOP_FRAC`, `MIN_ROWS`, `STRENGTH`.

- [ ] **Step 1: Write the failing check** `test/volume_balance_check.py`:

```python
import sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'tool'))
from volume_balance import balance  # noqa: E402

rng = np.random.default_rng(1)
vol = np.repeat([0, 1, 2], [300, 200, 100])
s = rng.random(600)
s[vol == 0] += 0.5                                     # volume 0 scores high everywhere
allr = np.ones(600, bool)
assert np.array_equal(balance(s, vol, allr, 0.0), s)                       # off = unchanged
one = vol == 1
assert np.array_equal(balance(s, vol, one, 0.5), s)                        # one volume = unchanged
b = balance(s, vol, allr, 0.5, top_frac=0.05, min_rows=50)
top = np.argsort(-b)[:30]
assert (vol[top] == 0).mean() < (vol[np.argsort(-s)[:30]] == 0).mean()     # the inflated volume loses share
small = allr.copy(); small[(vol == 2)] = False; small[np.flatnonzero(vol == 2)[:5]] = True
b2 = balance(s, vol, small, 0.5, top_frac=0.05, min_rows=50)
d = s - b2
assert abs(d[vol == 2][0] - np.mean([d[vol == 0][0], d[vol == 1][0]])) < 1e-12   # small part takes the mean offset
order0 = np.argsort(-s[vol == 0]); assert np.array_equal(order0, np.argsort(-b[vol == 0]))  # order inside a volume kept
print('volume balance check: ok')
```

- [ ] **Step 2: Run it.** `.venv\Scripts\python.exe -I test/volume_balance_check.py`. Expected: FAIL, `ModuleNotFoundError: volume_balance`.

- [ ] **Step 3: Write `tool/volume_balance.py`:**

```python
"""Volume balance reference (docs/superpowers/plans/2026-10-14-volume-balance.md). The engine port is engine/src/balance.rs.

  .venv\\Scripts\\python.exe -I tool/volume_balance.py --volumes     # write engine/data/volumes.json from catalog.db
  .venv\\Scripts\\python.exe -I tool/volume_balance.py --measure     # grid + decision rule -> local-benchmarks/volume-balance-report.md
"""
import json
import math
import sqlite3
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
VOLUMES = ROOT / 'engine' / 'data' / 'volumes.json'
VOLUME_KEYS = ['ot', 'nt', 'bom', 'dc', 'pgp']
TOP_FRAC = 0.03    # set by --measure (Task 1)
MIN_ROWS = 50
STRENGTH = 0.5     # set by --measure (Task 1); the app passes it as the engine config key volume_balance


def balance(scores, vol, eligible, strength, top_frac=TOP_FRAC, min_rows=MIN_ROWS):
    """Subtract strength x each volume's baseline (mean of its best ceil(top_frac * n) eligible scores) when two or more
    volumes have eligible rows. Volumes with fewer than min_rows eligible rows take the mean of the computed baselines."""
    out = np.asarray(scores, dtype=np.float64).copy()
    present = [k for k in np.unique(vol[eligible])]
    if strength <= 0 or len(present) < 2:
        return out
    base = {}
    for k in present:
        x = out[eligible & (vol == k)]
        if len(x) >= min_rows:
            n = max(1, math.ceil(top_frac * len(x)))
            base[k] = float(np.sort(x)[-n:].mean())
    if not base:
        return out
    fill = float(np.mean(list(base.values())))
    for k in present:
        out[vol == k] -= strength * base.get(k, fill)
    return out


def volume_ranges():
    c = sqlite3.connect(f'file:{(ROOT / "generated-artifacts/release/catalog.db").as_posix()}?mode=ro', uri=True)
    got = {k: (a, b) for k, a, b in c.execute('SELECT key, first_verse_id, last_verse_id FROM volumes')}
    return [{'key': k, 'first': got[k][0], 'last': got[k][1]} for k in VOLUME_KEYS]


def volume_of_rows(verse_ids):
    vols = json.loads(VOLUMES.read_text('utf-8'))['volumes']
    out = np.full(len(verse_ids), -1)
    for k, v in enumerate(vols):
        out[(verse_ids >= v['first']) & (verse_ids <= v['last'])] = k
    assert (out >= 0).all(), 'a verse outside every volume'
    return out
```

Then add `main()` with `--volumes` (writes `{"format": "volumes-v1", "volumes": volume_ranges()}`) and `--measure`. `--measure`
runs `SimilarVerses.similar_with_topics(v, 10, volume_balance=s)` and `Trails.trail_next({... 'seed': {'verse_id': v}, 'k': 10,
'volume_balance': s})` over the grid (setting the module's `TOP_FRAC` per run), applies the decision rule exactly as written
above, prints and writes the report table (setting, same-volume share, similarity change, per-volume share, flooding ratio,
pass/fail per rule), and prints the winner.

- [ ] **Step 4: Wire the reference.** In `tool/similar_verses.py` `similar_with_topics`, add `volume_balance=0.0`, and right
  after `g` and `t` are built:

```python
        if volume_balance:
            from volume_balance import balance, volume_of_rows
            vol = getattr(self, '_vol', None)
            if vol is None:
                vol = self._vol = volume_of_rows(self.verse_ids)
            g = balance(g, vol, ok, volume_balance)
            t = balance(t, vol, ok, volume_balance)
```

  In `tool/trails.py` `trail_next`, with `vb = float(req.get('volume_balance', 0.0))`, apply the same `balance` to `cos_t`,
  `cos_p` and `overlap` with the eligibility mask the pool uses (`allowed`), before the pool loop.

- [ ] **Step 5: Run the checks.** `test/volume_balance_check.py` → `volume balance check: ok`. `test/trails_reference_check.py`
  and the existing similar-verses golden check → unchanged (balance defaults to 0).

- [ ] **Step 6: Measure.** `python -I tool/volume_balance.py --volumes` then `--measure`. Expected: a winner that passes all
  four rules (the probe suggests strength 0.5). Write `TOP_FRAC`/`STRENGTH` into `tool/volume_balance.py`. Ledger the table's
  winning row. If nothing passes, STOP and report to the owner.

- [ ] **Step 7: Commit.** `git add tool/volume_balance.py engine/data/volumes.json test/volume_balance_check.py tool/similar_verses.py tool/trails.py`
  then `git commit -m "volume balance: reference, measurement and chosen settings"`.

### Task 2: Remove the scope-profile code

**Files:**
- Delete: `engine/src/scope.rs`, `engine/data/scope_profile.json`, `engine/data/scope_q.f16.bin`,
  `engine/data/scope_overrides.json`, `tool/make_scope_profile.py`, `tool/scope_profile.py`, `tool/make_scope_goldens.py`,
  `test/scope_profile_check.py`, `test/scope_reference_check.py`, `test/golden/scope.json`
- Rename: `tool/scope_review_sheet.py` → `tool/balance_review_sheet.py` (used in Task 5)
- Modify: `engine/src/lib.rs` (drop `pub mod scope;`), `engine/src/search.rs` (drop `search_scoped`, `query_genome_parts`,
  `predicted_genome_parts`; restore `search` and `query_genome` to the pre-scope bodies), `engine/src/engine.rs` (drop
  `scope`, `scope_default`, `scope_profiles` config key, `ranges`, `scope_for`, `genome_scores_scoped`, the scoped branch of
  `similar_op`, `"scope_profiles"` in capabilities), `engine/tests/engine_e2e.rs` (drop the three scope tests),
  `test/golden/engine_capabilities.json` if it lists `scope_profiles`.

- [ ] **Step 1:** `git show 9cfca2d --stat` to list what the scope engine commit added. Revert those hunks in `search.rs` and
  `engine.rs` by hand (do not `git revert`: later commits touch the same files). Delete the listed files with `git rm`.
- [ ] **Step 2:** `cd engine; cargo test --release 2>&1 | tail -20`. Expected: all pass, no `scope` symbol left
  (`git grep -n "scope_profile\|ScopeProfiles\|search_scoped"` → only DEVLOG / old plan lines).
- [ ] **Step 3: Commit.** `git commit -m "remove scope profiles (replaced by volume balance)"`.

### Task 3: Engine port

**Files:**
- Create: `engine/src/balance.rs`
- Modify: `engine/src/lib.rs`, `engine/src/engine.rs`, `engine/src/search.rs`, `engine/src/trails.rs`
- Create: `tool/make_balance_goldens.py`, `test/golden/volume_balance.json`
- Test: `engine/src/balance.rs` (unit), `engine/tests/engine_e2e.rs`

**Interfaces:**
- Consumes: `engine/data/volumes.json`, `TOP_FRAC`, `MIN_ROWS` from Task 1.
- Produces: `pub struct Volumes`, `Volumes::open_embedded(&Index) -> Option<Volumes>`,
  `Volumes::balance(&self, scores: &mut [f64], eligible: &dyn Fn(usize) -> bool, strength: f64)`.

- [ ] **Step 1: Failing unit tests** in `balance.rs` (`#[cfg(test)]`): the same five cases as `test/volume_balance_check.py`
  (off, one volume, inflated volume loses share, small part takes the mean offset, order inside a volume kept), built on a
  `Volumes { of_row }` made by hand.
- [ ] **Step 2:** `cargo test --release balance` → FAIL (module missing).
- [ ] **Step 3: Write `balance.rs`:**

```rust
//! Volume balance (docs/superpowers/plans/2026-10-14-volume-balance.md; reference: tool/volume_balance.py).
//! Each volume's baseline for this request (mean of its best TOP_FRAC eligible scores) is partly removed before volumes
//! compete, so no volume wins only for being itself. One volume in scope = no change.

use crate::search::Index;
use serde::Deserialize;

pub const TOP_FRAC: f64 = 0.03; // tool/volume_balance.py
pub const MIN_ROWS: usize = 50;
const VOLUMES_JSON: &str = include_str!("../data/volumes.json");

#[derive(Deserialize)]
struct Range { first: i64, last: i64 }
#[derive(Deserialize)]
struct File { volumes: Vec<Range> }

pub struct Volumes { of_row: Vec<u8>, count: usize }

impl Volumes {
    pub fn open_embedded(index: &Index) -> Option<Self> {
        let f: File = serde_json::from_str(VOLUMES_JSON).ok()?;
        let mut of_row = Vec::with_capacity(index.verse_ids.len());
        for &v in &index.verse_ids {
            of_row.push(f.volumes.iter().position(|r| r.first <= v && v <= r.last)? as u8);
        }
        Some(Self { of_row, count: f.volumes.len() })
    }

    pub fn balance(&self, s: &mut [f64], eligible: &dyn Fn(usize) -> bool, strength: f64) {
        if strength <= 0.0 { return; }
        let mut per: Vec<Vec<f64>> = vec![Vec::new(); self.count];
        for (r, &k) in self.of_row.iter().enumerate() {
            if eligible(r) { per[k as usize].push(s[r]); }
        }
        if per.iter().filter(|p| !p.is_empty()).count() < 2 { return; }
        let mut base: Vec<Option<f64>> = vec![None; self.count];
        for (k, p) in per.iter_mut().enumerate() {
            if p.len() >= MIN_ROWS {
                let n = ((TOP_FRAC * p.len() as f64).ceil() as usize).max(1);
                let cut = p.len() - n;
                p.select_nth_unstable_by(cut, |a, b| a.partial_cmp(b).unwrap());
                base[k] = Some(p[cut..].iter().sum::<f64>() / n as f64);
            }
        }
        let got: Vec<f64> = base.iter().flatten().copied().collect();
        if got.is_empty() { return; }
        let fill = got.iter().sum::<f64>() / got.len() as f64;
        let off: Vec<f64> = (0..self.count).map(|k| if per[k].is_empty() { 0.0 } else { strength * base[k].unwrap_or(fill) }).collect();
        for (r, &k) in self.of_row.iter().enumerate() { s[r] -= off[k as usize]; }
    }
}
```

- [ ] **Step 4: Wire it.** `engine.rs`: `Config.volume_balance: f64` with `#[serde(default)]`. The engine keeps
  `volumes: Option<Volumes>` and `balance_default: f64`. `fn strength(&self, req) -> Result<f64, Fail>` reads the request
  number (must be within 0..=1, else `invalid_input`), falling back to the default, and returns 0 when `volumes` is None.
  The capabilities field is `"volume_balance": self.volumes.is_some()`. Pass `Option<(&Volumes, f64)>` into:
  `similar_with_topics` (balance `g` and `tscore` with `ok`), the plain `similar` path (balance the `genome_scores` vector),
  `Index::search` (new last parameter; balance `da`, `sa`, `ga` with the eligibility mask before `lane`), and
  `trails::trail_next` (balance `cos_t`, `cos_p`, `overlap` with `allowed`). Include the strength in each response's
  configuration id only when it is > 0 (so ids stay the same when it is off).
- [ ] **Step 5: Goldens.** `tool/make_balance_goldens.py` writes `test/golden/volume_balance.json`: similar cases (10 verses
  × scopes {canon, bible, ot_bom, one book, Malachi 4 + Matthew 1}) and trails cases (5 seeds × {canon, bible}) at the chosen
  strength, from the Python reference. e2e tests:
  `volume_balance_matches_python_goldens` (5e-5 near-tie tolerance, as before);
  `volume_balance_off_and_one_volume_are_today` (strength 0 and a one-book filter give byte-identical hits to today);
  `volume_balance_rejects_bad_strength` (`1.5` and `"x"` → `invalid_input`).
- [ ] **Step 6:** `cargo test --release 2>&1 | tail -30` → all pass, including all old goldens and the speed budget.
- [ ] **Step 7: Commit.** `git commit -m "volume balance: engine port pinned to the reference goldens"`.

### Task 4: Meaning search check

**Files:** Create `tool/volume_balance_search.py`. Output `local-benchmarks/volume-balance-search.md`.

- [ ] **Step 1:** Using `review_sheet.Engine` (the ctypes wrapper, as in the old scope sheet), run 200 questions with profile
  `compass`, `volume_balance` 0 vs the chosen strength. Report the dominant-volume share, the share of today's top 10 kept, and
  the per-volume share of all hits.
- [ ] **Step 2:** Apply the meaning-search rule (≥ 5 points lower, ≥ 60% kept). If it fails, run the grid for search only and
  pick by the same rule. A separate search strength becomes the config key `volume_balance_search` (same default 0), wired
  in `search` only. Ledger the ruling.
- [ ] **Step 3: Commit** the tool (`git commit -m "volume balance: meaning search measured"`).

### Task 5: App wiring and blind sheet

**Files:**
- Modify: `lib/services/engine/engine_pack.dart` (`'volume_balance': <STRENGTH>` in `config()`, plus
  `'volume_balance_search'` if Task 4 made one)
- Test: the existing engine-pack config test (or a new `test/engine_pack_config_test.dart`): `config()` contains the key
  with the chosen value.
- Modify: `tool/balance_review_sheet.py` (renamed in Task 2): the two lists are `volume_balance` 0 vs the chosen strength.
  40 similar items (20 across the canon, 20 for two-volume mixes) and 40 search items, only pairs whose lists differ, with the
  same blind A/B page and scorer. Scoring rule written into the sheet intro and the tool: the feature stays on unless the new
  list wins **less than 45%** of decided pairs.
- [ ] **Step 1:** Write the config test, run `flutter test test/engine_pack_config_test.dart` → FAIL. Add the key → PASS.
- [ ] **Step 2:** Build the sheets → `local-benchmarks/balance-review-similar.html`, `balance-review-search.html` (+ keys).
- [ ] **Step 3:** `flutter test` (whole suite) → pass. `flutter analyze` → no new issues.
- [ ] **Step 4: Commit.** `git commit -m "volume balance: on in the app, blind sheets"`.

### Task 6: Docs and builds

- [ ] `docs/DEVLOG.md`: a section "volume balance replaces scope profiles", with the probe numbers (per-gene dials 78.6 → 78.0,
  full centring 77.6, 4 directions removed 77.1 with the volume still 98% guessable; output offset 60.2), the chosen settings
  and the Task 1/4 tables in simple English.
- [ ] `docs/EXPERIENCE.md`: one paragraph on what the reader sees (nothing to switch, mixes are fair).
- [ ] Mark `docs/superpowers/plans/2026-10-14-scope-profiles.md` as superseded at its top.
- [ ] Rebuild the Windows release and the installer (`generated-artifacts/dist/Scriptura-Setup-1.0.0.exe`) and the arm64 APK,
  because the engine library changed. Smoke-test Similar verses and a canon search on Windows.
- [ ] Commit `git commit -m "devlog: volume balance"`.
