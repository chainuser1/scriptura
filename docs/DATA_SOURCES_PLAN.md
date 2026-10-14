# Clean Data Source Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One authoritative, verifiable, provenance-labeled data layer for the app (one derived content database whose English text is KJV, plus a writable user database), serving only what is complete, with every legacy resource classified, quarantined or removed so nothing old can be loaded by accident.

**Architecture:** `scriptures_genome.db` from `application-v1` is the only runtime content source for structure, search text, vectors and non-English languages, opened read-only through a validated `ContentDatabase`. A derived copy of it, built by `tool/build_kjv_content_db.py`, carries KJV (LDS edition) text in the English table, so the app reads one database and one table per language. A `ContentRepository` serves passages/chapters/books for the languages the database declares complete, with explicit provenance. A separate writable `user.db` holds personal data. A `ReleaseStore` verifies and atomically activates versioned releases.

**Tech Stack:** Flutter/Dart (`sqlite3` FFI package, Riverpod already in the project), Python 3.14 tooling in the existing `.venv`, SQLite 3 with FTS5.

**Spec:** [PLAN.md](../PLAN.md) sections 4, 5, 9, 11, 13 (Phase 4); [PLAN_REVIEW.md](PLAN_REVIEW.md); [ARTIFACT_HANDOFF.md](ARTIFACT_HANDOFF.md); owner decisions D1–D7 below; the legacy-resource review in [Part A](#part-a-legacy-resource-disposition).

> **Supersession note (2026-10-13).** The shipped reading release now uses the compact **schema v2** layout built by
> `tool/build_release.py` (Task 6c): `content.db` + `catalog.db` + `phrase-index.db`. Code and tests in Tasks 4, 5, 8
> and 9 below were written against the earlier v1 shape (`scriptures_genome.db` with per-language `reference`,
> `book`, `chapter`, `verse` columns). The files in the repository are authoritative; where a code block here
> disagrees with them (table names `text_<language>`, repository signature `ContentRepository(content, catalog)`,
> chapters read by `bookId`, `requiredReleaseFiles = {'content.db', 'catalog.db'}`), the repository wins.

## Global Constraints

- Authoritative source files: `<projects>\scriptura\application_databases` (`scriptures_genome.db` required; `questions_genome.db` optional; `scripture_genome_raw.db` diagnostic only). The SHA-256-verified staging copy under `.artifact-staging/import-application-v1/databases` is identical. Source DBs are opened **read-only** and never modified (PLAN 5.1, 9).
- Verse IDs are canonical `INTEGER` 1..41,995 and identical in every legacy and new database (verified; the only naming difference is "Song of Solomon" vs "Song of Songs", 117 verses).
- **Serve what is complete.** A language is offered only if `language_coverage.complete = 1` in the installed database and its table exists. Today that is `english, spanish, tagalog, cebuano, greek` (41,995 verses each). `french` (35,810), `german` (36,831) and `hebrew` (21,759) stay in the database but are not served. Japanese is excluded by the owner.
- The SQL language→table allowlist (`english, spanish, tagalog, cebuano, greek, french, german, hebrew` → `scriptures_<language>`) exists only to make table names safe; it is not the serving list. User text is never interpolated into SQL; values are bound (PLAN 5.2).
- **English text in the content database is KJV (LDS edition)** (owner instruction, 2026-10-13). `tool/build_kjv_content_db.py` derives a new `scriptures_genome.db` from the pinned base, replacing only `scriptures_english.scripture_text`, the English provenance rows and metadata. The pinned original is never modified. The NRSVue/YLT retrieval text stays outside the shipped database (in the retrieval bundle used offline for indexes). Search edition ≠ display edition is an explicit policy (PLAN 5.2).
- Every passage carries `source` and `quality_tier` (from `scripture_text_sources`, or `edition:<id>` for edition packs). Edition packs carry `license_status = unreviewed` until the rights audit (PLAN 9, Phase 6).
- Text is never machine-translated. If a served language unexpectedly lacks a verse (data defect), the repository returns the English passage flagged `isFallback`, never blank (PLAN 5.2).
- Personal data lives only in `user.db`, is never deleted by cleanup or install code, and migrates transactionally (PLAN 5.3).
- No network access at runtime for content. The legacy GitHub-release downloader is removed, not disabled (PLAN 2, 9).
- Git fixtures are synthetic. Scripture edition text, databases, models and legacy resources never enter Git (PLAN 12.3).
- Legacy files are classified, moved, never deleted by this plan. The SHA-256-verified recovery copy (docs/PHASE0_BASELINE.md) is the safety net.

## Review Focus

Failure modes the spec implies that no single task's happy path exercises (each is pinned by a test named in the owning task):

1. **Unknown, injected or incomplete language** (`"klingon"`, `"english; DROP TABLE x"`, `"french"` at 5/8 coverage, `"hebrew"` not installed) must raise `unsupportedLanguage`, never reach SQL, never half-serve. → Tasks 4 and 5.
2. **Data hole in a "complete" language** (a Spanish verse row missing): the chapter returns every verse in order, with exactly the missing ones flagged `isFallback` and carrying English provenance. → Task 5.
3. **A KJV source that does not match the corpus** (missing verse IDs, a changed reference, empty text, unknown volume) is refused with no partial release left behind, and the derived database may differ from the pinned base only in English text, English provenance and metadata. → Task 6.
4. **Truncated, wrong or non-SQLite file at the content path** produces a specific `ContentException`/`ReleaseException`, not a crash or an empty library; a release whose file was truncated after install reads as "not installed". → Tasks 4 and 8.
5. **Greek polytonic and accented text round-trip unchanged**, and book lookups accept the aliases users actually type ("Psalm", "Song of Solomon"). → Task 5.

---

## Decision gates

| # | Decision | Status / value used by this plan | Effect if changed |
|---|---|---|---|
| D1 | English text in the content database | **Resolved: KJV (LDS edition)**, switched in the English table of a derived `scriptures_genome.db` (owner instruction, 2026-10-13) | Re-run `tool/build_kjv_content_db.py` with another source |
| D2 | Where legacy files live | Default `legacy-quarantine/resources/`, gitignored (needs approval at Task 2) | Path constant |
| D3 | Study aids (topics, cross-references, footnotes) in v1 | **No.** Classified and preserved only; rights audit first | Later plan |
| D4 | AI summaries | Never unlabeled; if ever shipped, "AI-generated" with model name | Presentation rule |
| D5 | Languages served | **Resolved: only complete ones** (English, Spanish, Tagalog, Cebuano, Greek today); data-driven from `language_coverage` so French/German/Hebrew appear automatically if a later release completes them | None |
| D6 | Japanese | **Resolved: excluded.** Legacy `japanese-scriptures-sqlite.db` is classified `discard` | None |
| D7 | Ilocano and Waray (complete legacy databases, not in the application DBs) | **Resolved: not served.** The encoder and genome head were not trained on these languages, so semantic search would be unreliable; kept in quarantine as `archive` | Would need retraining/evaluation first, then a new decision |
| D8 | Release host for the in-app downloader | **Resolved: Hugging Face, set up later** (owner, 2026-10-13). The downloader and artifact upload are deferred; the app must only need plain HTTPS GET with Range support and no credentials | Base URL constant and manifest `url` fields |
| D9 | Rights gate before anything is hosted publicly | **Open, blocking for public hosting.** The app cannot carry tokens, so whatever it downloads is world-readable. Text provenance of the Spanish/Tagalog/Cebuano/Greek tables (`single_source`) and the LDS-edition KJV/standard-works text is unreviewed (PLAN 9, Phase 6). Until cleared, host privately for development only | Whether Task 11 ships |
| D10 | Pack split | Default: **reading pack** (content DB + catalog) required; **search pack** (encoder, indexes, ColBERT) optional; questions DB optional | Manifest `group` fields |

Rights note: NRSVue (27,567 base English verses), Church-edition material, topical/triple indexes and NET notes are not assumed redistributable. KJV Bible text is generally public domain, but the LDS edition's non-Bible text and editorial material are not assumed free. Nothing here is a legal determination; Phase 6 owns the audit.

---

## Part A: Legacy resource disposition

Review of `assets/resources` (read-only inspection; WAL databases inspected on copies). All text databases and study aids share verse IDs 1..41,995 with the new corpus.

| Legacy item | What it is | Class | Pack |
|---|---|---|---|
| `lds-scriptures-sqlite.db` | Full KJV/LDS-edition text, 41,995 verses (Bible = KJV; Book of Mormon, D&C, Pearl of Great Price = standard-works text) | **required_pack** | `edition-kjv-lds` (source of the English text in the content database) |
| `user-data.db` | Old adaptive-search state. No notes/bookmarks/highlights. | archive | none |
| `nrsvue-scriptures-sqlite.db` | NRSVue; already the base English source for 27,567 verses | archive | none |
| `ylt-scriptures-sqlite.db`, `rotherham-scriptures-sqlite.db` | Young's Literal / Rotherham, full | optional_pack | `edition-ylt`, `edition-rotherham` |
| `cebuano`, `greek`, `spanish`, `tagalog` `-scriptures-sqlite.db` | Already represented in `scriptures_genome.db` | archive | none |
| `ilocano`, `waray` `-scriptures-sqlite.db` | Complete languages absent from the new DB; model not trained on them (D7) | archive | none |
| `japanese-scriptures-sqlite.db` | Excluded by owner (D6) | discard | none |
| `topical-guide.db`, `triple-index.db`, `verse-cross-refs.db`, `footnotes-lds-summaries.db` | Topical Guide, Triple index, cross-references, chapter summaries + notes | optional_pack | `study-aids-*` |
| `chapter-summaries-fts.db`, `verse-summaries.db` | AI-generated summaries (kimi-k2) | optional_pack | `ai-summaries` |
| `verse-tags.db` | AI people/places/doctrine tags | optional_pack | `entities` |
| `verse-embeddings.db`, `verse_embeddings.db`, `verse-graph.db`, `search-graph.db`, `concept-embeddings.db` | 768-d embeddings, HNSW, kNN, clusters, PageRank, PMI expansion | discard | none |
| `models/scripture-bge/onnx/*` | Legacy encoder, hashed-word tokenizer | discard | none |
| `*.db-wal`, `*.db-shm` | SQLite sidecars | same as parent | none |

"discard" means: never loaded, never bundled, kept only inside quarantine until the owner chooses to delete.

---

## File structure

| Path | Responsibility |
|---|---|
| `tool/legacy_inventory.py` | Classify + hash every legacy file; refuse unclassified files |
| `docs/legacy_disposition.json` | Committed machine-readable disposition (Task 1 output) |
| `test/legacy_disposition_check.py` | Guard: manifest valid and matches disk |
| `tool/make_fixture_content_db.py` | Generate the synthetic content fixture |
| `test/fixtures/content_mini.db` | Committed synthetic fixture (8 verses; english, spanish, greek complete; french partial) |
| `lib/data/content/content_database.dart` | Validated read-only open, `ContentException`, complete-language discovery |
| `lib/data/content/content_repository.dart` | Passages, chapters, books, aliases, served languages |
| `tool/build_kjv_content_db.py` | Derive the release DB (English text → KJV), self-check, write manifest |
| `tool/build_catalog_db.py`, `tool/data/*.json` | Build `catalog.db` (verse-ID ranges, per-language names/aliases); cited manual labels; extracted legacy aliases |
| `lib/data/content/catalog.dart` | In-memory immutable catalog loaded from `catalog.db` (Task 6b) |
| `test/build_kjv_content_db_check.py` | Checks for the above on the synthetic fixture |
| `lib/data/user/user_database.dart` | `user.db` schema, migrations, bookmarks/notes/highlights |
| `lib/services/artifacts/release_store.dart` | Verified import, atomic activation |
| `tool/check_data_sources.py` | Static gate: no legacy references in app code |

---

### Task 1: Legacy disposition manifest and guard

**Status:** implemented and run 2026-10-13 (36 files classified: 3 required, 17 optional, 6 archive, 10 discard; guard passes).

**Files:**
- Create: `tool/legacy_inventory.py`
- Create: `docs/legacy_disposition.json` (generated)
- Create: `test/legacy_disposition_check.py`

**Interfaces:**
- Consumes: files under `assets/resources/` (or `legacy-quarantine/resources/` after Task 2).
- Produces: `docs/legacy_disposition.json` with `{"root": str, "files": [{"path", "bytes", "sha256", "class", "pack", "reason"}]}`; `class` ∈ `required_pack|optional_pack|archive|discard`; `pack` is non-null for the two pack classes.

- [ ] **Step 1: Write the failing guard test**

`test/legacy_disposition_check.py`:

```python
"""Guard: every legacy resource file is classified, nothing legacy is a runtime source.
Run: .venv\\Scripts\\python.exe -I test/legacy_disposition_check.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
manifest = json.loads((ROOT / 'docs' / 'legacy_disposition.json').read_text('utf-8'))
files = manifest['files']

assert files, 'empty manifest'
assert {f['class'] for f in files} <= {'required_pack', 'optional_pack', 'archive', 'discard'}
assert all(f['reason'] for f in files), 'every entry needs a reason'
assert not [f for f in files if f['class'] in ('required_pack', 'optional_pack') and not f['pack']], 'pack classes need a pack name'
assert len({f['path'] for f in files}) == len(files), 'duplicate paths'

by_path = {f['path']: f for f in files}
assert by_path['db/lds-scriptures-sqlite.db']['class'] == 'required_pack', 'KJV is the default English display edition (D1)'
assert by_path['db/japanese-scriptures-sqlite.db']['class'] == 'discard', 'Japanese is excluded (D6)'

discard = {f['path'] for f in files if f['class'] == 'discard'}
for must in ('db/verse-embeddings.db', 'db/verse-graph.db', 'db/search-graph.db',
             'db/concept-embeddings.db', 'models/scripture-bge/onnx/model_quantized.onnx'):
    assert must in discard, f'{must} must be discard'

known = {f['path']: f['bytes'] for f in files}
for base in (ROOT / 'assets' / 'resources', ROOT / 'legacy-quarantine' / 'resources'):
    if base.exists():
        for p in base.rglob('*'):
            if p.is_file():
                rel = p.relative_to(base).as_posix()
                assert rel in known, f'unclassified legacy file: {rel}'
                assert p.stat().st_size == known[rel], f'size changed: {rel}'
print('legacy disposition: OK,', len(files), 'files')
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv\Scripts\python.exe -I test/legacy_disposition_check.py`
Expected: FAIL with `FileNotFoundError ... legacy_disposition.json`.

- [ ] **Step 3: Write the inventory tool**

`tool/legacy_inventory.py`:

```python
"""Classify and hash every legacy resource file. Refuses to write if any file is unclassified.

  .venv\\Scripts\\python.exe -I tool/legacy_inventory.py [--root PATH] [--out docs/legacy_disposition.json]
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQ, OPT, ARCH, DISC = 'required_pack', 'optional_pack', 'archive', 'discard'

# key: path relative to the resources root, or bare file name -> (class, pack, reason)
RULES = {
    'lds-scriptures-sqlite.db': (REQ, 'edition-kjv-lds', 'Default English display edition (owner decision D1); full KJV/LDS text, same IDs'),
    'user-data.db': (ARCH, None, 'Old adaptive-search learning state; contains no notes, bookmarks or highlights'),
    'nrsvue-scriptures-sqlite.db': (ARCH, None, 'NRSVue; already the base English source for 27,567 verses'),
    'ylt-scriptures-sqlite.db': (OPT, 'edition-ylt', "Young's Literal Translation, full"),
    'rotherham-scriptures-sqlite.db': (OPT, 'edition-rotherham', 'Rotherham, full'),
    'cebuano-scriptures-sqlite.db': (ARCH, None, 'Already represented in scriptures_genome.db'),
    'greek-scriptures-sqlite.db': (ARCH, None, 'Already represented in scriptures_genome.db (text identical)'),
    'spanish-scriptures-sqlite.db': (ARCH, None, 'Already represented in scriptures_genome.db'),
    'tagalog-scriptures-sqlite.db': (ARCH, None, 'Already represented in scriptures_genome.db'),
    'ilocano-scriptures-sqlite.db': (ARCH, None, 'Not served: the encoder and genome head were not trained on this language (owner decision D7, 2026-10-13)'),
    'waray-scriptures-sqlite.db': (ARCH, None, 'Not served: the encoder and genome head were not trained on this language (owner decision D7, 2026-10-13)'),
    'japanese-scriptures-sqlite.db': (DISC, None, 'Excluded by owner decision D6 (2026-10-13)'),
    'topical-guide.db': (OPT, 'study-aids-topics', 'Topical Guide index; drop topic_ppr/verse_pagerank (old graph); rights unreviewed'),
    'triple-index.db': (OPT, 'study-aids-index', 'Triple Combination index; rights unreviewed'),
    'verse-cross-refs.db': (OPT, 'study-aids-crossrefs', 'Cross-references with snippets; provenance unreviewed'),
    'footnotes-lds-summaries.db': (OPT, 'study-aids-footnotes', 'Chapter summaries and notes; per-column rights unreviewed'),
    'chapter-summaries-fts.db': (OPT, 'ai-summaries', 'AI-generated (kimi-k2); must be labeled AI-generated'),
    'verse-summaries.db': (OPT, 'ai-summaries', 'AI-generated (kimi-k2); must be labeled AI-generated'),
    'verse-tags.db': (OPT, 'entities', 'AI people/places/doctrine tags; quality unreviewed'),
    'verse-embeddings.db': (DISC, None, 'Legacy 768-d embeddings + HNSW; superseded (PLAN 1.8)'),
    'verse_embeddings.db': (DISC, None, 'Empty legacy file'),
    'verse-graph.db': (DISC, None, 'Legacy kNN/clusters/spectral; superseded (PLAN 1.8)'),
    'search-graph.db': (DISC, None, 'Legacy PageRank/PMI/entity graph; superseded (PLAN 1.8)'),
    'concept-embeddings.db': (DISC, None, 'Legacy concept embeddings for query expansion; superseded (PLAN 1.8)'),
    'models/scripture-bge/onnx/model_quantized.onnx': (DISC, None, 'Legacy encoder, hashed-word tokenizer; never a substitute (PLAN 2, 3)'),
    'models/scripture-bge/onnx/tokenizer.json': (DISC, None, 'Legacy tokenizer; the pinned BGE-M3 tokenizer is authoritative'),
}


def classify(rel):
    for suffix in ('-wal', '-shm'):
        if rel.endswith(suffix):
            c, pack, _ = classify(rel[: -len(suffix)])
            return c, pack, f'SQLite {suffix[1:]} sidecar of {rel[: -len(suffix)].rsplit("/", 1)[-1]}'
    if rel in RULES:
        return RULES[rel]
    if rel.startswith('db/') and rel[3:] in RULES:
        return RULES[rel[3:]]
    raise KeyError(rel)


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 22), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    default_root = ROOT / 'assets' / 'resources'
    if not default_root.exists():
        default_root = ROOT / 'legacy-quarantine' / 'resources'
    ap.add_argument('--root', default=str(default_root))
    ap.add_argument('--out', default=str(ROOT / 'docs' / 'legacy_disposition.json'))
    a = ap.parse_args()
    root = Path(a.root)
    entries, unknown = [], []
    for p in sorted(x for x in root.rglob('*') if x.is_file()):
        rel = p.relative_to(root).as_posix()
        try:
            cls, pack, reason = classify(rel)
        except KeyError:
            unknown.append(rel)
            continue
        entries.append({'path': rel, 'bytes': p.stat().st_size, 'sha256': sha256(p), 'class': cls, 'pack': pack, 'reason': reason})
    if unknown:
        print('UNCLASSIFIED files (add a rule in RULES):', *unknown, sep='\n  ')
        return 1
    Path(a.out).write_text(json.dumps({'root': 'assets/resources', 'files': entries}, indent=1), 'utf-8')
    by = {}
    for e in entries:
        by[e['class']] = by.get(e['class'], 0) + 1
    print(f'{len(entries)} files classified: {by} -> {a.out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
```

- [ ] **Step 4: Generate the manifest, then run the guard**

Run: `.venv\Scripts\python.exe -I tool/legacy_inventory.py` (hashes ~1.4 GB, about a minute)
Expected: `NN files classified: {...}` and exit 0.
Run: `.venv\Scripts\python.exe -I test/legacy_disposition_check.py`
Expected: `legacy disposition: OK, NN files`.

- [ ] **Step 5: Commit**

```bash
git add tool/legacy_inventory.py docs/legacy_disposition.json test/legacy_disposition_check.py
git commit -m "data: classify legacy resources and add disposition guard"
```

---

### Task 2: Quarantine the legacy resources (owner approval required)

**Status:** done 2026-10-13 with owner approval: `assets/resources` moved to `legacy-quarantine/resources`; 36 files, 0 hash differences; `assets/` now holds only fonts and icons.

**Files:**
- Modify: `.gitignore`

**Interfaces:**
- Consumes: `docs/legacy_disposition.json` from Task 1.
- Produces: `assets/resources/` no longer exists; `legacy-quarantine/resources/` holds byte-identical files. **Task 6 reads the KJV source from this location.**

- [ ] **Step 1: Get the owner's approval for the move (decision D2)**

Ask: "Move `assets/resources/` (1.4 GB, same volume, a rename) to `legacy-quarantine/resources/`? Nothing is deleted; a SHA-256-verified recovery copy already exists." Do not proceed without a yes.

- [ ] **Step 2: Add the ignore rule**

Append to `.gitignore`:

```gitignore
/legacy-quarantine/
```

- [ ] **Step 3: Move, then check**

Run (PowerShell, from the project root; no Flutter or Python process may hold the files):

```powershell
New-Item -ItemType Directory -Force legacy-quarantine | Out-Null
Move-Item -LiteralPath assets\resources -Destination legacy-quarantine\resources
Test-Path assets\resources            # expect False
Test-Path legacy-quarantine\resources # expect True
```

- [ ] **Step 4: Verify every file is intact and the guard still passes**

Run: `.venv\Scripts\python.exe -I tool/legacy_inventory.py --out generated-artifacts\legacy_after_move.json`
Then:

```powershell
$a = (Get-Content docs\legacy_disposition.json | ConvertFrom-Json).files | Sort-Object path
$b = (Get-Content generated-artifacts\legacy_after_move.json | ConvertFrom-Json).files | Sort-Object path
"files: $($a.Count) vs $($b.Count)"
$bad = Compare-Object ($a | ForEach-Object { "$($_.path) $($_.sha256)" }) ($b | ForEach-Object { "$($_.path) $($_.sha256)" })
"differences: $(@($bad).Count)"   # expect 0
```

Run: `.venv\Scripts\python.exe -I test/legacy_disposition_check.py`
Expected: OK.

- [ ] **Step 5: Commit**

```bash
git add .gitignore
git commit -m "data: quarantine legacy resources outside the asset tree"
```

---

### Task 3: Synthetic content fixture

**Status:** generator and committed fixture done 2026-10-13 (used by Tasks 5, 6 and 6b). `test/fixture_content_check.py` was not written; the fixture is exercised by the Python and Dart checks that depend on it. `.gitignore` allows `test/fixtures/*.db`.

**Files:**
- Create: `tool/make_fixture_content_db.py`
- Create: `test/fixtures/content_mini.db` (generated, committed)
- Create: `test/fixture_content_check.py`

**Interfaces:**
- Produces: a SQLite file with the exact real table shapes for `scripture_vectors`, `scriptures_english` (ids 1..8, complete), `scriptures_spanish` (1..8, complete), `scriptures_greek` (1..8, complete, polytonic-capable text), `scriptures_french` (1..5, **incomplete**), `scripture_text_sources`, `language_coverage`, `database_metadata`. Books: `Alpha Book` (ch1 v1-3, ch2 v1-2), `Beta Book` (ch1 v1-3).

- [ ] **Step 1: Write the failing check**

`test/fixture_content_check.py`:

```python
import sqlite3
from pathlib import Path

db = Path(__file__).resolve().parent / 'fixtures' / 'content_mini.db'
c = sqlite3.connect(f'file:{db.as_posix()}?mode=ro', uri=True)
count = lambda t: c.execute(f'select count(*) from {t}').fetchone()[0]  # noqa: E731
assert count('scriptures_english') == 8
assert count('scriptures_spanish') == 8
assert count('scriptures_greek') == 8
assert count('scriptures_french') == 5
assert dict(c.execute('select key, value from database_metadata'))['database_kind'] == 'scriptures'
assert all(len(b) == 2272 for (b,) in c.execute('select vector from scripture_vectors'))
assert c.execute("select count(*) from scripture_text_sources where lang='english' and source='synthetic'").fetchone()[0] == 8
cov = {r[0]: (r[1], r[2], r[3]) for r in c.execute('select language, rows, expected_rows, complete from language_coverage')}
assert cov == {'english': (8, 8, 1), 'spanish': (8, 8, 1), 'greek': (8, 8, 1), 'french': (5, 8, 0)}, cov
el = c.execute('select scripture_text from scriptures_greek where verse_id = 1').fetchone()[0]
assert any('\u0370' <= ch <= '\u03ff' for ch in el), 'greek fixture must contain Greek letters'
print('fixture: OK')
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -I test/fixture_content_check.py`
Expected: FAIL (`unable to open database file`).

- [ ] **Step 3: Write the generator**

`tool/make_fixture_content_db.py`:

```python
"""Generate test/fixtures/content_mini.db: synthetic text, real schema (PLAN 12.3)."""
import sqlite3
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / 'test' / 'fixtures' / 'content_mini.db'
BOOKS = [('Alpha Book', 'Alpha', [3, 2]), ('Beta Book', 'Beta', [3])]  # (book, short, verses per chapter)

TEXT_TABLE = '''CREATE TABLE {t} (
    verse_id INTEGER PRIMARY KEY REFERENCES scripture_vectors(verse_id),
    scripture_text TEXT NOT NULL CHECK(length(trim(scripture_text))>0),
    reference TEXT NOT NULL UNIQUE,
    shortened TEXT NOT NULL,
    book TEXT NOT NULL,
    chapter INTEGER NOT NULL,
    verse INTEGER NOT NULL,
    UNIQUE(book,chapter,verse))'''

# language -> (rows present, source name, text maker)
LANGS = {
    'english': (8, 'synthetic', lambda i: f'Synthetic English passage {i}.'),
    'spanish': (8, 'synthetic_es', lambda i: f'Pasaje sintético {i}: ¿cómo estás?'),
    'greek': (8, 'synthetic_el', lambda i: f'Σύνθετο κείμενο {i} ἀγάπη'),
    'french': (5, 'synthetic_fr', lambda i: f'Passage synthétique {i}.'),
}


def verses():
    vid = 0
    for book, short, chapters in BOOKS:
        for ch, n in enumerate(chapters, 1):
            for v in range(1, n + 1):
                vid += 1
                yield vid, book, short, ch, v


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if OUT.exists():
        OUT.unlink()
    c = sqlite3.connect(OUT)
    c.execute('CREATE TABLE database_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL) WITHOUT ROWID')
    c.executemany('INSERT INTO database_metadata VALUES (?,?)', [
        ('application_release', 'fixture-v1'), ('database_kind', 'scriptures'), ('dimensions', '568'),
        ('schema_version', 'v5.0'), ('vector_bytes', '2272'), ('vector_encoding', 'float32_little_endian')])
    c.execute('CREATE TABLE scripture_vectors (verse_id INTEGER PRIMARY KEY, vector BLOB NOT NULL CHECK(length(vector)=2272))')
    c.execute('''CREATE TABLE scripture_text_sources (
        verse_id INTEGER NOT NULL REFERENCES scripture_vectors(verse_id), lang TEXT NOT NULL,
        source TEXT NOT NULL, quality_tier TEXT NOT NULL, PRIMARY KEY(verse_id,lang)) WITHOUT ROWID''')
    c.execute('''CREATE TABLE language_coverage (
        language TEXT PRIMARY KEY, table_name TEXT NOT NULL, rows INTEGER NOT NULL, expected_rows INTEGER NOT NULL,
        complete INTEGER NOT NULL CHECK(complete IN (0,1)), reference_language TEXT NOT NULL) WITHOUT ROWID''')
    for vid, *_ in verses():
        c.execute('INSERT INTO scripture_vectors VALUES (?,?)', (vid, bytes(2272)))
    for lang, (limit, source, mk) in LANGS.items():
        c.execute(TEXT_TABLE.format(t=f'scriptures_{lang}'))
        for vid, book, short, ch, v in verses():
            if vid > limit:
                continue
            c.execute(f'INSERT INTO scriptures_{lang} VALUES (?,?,?,?,?,?,?)',
                      (vid, mk(vid), f'{book} {ch}:{v}', f'{short} {ch}:{v}', book, ch, v))
            c.execute('INSERT INTO scripture_text_sources VALUES (?,?,?,?)', (vid, lang, source, 'core'))
        c.execute('INSERT INTO language_coverage VALUES (?,?,?,?,?,?)',
                  (lang, f'scriptures_{lang}', limit, 8, int(limit == 8), 'english'))
    c.commit()
    c.execute('VACUUM')
    c.close()
    print('wrote', OUT)


if __name__ == '__main__':
    main()
```

- [ ] **Step 4: Generate and run the check**

Run: `.venv\Scripts\python.exe -I tool/make_fixture_content_db.py`
Run: `.venv\Scripts\python.exe -I test/fixture_content_check.py`
Expected: `fixture: OK`.

- [ ] **Step 5: Allow the fixture past the `*.db` ignore rule, then commit**

Append to `.gitignore` (the fixture is synthetic, a few KB, and contains no scripture text):

```gitignore
!/test/fixtures/*.db
```

Verify with `git check-ignore -v test/fixtures/content_mini.db` (no output = not ignored), then:

```bash
git add .gitignore tool/make_fixture_content_db.py test/fixtures/content_mini.db test/fixture_content_check.py
git commit -m "test: add synthetic content fixture with real schema"
```

---

### Task 4: `ContentDatabase` (validated read-only open) and SQLite qualification

**Status:** executed 2026-10-13, 6 tests pass. SQLite loads on the Windows host test runner and FTS5 is available (no extra DLL step needed). The `sqlite3` package now deprecates `Database.dispose()`; the code calls `close()`.

**Files:**
- Modify: `pubspec.yaml`
- Create: `lib/data/content/content_database.dart`
- Test: `test/data/content_database_test.dart`

**Interfaces:**
- Produces:
  - `enum ContentErrorKind { missing, notSqlite, wrongKind, wrongDimensions, notFound, unsupportedLanguage }`
  - `class ContentException implements Exception { ContentErrorKind kind; String message; }`
  - `class ContentDatabase { static ContentDatabase open(String path, {String kind = 'scriptures'}); final Database db; final Map<String,String> metadata; final Set<String> completeLanguages; bool hasTable(String name); void dispose(); }` where `completeLanguages` = languages with `language_coverage.complete = 1` **and** an existing table.

- [ ] **Step 1: Add the dependency and write the failing tests**

Run: `flutter pub add sqlite3 path`

`test/data/content_database_test.dart`:

```dart
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:scriptures_reader_mobile/data/content/content_database.dart';

const fixture = 'test/fixtures/content_mini.db';

void main() {
  test('opens the fixture read-only and exposes metadata', () {
    final c = ContentDatabase.open(fixture);
    addTearDown(c.dispose);
    expect(c.metadata['database_kind'], 'scriptures');
    expect(c.hasTable('scriptures_english'), isTrue);
    expect(c.hasTable('scriptures_hebrew'), isFalse);
  });

  test('only languages declared complete are reported as complete', () {
    final c = ContentDatabase.open(fixture);
    addTearDown(c.dispose);
    expect(c.completeLanguages, {'english', 'spanish', 'greek'}); // french is 5/8, hebrew absent
  });

  test('FTS5 is available in the bundled SQLite', () {
    final c = ContentDatabase.open(fixture);
    addTearDown(c.dispose);
    final r = c.db.select("SELECT sqlite_compileoption_used('ENABLE_FTS5') AS fts5");
    expect(r.first['fts5'], 1);
  });

  test('missing file raises ContentException(missing)', () {
    expect(() => ContentDatabase.open('test/fixtures/nope.db'),
        throwsA(isA<ContentException>().having((e) => e.kind, 'kind', ContentErrorKind.missing)));
  });

  test('a non-SQLite file raises ContentException(notSqlite)', () {
    final f = File('${Directory.systemTemp.path}/not_a_db.db')..writeAsStringSync('this is not sqlite');
    addTearDown(() => f.deleteSync());
    expect(() => ContentDatabase.open(f.path),
        throwsA(isA<ContentException>().having((e) => e.kind, 'kind', ContentErrorKind.notSqlite)));
  });

  test('a database of the wrong kind is rejected', () {
    expect(() => ContentDatabase.open(fixture, kind: 'questions'),
        throwsA(isA<ContentException>().having((e) => e.kind, 'kind', ContentErrorKind.wrongKind)));
  });
}
```

- [ ] **Step 2: Run to verify it fails**

Run: `flutter test test/data/content_database_test.dart`
Expected: FAIL (`content_database.dart` does not exist).

- [ ] **Step 3: Write the implementation**

`lib/data/content/content_database.dart`:

```dart
import 'dart:io';

import 'package:sqlite3/sqlite3.dart';

enum ContentErrorKind { missing, notSqlite, wrongKind, wrongDimensions, notFound, unsupportedLanguage }

class ContentException implements Exception {
  ContentException(this.kind, this.message);
  final ContentErrorKind kind;
  final String message;
  @override
  String toString() => 'ContentException(${kind.name}): $message';
}

/// A validated, read-only handle on one application content database.
class ContentDatabase {
  ContentDatabase._(this.db, this.metadata, this._tables, this.completeLanguages);

  final Database db;
  final Map<String, String> metadata;
  final Set<String> _tables;

  /// Languages the database declares complete AND whose table exists. Only these are served.
  final Set<String> completeLanguages;

  static ContentDatabase open(String path, {String kind = 'scriptures'}) {
    if (!File(path).existsSync()) {
      throw ContentException(ContentErrorKind.missing, 'No content database at $path');
    }
    final Database db = sqlite3.open(path, mode: OpenMode.readOnly);
    try {
      final metadata = {
        for (final r in db.select('SELECT key, value FROM database_metadata')) r['key'] as String: r['value'] as String
      };
      if (metadata['database_kind'] != kind) {
        throw ContentException(ContentErrorKind.wrongKind,
            'Expected database_kind=$kind, found ${metadata['database_kind']}');
      }
      if (metadata['dimensions'] != '568' || metadata['vector_encoding'] != 'float32_little_endian') {
        throw ContentException(ContentErrorKind.wrongDimensions,
            'Unsupported vector contract: ${metadata['dimensions']}/${metadata['vector_encoding']}');
      }
      final tables = {
        for (final r in db.select("SELECT name FROM sqlite_master WHERE type IN ('table','view')")) r['name'] as String
      };
      final complete = <String>{};
      if (tables.contains('language_coverage')) {
        for (final r in db.select('SELECT language, table_name FROM language_coverage WHERE complete = 1')) {
          if (tables.contains(r['table_name'])) complete.add(r['language'] as String);
        }
      }
      return ContentDatabase._(db, metadata, tables, complete);
    } on SqliteException catch (e) {
      db.dispose();
      throw ContentException(ContentErrorKind.notSqlite, 'Not a usable SQLite database: ${e.message}');
    } catch (_) {
      db.dispose();
      rethrow;
    }
  }

  bool hasTable(String name) => _tables.contains(name);

  void dispose() => db.dispose();
}
```

Note: for the `kind: 'questions'` test the fixture fails the kind check before any vector check, which is the behavior under test.

- [ ] **Step 4: Run the tests**

Run: `flutter test test/data/content_database_test.dart`
Expected: PASS (6 tests).
If it fails with `Failed to load dynamic library 'sqlite3.dll'`, the host test runner has no SQLite: resolve the `sqlite3` package version that bundles it via build hooks, or place the official `sqlite3.dll` in the project root and add `/sqlite3.dll` to `.gitignore`; then re-run. If `fts5` is `0` on Android builds, add `sqlite3_flutter_libs` and re-run the FTS5 test on-device in Phase 4.

- [ ] **Step 5: Commit**

```bash
git add pubspec.yaml pubspec.lock lib/data/content/content_database.dart test/data/content_database_test.dart
git commit -m "data: add validated read-only content database"
```

---

### Task 5: `ContentRepository`

**Status:** executed 2026-10-13, 8 tests pass. The repository still carries its own small alias map; delegating `listBooks`/`resolveBook` to `Catalog` (Task 6b) is not wired yet.

**Files:**
- Create: `lib/data/content/content_repository.dart`
- Test: `test/data/content_repository_test.dart`

**Interfaces:**
- Consumes: `ContentDatabase` (with `completeLanguages`), `ContentException`, `ContentErrorKind` (Task 4).
- Produces:

```dart
const supportedLanguages = {...}; // SQL allowlist language -> 'scriptures_<language>' (8 entries)
class Passage { int verseId; String text, reference, shortened, book; int chapter, verse;
  String language;          // language of `text`
  String requestedLanguage; // what the caller asked for
  bool get isFallback;      // language != requestedLanguage
  String source, qualityTier; }
class BookEntry { String name; int firstVerseId, chapters, verses; }
class ContentRepository {
  ContentRepository(ContentDatabase content);
  List<String> get servedLanguages;                    // sorted; complete AND allowlisted
  Passage getPassage(int verseId, {String language = 'english'});
  List<Passage> getChapter(String book, int chapter, {String language = 'english'});
  List<BookEntry> listBooks();
  String? resolveBook(String input);                   // canonical name or null
}
```

- [ ] **Step 1: Write the failing tests**

`test/data/content_repository_test.dart`:

```dart
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:scriptures_reader_mobile/data/content/content_database.dart';
import 'package:scriptures_reader_mobile/data/content/content_repository.dart';
import 'package:sqlite3/sqlite3.dart';

Matcher unsupported() =>
    throwsA(isA<ContentException>().having((e) => e.kind, 'kind', ContentErrorKind.unsupportedLanguage));

void main() {
  late ContentDatabase db;
  late ContentRepository repo;
  setUp(() {
    db = ContentDatabase.open('test/fixtures/content_mini.db');
    repo = ContentRepository(db);
  });
  tearDown(() => db.dispose());

  test('only complete languages are served', () {
    expect(repo.servedLanguages, ['english', 'greek', 'spanish']);
  });

  test('passage in a served language carries its own provenance', () {
    final p = repo.getPassage(2, language: 'spanish');
    expect(p.text, 'Pasaje sintético 2: ¿cómo estás?'); // accents and ¿ unchanged
    expect(p.isFallback, isFalse);
    expect(p.source, 'synthetic_es');
    expect(p.reference, 'Alpha Book 1:2');
  });

  test('an incomplete or uninstalled language is not served (no half-serving)', () {
    expect(() => repo.getPassage(1, language: 'french'), throwsA(isA<ContentException>())); // 5/8
    expect(() => repo.getPassage(1, language: 'french'), unsupported());
    expect(() => repo.getPassage(1, language: 'hebrew'), unsupported()); // not installed
    expect(() => repo.getChapter('Alpha Book', 1, language: 'french'), unsupported());
  });

  test('unknown or injected language never reaches SQL', () {
    for (final bad in ['klingon', 'english; DROP TABLE scriptures_english', '', 'ENGLISH']) {
      expect(() => repo.getPassage(1, language: bad), unsupported());
    }
    expect(repo.getPassage(1).text, startsWith('Synthetic')); // table still there
  });

  test('unknown verse id raises notFound', () {
    expect(() => repo.getPassage(9999),
        throwsA(isA<ContentException>().having((e) => e.kind, 'kind', ContentErrorKind.notFound)));
  });

  test('a data hole in a complete language falls back per verse, flagged, in order', () {
    final dir = Directory.systemTemp.createTempSync('hole');
    final copy = '${dir.path}/content.db';
    File('test/fixtures/content_mini.db').copySync(copy);
    final w = sqlite3.open(copy);
    w.execute('DELETE FROM scriptures_spanish WHERE verse_id IN (6, 7)'); // Beta Book 1:1 and 1:2
    w.dispose();

    final holey = ContentDatabase.open(copy);
    addTearDown(holey.dispose);
    final r = ContentRepository(holey);

    final ch = r.getChapter('Beta Book', 1, language: 'spanish');
    expect(ch.map((p) => p.verse), [1, 2, 3]);
    expect(ch.map((p) => p.isFallback), [true, true, false]);
    expect(ch[0].language, 'english');
    expect(ch[0].source, 'synthetic'); // English provenance, not Spanish
    expect(ch[2].source, 'synthetic_es');

    final p = r.getPassage(7, language: 'spanish');
    expect(p.isFallback, isTrue);
    expect(p.requestedLanguage, 'spanish');
  });

  test('Greek (polytonic) round-trips unchanged', () {
    final p = repo.getPassage(1, language: 'greek');
    expect(p.text, 'Σύνθετο κείμενο 1 ἀγάπη');
    expect(p.isFallback, isFalse);
  });

  test('books come in canonical order with chapter/verse counts', () {
    final b = repo.listBooks();
    expect(b.map((x) => x.name), ['Alpha Book', 'Beta Book']);
    expect(b.first.chapters, 2);
    expect(b.first.verses, 5);
  });

  test('book aliases resolve to canonical names', () {
    expect(repo.resolveBook('  alpha   BOOK '), 'Alpha Book');
    expect(repo.resolveBook('nonsense'), isNull);
  });
}
```

(Delete the redundant first `expect` line in the "incomplete" test when implementing; both assertions check the same thing.)

- [ ] **Step 2: Run to verify it fails**

Run: `flutter test test/data/content_repository_test.dart`
Expected: FAIL (`content_repository.dart` does not exist).

- [ ] **Step 3: Write the implementation**

`lib/data/content/content_repository.dart`:

```dart
import 'content_database.dart';

/// SQL-safety allowlist only: which table a language name may map to. NOT the serving list.
const supportedLanguages = <String, String>{
  'english': 'scriptures_english',
  'spanish': 'scriptures_spanish',
  'tagalog': 'scriptures_tagalog',
  'cebuano': 'scriptures_cebuano',
  'greek': 'scriptures_greek',
  'french': 'scriptures_french',
  'german': 'scriptures_german',
  'hebrew': 'scriptures_hebrew',
};

/// Names users type that differ from the corpus's canonical book names.
const _bookAliases = <String, String>{
  'psalm': 'Psalms',
  'song of solomon': 'Song of Songs',
  'songs of solomon': 'Song of Songs',
  'song of songs': 'Song of Songs',
  'js-h': 'Joseph Smith--History',
  'joseph smith-history': 'Joseph Smith--History',
  'd&c': 'Doctrine and Covenants',
};

class Passage {
  Passage({
    required this.verseId,
    required this.text,
    required this.reference,
    required this.shortened,
    required this.book,
    required this.chapter,
    required this.verse,
    required this.language,
    required this.requestedLanguage,
    required this.source,
    required this.qualityTier,
  });

  final int verseId;
  final String text, reference, shortened, book;
  final int chapter, verse;
  final String language, requestedLanguage, source, qualityTier;
  bool get isFallback => language != requestedLanguage;
}

class BookEntry {
  BookEntry(this.name, this.firstVerseId, this.chapters, this.verses);
  final String name;
  final int firstVerseId, chapters, verses;
}

class ContentRepository {
  ContentRepository(this._content);
  final ContentDatabase _content;

  static String _norm(String s) => s.trim().toLowerCase().replaceAll('—', '--').replaceAll(RegExp(r'\s+'), ' ');

  /// Languages offered to users: declared complete by the database AND on the allowlist.
  List<String> get servedLanguages =>
      [for (final l in supportedLanguages.keys) if (_content.completeLanguages.contains(l)) l]..sort();

  String _served(String language) {
    if (!supportedLanguages.containsKey(language) || !_content.completeLanguages.contains(language)) {
      throw ContentException(ContentErrorKind.unsupportedLanguage,
          'Language "$language" is not served (unknown or incomplete)');
    }
    return language;
  }

  Passage _row(dynamic r, String language, String requested) => Passage(
        verseId: r['verse_id'] as int,
        text: r['scripture_text'] as String,
        reference: r['reference'] as String,
        shortened: r['shortened'] as String,
        book: r['book'] as String,
        chapter: r['chapter'] as int,
        verse: r['verse'] as int,
        language: language,
        requestedLanguage: requested,
        source: (r['source'] as String?) ?? 'unknown',
        qualityTier: (r['quality_tier'] as String?) ?? 'unknown',
      );

  Passage? _fetch(String language, int verseId, String requested) {
    final table = supportedLanguages[language]!; // allowlisted, never user text
    final rows = _content.db.select(
      'SELECT s.verse_id, s.scripture_text, s.reference, s.shortened, s.book, s.chapter, s.verse, '
      't.source AS source, t.quality_tier AS quality_tier '
      'FROM $table s LEFT JOIN scripture_text_sources t ON t.verse_id = s.verse_id AND t.lang = ? '
      'WHERE s.verse_id = ?',
      [language, verseId],
    );
    return rows.isEmpty ? null : _row(rows.first, language, requested);
  }

  Passage getPassage(int verseId, {String language = 'english'}) {
    final lang = _served(language);
    final hit = _fetch(lang, verseId, language);
    if (hit != null) return hit;
    if (lang != 'english') {
      final en = _fetch('english', verseId, language); // data hole in a "complete" language
      if (en != null) return en;
    }
    throw ContentException(ContentErrorKind.notFound, 'No passage with verse_id $verseId');
  }

  List<Passage> getChapter(String book, int chapter, {String language = 'english'}) {
    final lang = _served(language);
    final table = supportedLanguages[lang]!;
    final rows = _content.db.select(
      'SELECT e.verse_id AS verse_id, e.book AS book, e.chapter AS chapter, e.verse AS verse, '
      'e.scripture_text AS e_text, e.reference AS e_ref, e.shortened AS e_short, '
      'l.scripture_text AS l_text, l.reference AS l_ref, l.shortened AS l_short, '
      'tl.source AS l_source, tl.quality_tier AS l_tier, te.source AS e_source, te.quality_tier AS e_tier '
      'FROM scriptures_english e '
      'LEFT JOIN $table l ON l.verse_id = e.verse_id '
      'LEFT JOIN scripture_text_sources tl ON tl.verse_id = e.verse_id AND tl.lang = ? '
      "LEFT JOIN scripture_text_sources te ON te.verse_id = e.verse_id AND te.lang = 'english' "
      'WHERE e.book = ? AND e.chapter = ? ORDER BY e.verse',
      [lang, book, chapter],
    );
    return [
      for (final r in rows)
        () {
          final hasLocal = r['l_text'] != null;
          return Passage(
            verseId: r['verse_id'] as int,
            text: (hasLocal ? r['l_text'] : r['e_text']) as String,
            reference: (hasLocal ? r['l_ref'] : r['e_ref']) as String,
            shortened: (hasLocal ? r['l_short'] : r['e_short']) as String,
            book: r['book'] as String,
            chapter: r['chapter'] as int,
            verse: r['verse'] as int,
            language: hasLocal ? lang : 'english',
            requestedLanguage: language,
            source: ((hasLocal ? r['l_source'] : r['e_source']) as String?) ?? 'unknown',
            qualityTier: ((hasLocal ? r['l_tier'] : r['e_tier']) as String?) ?? 'unknown',
          );
        }()
    ];
  }

  List<BookEntry> listBooks() {
    final rows = _content.db.select(
      'SELECT book, MIN(verse_id) AS first_id, MAX(chapter) AS chapters, COUNT(*) AS verses '
      'FROM scriptures_english GROUP BY book ORDER BY first_id',
    );
    return [
      for (final r in rows)
        BookEntry(r['book'] as String, r['first_id'] as int, r['chapters'] as int, r['verses'] as int)
    ];
  }

  String? resolveBook(String input) {
    final key = _norm(input);
    for (final b in listBooks()) {
      if (_norm(b.name) == key) return b.name;
    }
    return _bookAliases[key];
  }
}
```

- [ ] **Step 4: Run the tests**

Run: `flutter test test/data/content_repository_test.dart`
Expected: PASS (9 tests).

- [ ] **Step 5: Commit**

```bash
git add lib/data/content/content_repository.dart test/data/content_repository_test.dart
git commit -m "data: add content repository serving only complete languages"
```

---

### Task 6: KJV English text in the content database (derived release)

**Status:** implemented and verified 2026-10-13 (tool, check and real build). Step 5 (commit) remains.

**Files:**
- Create: `tool/build_kjv_content_db.py`
- Test: `test/build_kjv_content_db_check.py`
- Output (gitignored): `generated-artifacts/release-application-v1-kjv/scriptures_genome.db` and `manifest.json`

**Interfaces:**
- Consumes: the pinned base `scriptures_genome.db`; the legacy `lds-scriptures-sqlite.db` (tables `books(id, volume_id, book_title)`, `chapters(id, book_id, chapter_number)`, `verses(id, chapter_id, verse_number, scripture_text)`); the Task 3 fixture for tests.
- Produces: `build(base_db, legacy_db, out_dir, release=None) -> {'release', 'rows', 'sources', 'manifest'}` and a release directory containing `scriptures_genome.db` plus `manifest.json` (`{"release", "files": {name: {"bytes", "sha256"}}, ...}`, the shape `ReleaseStore` consumes in Task 8). Release id defaults to `<application_release>+kjv`.

Behavior (this is the contract the check pins):
- Only these change relative to the base: `scriptures_english.scripture_text` (all 41,995 verses), `scripture_text_sources` rows with `lang='english'` (`source` = `kjv` for volumes 1-2 Old/New Testament, `lds` for volumes 3-5 Book of Mormon / D&C / Pearl of Great Price), and `database_metadata` (`application_release`, `english_text_edition`, `derived_from_sha256`, `english_source_sha256`, `derived_with`).
- Every other table and column is digest-compared against the base after the build; any difference aborts the build.
- Verse IDs and `(book, chapter, verse)` must match the base exactly (only the alias `Song of Solomon` → `Song of Songs` is accepted); empty text or an unknown volume aborts.
- The base and legacy files are opened read-only and never modified; an existing output directory is refused; a failed build leaves no partial directory.
- The retrieval text (NRSVue/YLT mix) is not carried into the result.

- [x] **Step 1: Write the failing check**

`test/build_kjv_content_db_check.py` asserts, on the synthetic fixture: the base file hash is unchanged; English text is switched for all 8 verses; no `Synthetic…` base text survives; Spanish, Greek, French, vectors and coverage tables are row-for-row equal to the base; English sources are `kjv` for the Old Testament book and `lds` for the Book of Mormon book while Spanish provenance is untouched; metadata and manifest hash are correct; `integrity_check` is `ok`; a legacy source with a missing verse, or with a wrong book name, is refused and leaves no output directory; an existing output directory is refused.

- [x] **Step 2: Run it to verify it fails**

Run: `.venv\Scripts\python.exe -I test/build_kjv_content_db_check.py`
Expected (before the tool exists): `ModuleNotFoundError: build_kjv_content_db`.

- [x] **Step 3: Implement the tool**

`tool/build_kjv_content_db.py` (see the file; it copies the base, applies the three changes in one transaction, `VACUUM`s, then runs the digest self-check and writes the manifest).

- [x] **Step 4: Run the check, then the real build**

Run: `.venv\Scripts\python.exe -I tool/make_fixture_content_db.py` then `.venv\Scripts\python.exe -I test/build_kjv_content_db_check.py`
Expected: `build_kjv_content_db: OK`.

Real build (legacy file copied to a scratch directory first because it has a WAL sidecar; its text is identical with and without the WAL):

```powershell
.venv\Scripts\python.exe -I tool/build_kjv_content_db.py `
  <projects>\scriptura\application_databases\scriptures_genome.db `
  generated-artifacts\lds-view\lds-scriptures-sqlite.db `
  generated-artifacts\release-application-v1-kjv
```

Recorded result (2026-10-13): release `application-v1+kjv`; 41,995 passages (`kjv` 31,102, `lds` 10,893); `integrity_check` ok; output 214,990,848 bytes, SHA-256 `609f442cb05b3a03c06b0fe95c4cb99f291897339373f64866c97f4957768d18`; base SHA-256 `e8ca90e1…c9c36` unchanged before and after; Genesis 1:1, Psalms 23:1, John 3:16 read as KJV, Doctrine and Covenants 64:7 and 1 Nephi 3:7 read as `lds`; language coverage unchanged (English/Spanish/Tagalog/Cebuano/Greek complete).

- [ ] **Step 5: Commit**

```bash
git add tool/build_kjv_content_db.py test/build_kjv_content_db_check.py tool/make_fixture_content_db.py test/fixtures/content_mini.db
git commit -m "data: derive the content database with KJV English text"
```

---

### Task 6b: Catalog database (volumes, books, chapters; per-language names and aliases)

**Status:** Python tool, check and real build implemented 2026-10-13; Dart reader executed the same day, 4 tests pass, and the real-release integration test passes.

**Files:**
- Create: `tool/build_catalog_db.py`, `tool/data/catalog_manual.json`, `tool/data/book_aliases_en.json`
- Test: `test/build_catalog_db_check.py`
- Create (Dart): `lib/data/content/catalog.dart`; Test: `test/data/catalog_test.dart`
- Output (gitignored): `generated-artifacts/catalog.db`, copied into the release directory and listed in its `manifest.json` with `content_contract.verse_order_sha256`

**Schema** (language names come from the fixed allowlist `english, spanish, tagalog, cebuano, greek, french, german, hebrew`; a language gets tables only if the application DB declares it complete):

| Table | Key | Contents |
|---|---|---|
| `volumes` | `volume_id` | `key` (`ot,nt,bom,dc,pgp`), `first_verse_id`, `last_verse_id`, `book_count` |
| `books` | `book_id` | `volume_id`, `canonical_name`, `first_verse_id`, `last_verse_id`, `chapter_count`, `verse_count` |
| `chapters` | `(book_id, chapter)` | `first_verse_id`, `last_verse_id` |
| `volume_names_<language>` | `volume_id` | `name`, `short_name`, `source` (`manual`, `legacy_<language>`, `application_db`, `legacy_lds`, `fallback_en`), `citation` |
| `book_names_<language>` | `book_id` | `name`, `short_name` (from that language's own table), `long_name` (legacy, only where titles match at the same index), `source`, `long_source` |
| `book_aliases_<language>` | `alias` | `book_id`; folded case/periods/spaces, accent-stripped and `1 jn`/`1jn` variants; ambiguous aliases are dropped |
| `catalog_coverage`, `alias_conflicts`, `catalog_meta` | | counts, dropped aliases, schema version, `verse_order_sha256`, source hashes, served languages |

**Contract:** the catalog depends only on verse-ID structure. It is compatible with any content database whose `verse_order_sha256` (SHA-256 of the int64 little-endian ascending verse IDs; equal to the packaged retrieval config's value `47a72c00…db0f`) matches `catalog_meta`. Changing the English edition therefore never invalidates it.

**Recorded result (2026-10-13):** 87 books, 1,582 chapters, 5 volumes; languages english, spanish, tagalog, cebuano, greek; aliases 332 / 242 / 209 / 209 / 267; 2 ambiguous Greek aliases dropped (`ιακ`, `μωσ`); long titles for all 87 books in english, spanish, greek; no fallback labels; `catalog.db` 212,992 bytes, SHA-256 `3c61d48d85f372fd810a0f70fa31970cd2fc7fbfde4b9e9618d05e63974b95f0`; OT/NT labels and the Cebuano Book of Mormon / Pearl of Great Price labels are `manual` with Church-page citations. A bug found and fixed during the real build: typed aliases must not be folded with the legacy-title rename ("song of solomon" was being lost).

- [x] **Step 1: Python tool, data files and check**

Run: `.venv\Scripts\python.exe -I test/build_catalog_db_check.py`
Expected: `build_catalog_db: OK`. It asserts: ID ranges and chapter coverage; only complete languages get tables; label precedence manual > localized legacy > single-book rule > flagged English fallback; long titles only on a matching index; aliases from names, short names, legacy and manual sources with ambiguous ones dropped and recorded; the contract hash; refusals for out-of-order legacy books, non-contiguous books, an existing output file, and unknown alias targets.

- [x] **Step 2: Real build**

```powershell
.venv\Scripts\python.exe -I tool/build_catalog_db.py `
  generated-artifacts\release-application-v1-kjv\scriptures_genome.db generated-artifacts\catalog.db `
  --legacy-lds generated-artifacts\lds-view\lds-scriptures-sqlite.db `
  --legacy-lang "spanish=legacy-quarantine\resources\db\spanish-scriptures-sqlite.db" `
  --legacy-lang "tagalog=legacy-quarantine\resources\db\tagalog-scriptures-sqlite.db" `
  --legacy-lang "cebuano=legacy-quarantine\resources\db\cebuano-scriptures-sqlite.db" `
  --legacy-lang "greek=legacy-quarantine\resources\db\greek-scriptures-sqlite.db" `
  --release-dir generated-artifacts\release-application-v1-kjv
```

- [ ] **Step 3: Write the failing Dart test**

`test/data/catalog_test.dart` creates a small catalog file with `sqlite3`, then asserts lookup, navigation, alias order and the contract check:

```dart
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:scriptures_reader_mobile/data/content/catalog.dart';
import 'package:scriptures_reader_mobile/data/content/content_database.dart';
import 'package:sqlite3/sqlite3.dart';

String makeCatalog({String contract = 'abc'}) {
  final path = '${Directory.systemTemp.createTempSync().path}/catalog.db';
  final db = sqlite3.open(path);
  db.execute('CREATE TABLE catalog_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)');
  db.execute("INSERT INTO catalog_meta VALUES ('verse_order_sha256', '$contract'), ('served_languages', 'english,spanish')");
  db.execute('CREATE TABLE volumes (volume_id INTEGER PRIMARY KEY, key TEXT, sort_order INTEGER, first_verse_id INTEGER, last_verse_id INTEGER, book_count INTEGER)');
  db.execute("INSERT INTO volumes VALUES (1,'ot',1,1,5,1),(3,'bom',2,6,8,1)");
  db.execute('CREATE TABLE books (book_id INTEGER PRIMARY KEY, volume_id INTEGER, canonical_name TEXT, sort_order INTEGER, first_verse_id INTEGER, last_verse_id INTEGER, chapter_count INTEGER, verse_count INTEGER)');
  db.execute("INSERT INTO books VALUES (1,1,'Alpha Book',1,1,5,2,5),(2,3,'Beta Book',2,6,8,1,3)");
  db.execute('CREATE TABLE chapters (book_id INTEGER, chapter INTEGER, first_verse_id INTEGER, last_verse_id INTEGER)');
  db.execute('INSERT INTO chapters VALUES (1,1,1,3),(1,2,4,5),(2,1,6,8)');
  for (final l in ['english', 'spanish']) {
    db.execute('CREATE TABLE volume_names_$l (volume_id INTEGER PRIMARY KEY, name TEXT, short_name TEXT, source TEXT, citation TEXT)');
    db.execute('CREATE TABLE book_names_$l (book_id INTEGER PRIMARY KEY, name TEXT, short_name TEXT, long_name TEXT, source TEXT, long_source TEXT)');
    db.execute('CREATE TABLE book_aliases_$l (alias TEXT PRIMARY KEY, book_id INTEGER)');
  }
  db.execute("INSERT INTO volume_names_english VALUES (1,'Old Testament','OT','legacy_lds',NULL),(3,'Book of Mormon','BoM','legacy_lds',NULL)");
  db.execute("INSERT INTO volume_names_spanish VALUES (1,'Antiguo Testamento',NULL,'manual','https://example.test'),(3,'Libro de Mormón','LM','legacy_spanish',NULL)");
  db.execute("INSERT INTO book_names_english VALUES (1,'Alpha Book','Alpha','The Long Alpha','application_db','legacy_lds'),(2,'Beta Book','Beta',NULL,'application_db',NULL)");
  db.execute("INSERT INTO book_names_spanish VALUES (1,'Libro Alfa','Alfa',NULL,'application_db',NULL),(2,'Libro Beta','Beta',NULL,'application_db',NULL)");
  db.execute("INSERT INTO book_aliases_english VALUES ('alpha book',1),('alpha',1),('beta book',2)");
  db.execute("INSERT INTO book_aliases_spanish VALUES ('libro alfa',1),('alfa',1),('libro beta',2)");
  db.dispose();
  return path;
}

void main() {
  test('loads names per language and resolves ids to books and chapters', () {
    final c = Catalog.load(makeCatalog(), contract: 'abc');
    expect(c.languages, ['english', 'spanish']);
    expect(c.books('spanish').map((b) => b.name), ['Libro Alfa', 'Libro Beta']);
    expect(c.volumes('spanish').first.name, 'Antiguo Testamento');
    expect(c.bookOfVerse(4)!.canonicalName, 'Alpha Book');
    expect(c.chapterOfVerse(4)!.chapter, 2);
    expect(c.bookOfVerse(999), isNull);
  });

  test('navigation crosses book boundaries from id ranges', () {
    final c = Catalog.load(makeCatalog(), contract: 'abc');
    expect(c.nextChapter(c.chapterOfVerse(5)!)!.bookId, 2);          // Alpha Book 2 -> Beta Book 1
    expect(c.previousChapter(c.chapterOfVerse(6)!)!.chapter, 2);     // Beta Book 1 -> Alpha Book 2
    expect(c.nextChapter(c.chapterOfVerse(8)!), isNull);
    expect(c.previousChapter(c.chapterOfVerse(1)!), isNull);
  });

  test('alias resolution: active language, then English, then other languages', () {
    final c = Catalog.load(makeCatalog(), contract: 'abc');
    expect(c.resolve('Alfa', language: 'spanish')!.canonicalName, 'Alpha Book');
    expect(c.resolve('alpha book', language: 'spanish')!.canonicalName, 'Alpha Book');  // English fallback
    expect(c.resolve('Libro Beta', language: 'english')!.canonicalName, 'Beta Book');   // other language
    expect(c.resolve('nonsense', language: 'spanish'), isNull);
  });

  test('a catalog built for a different verse-id contract is refused', () {
    expect(() => Catalog.load(makeCatalog(contract: 'zzz'), contract: 'abc'),
        throwsA(isA<ContentException>().having((e) => e.kind, 'kind', ContentErrorKind.wrongKind)));
  });
}
```

- [ ] **Step 4: Run to verify it fails**

Run: `flutter test test/data/catalog_test.dart`
Expected: FAIL (`catalog.dart` does not exist).

- [ ] **Step 5: Implement the reader**

`lib/data/content/catalog.dart`:

```dart
import 'package:sqlite3/sqlite3.dart';

import 'content_database.dart';

class VolumeEntry {
  VolumeEntry(this.id, this.key, this.name, this.shortName, this.source, this.firstVerseId, this.lastVerseId);
  final int id, firstVerseId, lastVerseId;
  final String key, name, source;
  final String? shortName;
}

class BookRef {
  BookRef(this.id, this.volumeId, this.canonicalName, this.firstVerseId, this.lastVerseId, this.chapterCount);
  final int id, volumeId, firstVerseId, lastVerseId, chapterCount;
  final String canonicalName;
}

class LocalizedBook {
  LocalizedBook(this.book, this.name, this.shortName, this.longName);
  final BookRef book;
  final String name, shortName;
  final String? longName;
}

class ChapterRange {
  ChapterRange(this.bookId, this.chapter, this.firstVerseId, this.lastVerseId);
  final int bookId, chapter, firstVerseId, lastVerseId;
}

/// Immutable, fully in-memory navigation and naming catalog. No SQL after load.
class Catalog {
  Catalog._(this.languages, this._books, this._chapters, this._names, this._volNames, this._aliases);

  final List<String> languages;
  final List<BookRef> _books;
  final List<ChapterRange> _chapters; // ordered by first verse id
  final Map<String, List<LocalizedBook>> _names;
  final Map<String, List<VolumeEntry>> _volNames;
  final Map<String, Map<String, int>> _aliases;

  static const _allowedLanguages = {'english', 'spanish', 'tagalog', 'cebuano', 'greek', 'french', 'german', 'hebrew'};

  /// [contract] is the content database's verse_order_sha256; a catalog built for another ID layout is refused.
  static Catalog load(String path, {required String contract}) {
    final db = sqlite3.open(path, mode: OpenMode.readOnly);
    try {
      final meta = {for (final r in db.select('SELECT key, value FROM catalog_meta')) r['key'] as String: r['value'] as String};
      if (meta['verse_order_sha256'] != contract) {
        throw ContentException(ContentErrorKind.wrongKind, 'Catalog was built for a different verse-id layout');
      }
      final languages = (meta['served_languages'] ?? '').split(',').where((l) => l.isNotEmpty).toList();
      final volumes = [for (final r in db.select('SELECT * FROM volumes ORDER BY sort_order')) r];
      final books = [
        for (final r in db.select('SELECT * FROM books ORDER BY sort_order'))
          BookRef(r['book_id'] as int, r['volume_id'] as int, r['canonical_name'] as String, r['first_verse_id'] as int,
              r['last_verse_id'] as int, r['chapter_count'] as int)
      ];
      final chapters = [
        for (final r in db.select('SELECT * FROM chapters ORDER BY first_verse_id'))
          ChapterRange(r['book_id'] as int, r['chapter'] as int, r['first_verse_id'] as int, r['last_verse_id'] as int)
      ];
      final byId = {for (final b in books) b.id: b};
      final names = <String, List<LocalizedBook>>{};
      final volNames = <String, List<VolumeEntry>>{};
      final aliases = <String, Map<String, int>>{};
      for (final l in languages) {
        if (!_allowedLanguages.contains(l)) {
          throw ContentException(ContentErrorKind.unsupportedLanguage, 'Unknown catalog language $l');
        }
        names[l] = [
          for (final r in db.select('SELECT * FROM book_names_$l ORDER BY book_id'))
            LocalizedBook(byId[r['book_id'] as int]!, r['name'] as String, r['short_name'] as String, r['long_name'] as String?)
        ];
        volNames[l] = [
          for (final v in volumes)
            for (final r in db.select('SELECT * FROM volume_names_$l WHERE volume_id = ?', [v['volume_id']]))
              VolumeEntry(v['volume_id'] as int, v['key'] as String, r['name'] as String, r['short_name'] as String?,
                  r['source'] as String, v['first_verse_id'] as int, v['last_verse_id'] as int)
        ];
        aliases[l] = {for (final r in db.select('SELECT alias, book_id FROM book_aliases_$l')) r['alias'] as String: r['book_id'] as int};
      }
      return Catalog._(languages, books, chapters, names, volNames, aliases);
    } on SqliteException catch (e) {
      throw ContentException(ContentErrorKind.notSqlite, 'Not a usable catalog: ${e.message}');
    } finally {
      db.dispose();
    }
  }

  List<LocalizedBook> books(String language) => _names[language] ?? _names['english']!;
  List<VolumeEntry> volumes(String language) => _volNames[language] ?? _volNames['english']!;

  BookRef? bookOfVerse(int verseId) {
    for (final b in _books) {
      if (verseId >= b.firstVerseId && verseId <= b.lastVerseId) return b;
    }
    return null;
  }

  ChapterRange? chapterOfVerse(int verseId) {
    for (final c in _chapters) {
      if (verseId >= c.firstVerseId && verseId <= c.lastVerseId) return c;
    }
    return null;
  }

  ChapterRange? nextChapter(ChapterRange c) {
    final i = _chapters.indexWhere((x) => x.firstVerseId == c.firstVerseId);
    return i >= 0 && i + 1 < _chapters.length ? _chapters[i + 1] : null;
  }

  ChapterRange? previousChapter(ChapterRange c) {
    final i = _chapters.indexWhere((x) => x.firstVerseId == c.firstVerseId);
    return i > 0 ? _chapters[i - 1] : null;
  }

  static String _fold(String s) => s.trim().toLowerCase().replaceAll('.', '').replaceAll(RegExp(r'\s+'), ' ');

  /// Active language first, then English, then every other catalog language.
  BookRef? resolve(String input, {required String language}) {
    final key = _fold(input);
    final order = [language, 'english', ...languages.where((l) => l != language && l != 'english')];
    for (final l in order) {
      final id = _aliases[l]?[key];
      if (id != null) return _books.firstWhere((b) => b.id == id);
    }
    return null;
  }
}
```

Wire into Task 5 when executing: `ContentRepository.listBooks()` and `resolveBook()` delegate to `Catalog`, and the hard-coded `_bookAliases` map is deleted. The Library screen in Task 9 groups books by `catalog.volumes(language)` and shows `book.name` in the active language.

- [ ] **Step 6: Run the tests**

Run: `flutter test test/data/catalog_test.dart`
Expected: PASS (4 tests).

- [ ] **Step 7: Commit**

```bash
git add tool/build_catalog_db.py tool/data test/build_catalog_db_check.py lib/data/content/catalog.dart test/data/catalog_test.dart
git commit -m "data: add language-specific catalog database and in-memory reader"
```

---

### Task 6c: Compact content database (schema v2) and one-command release build

**Status:** implemented, tested and run on the real data 2026-10-13. Dart layer migrated; 40 Flutter tests, analyzer clean.

**Why:** v1 repeated structure in every language table (book, chapter, verse, reference, shortened), carried 95 MB of
568-d vectors that the engine reads from its own native files, shipped three languages that are not served, and kept a
304,375-row per-verse provenance table. Measured with the real data, `chapter`, `verse`, `reference` and `shortened`
are exactly derivable from the catalog for all 209,975 served rows (0 mismatches), so the catalog is the single
structural authority.

**Layout** (`tool/build_content_v2.py`):

| Table | Contents |
|---|---|
| `content_meta` | `schema_version=2`, `kind=content`, served languages, `verse_order_sha256` contract, edition and source identities |
| `text_<language>` | `verse_id INTEGER PRIMARY KEY, text TEXT` for each served language only |
| `text_provenance` | `(language, first_verse_id, last_verse_id, source, quality_tier)`: 6 rows replace 304,375 |

Chapters are read as a primary-key range scan (`verse_id BETWEEN first AND last`) with bounds from the catalog;
book, chapter, verse number and localized references come from catalog binary searches (no SQL after load). The
repository refuses a catalog whose contract differs from the content database's.

**Equivalence proof built into the tool:** every v1 row (text, reference, shortened, book, chapter, verse) and every
per-verse provenance entry is reconstructed from v2 plus the catalog and compared; any difference aborts the build.

**One command** (`tool/build_release.py`, about 40 s, deterministic): pinned base + legacy KJV text + catalog data ->
KJV-switched intermediate -> `catalog.db` -> `content.db` -> `phrase-index.db` (FTS5, `columnsize=0`, optimized) ->
`manifest.json` (sizes, SHA-256, `content_contract`, edition and source hashes). Work files are always removed.

| File | v1 | v2 |
|---|---|---|
| Content database | 215.0 MB (34.4 MB compressed) | **42.1 MB (12.4 MB compressed)** |
| Catalog | 0.2 MB | 0.2 MB |
| Phrase index (5 languages) | not built | **17.5 MB** |
| Reading pack total | | **59.8 MB** |

Rebuilding from the same inputs gives byte-identical files (content `e5bd9372…`, catalog `3c61d48d…`, phrase `d045ade8…`).

Checks: `test/build_release_check.py` (v2 layout, equivalence refusal, manifest hashes, contract, KJV switched in,
phrase hits, work-dir cleanup, existing-output refusal), `test/build_catalog_db_check.py`,
`test/engine_capabilities_check.py` (reference round trip over all five languages and the committed goldens, now
against the v2 files), and `test/integration/real_release_test.dart` (install, contract, 87 books, 41,995 rows per
language, localized names).

Not changed: `scripture_vectors` and the three unserved languages stay in the pinned base and the research bundle;
the engine reads vectors from its own native files (ENGINE_PLAN).

---

### Task 7: `user.db`

**Status:** not executed (nothing in the current app depends on it yet).

**Files:**
- Create: `lib/data/user/user_database.dart`
- Test: `test/data/user_database_test.dart`

**Interfaces:**
- Produces:

```dart
class UserDatabase {
  static const currentVersion = 1;
  static UserDatabase open(String path, {required String corpusId});   // StateError on corpus mismatch
  void addBookmark(int verseId); void removeBookmark(int verseId); bool isBookmarked(int verseId);
  List<int> bookmarks();
  int addNote(int verseId, String body); List<UserNote> notesFor(int verseId);
  void setHighlight(int verseId, int color); int? highlightColor(int verseId);
  void setReadingPosition(int verseId); int? readingPosition();
  String? setting(String key); void putSetting(String key, String value);
  int get schemaVersion; void dispose();
}
class UserNote { int id; int verseId; String body; int createdAt; int updatedAt; }
```

- [ ] **Step 1: Write the failing tests**

`test/data/user_database_test.dart`:

```dart
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:scriptures_reader_mobile/data/user/user_database.dart';

String tempPath() => '${Directory.systemTemp.createTempSync().path}/user.db';

void main() {
  test('fresh database is created at the current schema version', () {
    final u = UserDatabase.open(tempPath(), corpusId: 'application-v1');
    addTearDown(u.dispose);
    expect(u.schemaVersion, UserDatabase.currentVersion);
    expect(u.setting('corpus_id'), 'application-v1');
  });

  test('bookmarks, notes, highlights and position persist across reopen', () {
    final path = tempPath();
    var u = UserDatabase.open(path, corpusId: 'application-v1');
    u.addBookmark(42);
    final id = u.addNote(42, 'a note with ¿accents? and Σύνθετο');
    u.setHighlight(42, 0xFFFFEB3B);
    u.setReadingPosition(42);
    u.dispose();

    u = UserDatabase.open(path, corpusId: 'application-v1');
    addTearDown(u.dispose);
    expect(u.isBookmarked(42), isTrue);
    expect(u.notesFor(42).single.body, 'a note with ¿accents? and Σύνθετο');
    expect(u.notesFor(42).single.id, id);
    expect(u.highlightColor(42), 0xFFFFEB3B);
    expect(u.readingPosition(), 42);
  });

  test('bookmarking twice is idempotent', () {
    final u = UserDatabase.open(tempPath(), corpusId: 'application-v1');
    addTearDown(u.dispose);
    u.addBookmark(7);
    u.addBookmark(7);
    expect(u.bookmarks(), [7]);
  });

  test('opening with a different corpus id is refused (IDs would be unverified)', () {
    final path = tempPath();
    UserDatabase.open(path, corpusId: 'application-v1').dispose();
    expect(() => UserDatabase.open(path, corpusId: 'application-v2'), throwsA(isA<StateError>()));
  });
}
```

- [ ] **Step 2: Run to verify it fails**

Run: `flutter test test/data/user_database_test.dart`
Expected: FAIL (`user_database.dart` does not exist).

- [ ] **Step 3: Implement**

`lib/data/user/user_database.dart`:

```dart
import 'package:sqlite3/sqlite3.dart';

class UserNote {
  UserNote(this.id, this.verseId, this.body, this.createdAt, this.updatedAt);
  final int id, verseId, createdAt, updatedAt;
  final String body;
}

/// Writable personal data. Never deleted by install or cleanup code.
class UserDatabase {
  UserDatabase._(this._db);
  final Database _db;

  static const currentVersion = 1;

  static const _migrations = <int, List<String>>{
    1: [
      'CREATE TABLE bookmarks (verse_id INTEGER PRIMARY KEY, created_at INTEGER NOT NULL)',
      'CREATE TABLE notes (id INTEGER PRIMARY KEY AUTOINCREMENT, verse_id INTEGER NOT NULL, body TEXT NOT NULL, '
          'created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL)',
      'CREATE INDEX notes_verse ON notes(verse_id)',
      'CREATE TABLE highlights (verse_id INTEGER PRIMARY KEY, color INTEGER NOT NULL, created_at INTEGER NOT NULL)',
      'CREATE TABLE reading_position (id INTEGER PRIMARY KEY CHECK(id = 1), verse_id INTEGER NOT NULL, '
          'updated_at INTEGER NOT NULL)',
      'CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)',
    ],
  };

  static UserDatabase open(String path, {required String corpusId}) {
    final db = sqlite3.open(path);
    db.execute('PRAGMA journal_mode = WAL');
    try {
      for (var v = db.userVersion + 1; v <= currentVersion; v++) {
        db.execute('BEGIN');
        try {
          for (final sql in _migrations[v]!) {
            db.execute(sql);
          }
          db.userVersion = v; // PRAGMA user_version inside the same transaction
          db.execute('COMMIT');
        } catch (_) {
          db.execute('ROLLBACK');
          rethrow;
        }
      }
      final u = UserDatabase._(db);
      final existing = u.setting('corpus_id');
      if (existing == null) {
        u.putSetting('corpus_id', corpusId);
      } else if (existing != corpusId) {
        throw StateError('user.db was written against corpus "$existing", not "$corpusId"; '
            'a verified ID migration is required before opening it');
      }
      return u;
    } catch (_) {
      db.dispose();
      rethrow;
    }
  }

  static int get _now => DateTime.now().millisecondsSinceEpoch;

  int get schemaVersion => _db.userVersion;

  void addBookmark(int verseId) => _db.execute('INSERT OR IGNORE INTO bookmarks VALUES (?, ?)', [verseId, _now]);
  void removeBookmark(int verseId) => _db.execute('DELETE FROM bookmarks WHERE verse_id = ?', [verseId]);
  bool isBookmarked(int verseId) => _db.select('SELECT 1 FROM bookmarks WHERE verse_id = ?', [verseId]).isNotEmpty;
  List<int> bookmarks() =>
      [for (final r in _db.select('SELECT verse_id FROM bookmarks ORDER BY created_at, verse_id')) r['verse_id'] as int];

  int addNote(int verseId, String body) {
    final t = _now;
    _db.execute('INSERT INTO notes (verse_id, body, created_at, updated_at) VALUES (?, ?, ?, ?)',
        [verseId, body, t, t]);
    return _db.lastInsertRowId;
  }

  List<UserNote> notesFor(int verseId) => [
        for (final r in _db.select('SELECT * FROM notes WHERE verse_id = ? ORDER BY id', [verseId]))
          UserNote(r['id'] as int, r['verse_id'] as int, r['body'] as String, r['created_at'] as int,
              r['updated_at'] as int)
      ];

  void setHighlight(int verseId, int color) => _db.execute(
      'INSERT INTO highlights VALUES (?, ?, ?) ON CONFLICT(verse_id) DO UPDATE SET color = excluded.color',
      [verseId, color, _now]);
  int? highlightColor(int verseId) {
    final r = _db.select('SELECT color FROM highlights WHERE verse_id = ?', [verseId]);
    return r.isEmpty ? null : r.first['color'] as int;
  }

  void setReadingPosition(int verseId) => _db.execute(
      'INSERT INTO reading_position VALUES (1, ?, ?) ON CONFLICT(id) DO UPDATE SET '
      'verse_id = excluded.verse_id, updated_at = excluded.updated_at',
      [verseId, _now]);
  int? readingPosition() {
    final r = _db.select('SELECT verse_id FROM reading_position WHERE id = 1');
    return r.isEmpty ? null : r.first['verse_id'] as int;
  }

  String? setting(String key) {
    final r = _db.select('SELECT value FROM settings WHERE key = ?', [key]);
    return r.isEmpty ? null : r.first['value'] as String;
  }

  void putSetting(String key, String value) => _db.execute(
      'INSERT INTO settings VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value', [key, value]);

  void dispose() => _db.dispose();
}
```

- [ ] **Step 4: Run the tests**

Run: `flutter test test/data/user_database_test.dart`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add lib/data/user/user_database.dart test/data/user_database_test.dart
git commit -m "data: add versioned writable user database"
```

---

### Task 8: `ReleaseStore` (verified import, atomic activation)

**Status:** executed 2026-10-13, 5 tests pass; also exercised against the real release by `test/integration/real_release_test.dart`.

**Files:**
- Create: `lib/services/artifacts/release_store.dart`
- Test: `test/services/release_store_test.dart`

**Interfaces:**
- Consumes: a release directory containing `manifest.json` (`{"release": "application-v1+kjv", "files": {"<name>": {"bytes": int, "sha256": "<hex>"}}}`), as written by `tool/build_kjv_content_db.py` (Task 6).
- Produces:

```dart
const requiredReleaseFiles = {'scriptures_genome.db', 'catalog.db'};
class ActiveRelease { String id; Directory dir; String path(String fileName); }
class ReleaseStore {
  ReleaseStore(Directory root);                       // <application-support>/scriptura
  ActiveRelease? active();                            // null when nothing is installed, active.json is damaged, or a file is missing/truncated
  Future<ActiveRelease> installFromDirectory(Directory source, {required Set<String> include});
}
class ReleaseException implements Exception { String code; String message; }  // manifest_missing, file_missing, size_mismatch, hash_mismatch
```

- [ ] **Step 1: Write the failing Dart tests**

`test/services/release_store_test.dart`:

```dart
import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:scriptures_reader_mobile/services/artifacts/release_store.dart';

Directory makeSource({bool corrupt = false}) {
  final d = Directory.systemTemp.createTempSync('src');
  final bytes = utf8.encode('hello content');
  File('${d.path}/scriptures_genome.db').writeAsBytesSync(corrupt ? utf8.encode('HELLO content') : bytes);
  File('${d.path}/manifest.json').writeAsStringSync(jsonEncode({
    'release': 'rel-1',
    'files': {
      'scriptures_genome.db': {'bytes': bytes.length, 'sha256': sha256.convert(bytes).toString()},
    },
  }));
  return d;
}

void main() {
  test('verified import is copied into a versioned directory and activated', () async {
    final store = ReleaseStore(Directory.systemTemp.createTempSync('root'));
    expect(store.active(), isNull);
    final rel = await store.installFromDirectory(makeSource(), include: {'scriptures_genome.db'});
    expect(rel.id, 'rel-1');
    expect(File(rel.path('scriptures_genome.db')).readAsStringSync(), 'hello content');
    expect(store.active()!.id, 'rel-1');
  });

  test('a corrupted file is rejected and the previous release stays active', () async {
    final store = ReleaseStore(Directory.systemTemp.createTempSync('root'));
    await store.installFromDirectory(makeSource(), include: {'scriptures_genome.db'});
    await expectLater(
      store.installFromDirectory(makeSource(corrupt: true), include: {'scriptures_genome.db'}),
      throwsA(isA<ReleaseException>().having((e) => e.code, 'code', 'hash_mismatch')),
    );
    expect(store.active()!.id, 'rel-1');
  });

  test('missing manifest and missing file have distinct codes', () async {
    final store = ReleaseStore(Directory.systemTemp.createTempSync('root'));
    final empty = Directory.systemTemp.createTempSync('empty');
    await expectLater(store.installFromDirectory(empty, include: {'x'}),
        throwsA(isA<ReleaseException>().having((e) => e.code, 'code', 'manifest_missing')));
    final src = makeSource();
    await expectLater(store.installFromDirectory(src, include: {'questions_genome.db'}),
        throwsA(isA<ReleaseException>().having((e) => e.code, 'code', 'file_missing')));
  });

  test('a damaged active.json reads as not installed rather than crashing', () {
    final root = Directory.systemTemp.createTempSync('root');
    File('${root.path}/active.json').writeAsStringSync('{not json');
    expect(ReleaseStore(root).active(), isNull);
  });

  test('active release whose file was truncated is treated as not installed', () async {
    final root = Directory.systemTemp.createTempSync('root');
    final store = ReleaseStore(root);
    final rel = await store.installFromDirectory(makeSource(), include: {'scriptures_genome.db'});
    File(rel.path('scriptures_genome.db')).writeAsBytesSync([1, 2, 3]);
    expect(store.active(), isNull);
  });
}
```

- [ ] **Step 2: Run to verify it fails**

Run: `flutter test test/services/release_store_test.dart`
Expected: FAIL (`release_store.dart` does not exist). `crypto` is already a project dependency.

- [ ] **Step 3: Implement `ReleaseStore`**

`lib/services/artifacts/release_store.dart`:

```dart
import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';

/// Files a usable release must contain: the derived content database (English text = KJV) and its catalog.
const requiredReleaseFiles = {'scriptures_genome.db', 'catalog.db'};

class ReleaseException implements Exception {
  ReleaseException(this.code, this.message);
  final String code, message;
  @override
  String toString() => 'ReleaseException($code): $message';
}

class ActiveRelease {
  ActiveRelease(this.id, this.dir);
  final String id;
  final Directory dir;
  String path(String fileName) => '${dir.path}/$fileName';
}

class ReleaseStore {
  ReleaseStore(this.root);
  final Directory root;

  File get _activeFile => File('${root.path}/active.json');

  /// Cheap check (existence + byte size recorded at install). Full hashing happens only at install.
  ActiveRelease? active() {
    try {
      final j = jsonDecode(_activeFile.readAsStringSync()) as Map<String, dynamic>;
      final id = j['release'] as String;
      final dir = Directory('${root.path}/content/$id');
      final files = (j['files'] as Map<String, dynamic>);
      for (final e in files.entries) {
        final f = File('${dir.path}/${e.key}');
        if (!f.existsSync() || f.lengthSync() != (e.value as Map)['bytes']) return null;
      }
      return ActiveRelease(id, dir);
    } catch (_) {
      return null;
    }
  }

  Future<String> _sha(File f) async => (await sha256.bind(f.openRead()).first).toString();

  Future<ActiveRelease> installFromDirectory(Directory source, {required Set<String> include}) async {
    final manifestFile = File('${source.path}/manifest.json');
    if (!manifestFile.existsSync()) {
      throw ReleaseException('manifest_missing', 'No manifest.json in ${source.path}');
    }
    final m = jsonDecode(manifestFile.readAsStringSync()) as Map<String, dynamic>;
    final id = m['release'] as String;
    final listed = (m['files'] as Map<String, dynamic>).cast<String, Map<String, dynamic>>();

    for (final name in include) {
      final entry = listed[name];
      final f = File('${source.path}/$name');
      if (entry == null || !f.existsSync()) {
        throw ReleaseException('file_missing', '$name is not in the import directory or its manifest');
      }
      if (f.lengthSync() != entry['bytes']) {
        throw ReleaseException('size_mismatch', '$name has ${f.lengthSync()} bytes, expected ${entry['bytes']}');
      }
      if (await _sha(f) != entry['sha256']) {
        throw ReleaseException('hash_mismatch', '$name failed SHA-256 verification');
      }
    }

    // Stage into a private directory, then rename into place; the active pointer flips last.
    final staging = Directory('${root.path}/staging/$id-${DateTime.now().microsecondsSinceEpoch}');
    staging.createSync(recursive: true);
    for (final name in include) {
      await File('${source.path}/$name').copy('${staging.path}/$name');
    }
    final finalDir = Directory('${root.path}/content/$id');
    finalDir.parent.createSync(recursive: true);
    if (finalDir.existsSync()) finalDir.deleteSync(recursive: true); // same release id re-import only
    staging.renameSync(finalDir.path);

    final pointer = File('${root.path}/active.json.tmp');
    pointer.writeAsStringSync(jsonEncode({
      'release': id,
      'files': {for (final n in include) n: {'bytes': File('${finalDir.path}/$n').lengthSync()}},
    }));
    pointer.renameSync(_activeFile.path); // atomic replace
    return ActiveRelease(id, finalDir);
  }
}
```

- [ ] **Step 4: Run all release tests**

Run: `flutter test test/services/release_store_test.dart`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add lib/services/artifacts/release_store.dart test/services/release_store_test.dart
git commit -m "data: install releases with verification and atomic activation"
```

---

### Task 9: Rewire startup and remove the legacy loaders (owner approval required)

**Status:** executed 2026-10-13 with owner approval. Removed `lib/database`, `lib/search_intelligence`, `lib/performance` and `test/benchmark_test.dart`; dropped `sqflite` and `dio`; `flutter analyze` reports no issues (was 38, 4 errors); all 27 Flutter tests pass. The search screen is now the library home; semantic search returns in Phase 5 behind the new engine.

**Files:**
- Modify: `lib/main.dart` (replace the downloader-driven `StartupScreen`)
- Modify: `lib/reader_mode/screens/reader_screen.dart` (read real passages)
- Replace: `lib/reader_mode/screens/search_screen.dart` (library home with language menu; the old pipeline UI is removed)
- Delete: `lib/database/`, `lib/search_intelligence/`
- Modify: `pubspec.yaml` (remove `sqflite`, `dio`)
- Test: `test/widget_test.dart`

**Interfaces:**
- Consumes: `ReleaseStore`, `requiredReleaseFiles`, `ContentDatabase`, `ContentRepository` (Tasks 4, 5, 8).
- Produces: `class ScripturesReaderApp extends StatelessWidget { const ScripturesReaderApp({required ContentRepository? repository}) }` (null shows the "not installed" screen); `LibraryScreen(repository)` with a language menu listing exactly `repository.servedLanguages`; `ReaderScreen(repository, book, chapter, language)`.

- [ ] **Step 1: Get the owner's approval to delete the legacy code**

The old code is recoverable from the baseline commit. The old search UI cannot compile today (`SearchPipeline` is undefined) and PLAN Phase 5 replaces it with the new engine seam. Do not proceed without a yes.

- [ ] **Step 2: Write the failing widget tests**

`test/widget_test.dart`:

```dart
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:scriptures_reader_mobile/data/content/content_database.dart';
import 'package:scriptures_reader_mobile/data/content/content_repository.dart';
import 'package:scriptures_reader_mobile/main.dart';

void main() {
  testWidgets('shows a clear message when no content release is installed', (tester) async {
    await tester.pumpWidget(const ScripturesReaderApp(repository: null));
    expect(find.textContaining('not installed'), findsOneWidget);
  });

  testWidgets('library lists books; a chapter shows real passage text', (tester) async {
    final db = ContentDatabase.open('test/fixtures/content_mini.db');
    addTearDown(db.dispose);
    await tester.pumpWidget(ScripturesReaderApp(repository: ContentRepository(db)));
    await tester.pumpAndSettle();

    expect(find.text('Alpha Book'), findsOneWidget);
    await tester.tap(find.text('Alpha Book'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Chapter 1'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Synthetic English passage 1.'), findsOneWidget);
  });

  testWidgets('language menu offers exactly the served (complete) languages', (tester) async {
    final db = ContentDatabase.open('test/fixtures/content_mini.db');
    addTearDown(db.dispose);
    await tester.pumpWidget(ScripturesReaderApp(repository: ContentRepository(db)));
    await tester.pumpAndSettle();

    await tester.tap(find.byIcon(Icons.language));
    await tester.pumpAndSettle();
    expect(find.text('English'), findsOneWidget);
    expect(find.text('Greek'), findsOneWidget);
    expect(find.text('Spanish'), findsOneWidget);
    expect(find.text('French'), findsNothing); // 5/8 in the fixture: not served

    await tester.tap(find.text('Spanish'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Alpha Book'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Chapter 1'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Pasaje sintético 1'), findsOneWidget);
  });
}
```

- [ ] **Step 3: Run to verify it fails**

Run: `flutter test test/widget_test.dart`
Expected: FAIL (`ScripturesReaderApp` has no `repository` parameter).

- [ ] **Step 4: Replace `main.dart`**

```dart
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:path_provider/path_provider.dart';

import 'data/content/content_database.dart';
import 'data/content/content_repository.dart';
import 'reader_mode/screens/search_screen.dart';
import 'services/artifacts/release_store.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final support = await getApplicationSupportDirectory();
  final store = ReleaseStore(Directory('${support.path}/scriptura'));
  ContentRepository? repo;
  final release = store.active();
  if (release != null) {
    ContentDatabase? content;
    try {
      content = ContentDatabase.open(release.path('scriptures_genome.db'));
      repo = ContentRepository(content);
    } on ContentException {
      content?.dispose();
      repo = null; // surfaced as "not installed"; never crash on a bad file
    }
  }
  runApp(ScripturesReaderApp(repository: repo));
}

class ScripturesReaderApp extends StatelessWidget {
  const ScripturesReaderApp({super.key, required this.repository});
  final ContentRepository? repository;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Scriptures Reader',
      theme: ThemeData(colorScheme: ColorScheme.fromSeed(seedColor: Colors.deepPurple), useMaterial3: true),
      darkTheme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.deepPurple, brightness: Brightness.dark),
        useMaterial3: true,
      ),
      themeMode: ThemeMode.system,
      home: repository == null ? const _NotInstalledScreen() : LibraryScreen(repository: repository!),
    );
  }
}

class _NotInstalledScreen extends StatelessWidget {
  const _NotInstalledScreen();
  @override
  Widget build(BuildContext context) {
    return const Scaffold(
      body: Center(
        child: Padding(
          padding: EdgeInsets.all(24),
          child: Text(
            'Scripture content is not installed.\n\n'
            'Import the application content pack to start reading. No data is downloaded automatically.',
            textAlign: TextAlign.center,
          ),
        ),
      ),
    );
  }
}
```

- [ ] **Step 5: Replace `search_screen.dart` with the library and make the reader read real data**

`lib/reader_mode/screens/search_screen.dart`:

```dart
import 'package:flutter/material.dart';

import '../../data/content/content_repository.dart';
import 'reader_screen.dart';

String _label(String language) => language[0].toUpperCase() + language.substring(1);

/// Home: books and chapters from the content repository. Semantic search returns in Phase 5 behind the new engine.
class LibraryScreen extends StatefulWidget {
  const LibraryScreen({super.key, required this.repository});
  final ContentRepository repository;

  @override
  State<LibraryScreen> createState() => _LibraryScreenState();
}

class _LibraryScreenState extends State<LibraryScreen> {
  String _language = 'english';

  @override
  Widget build(BuildContext context) {
    final books = widget.repository.listBooks();
    return Scaffold(
      appBar: AppBar(
        title: const Text('Library'),
        actions: [
          PopupMenuButton<String>(
            icon: const Icon(Icons.language),
            onSelected: (l) => setState(() => _language = l),
            itemBuilder: (_) => [
              for (final l in widget.repository.servedLanguages)
                PopupMenuItem(value: l, child: Text(_label(l))),
            ],
          ),
        ],
      ),
      body: ListView(
        children: [
          for (final b in books)
            ListTile(
              title: Text(b.name),
              subtitle: Text('${b.chapters} chapters'),
              onTap: () => Navigator.of(context).push(MaterialPageRoute(
                builder: (_) => _ChapterList(repository: widget.repository, book: b, language: _language),
              )),
            ),
        ],
      ),
    );
  }
}

class _ChapterList extends StatelessWidget {
  const _ChapterList({required this.repository, required this.book, required this.language});
  final ContentRepository repository;
  final BookEntry book;
  final String language;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(book.name)),
      body: ListView(
        children: [
          for (var c = 1; c <= book.chapters; c++)
            ListTile(
              title: Text('Chapter $c'),
              onTap: () => Navigator.of(context).push(MaterialPageRoute(
                builder: (_) => ReaderScreen(repository: repository, book: book.name, chapter: c, language: language),
              )),
            ),
        ],
      ),
    );
  }
}
```

In `reader_screen.dart`: change the widget fields to `final ContentRepository repository; final String book; final int chapter; final String language;` (default `'english'`), delete the hard-coded Psalm text block, and build the body from `repository.getChapter(book, chapter, language: language)`:

```dart
final passages = widget.repository.getChapter(widget.book, widget.chapter, language: widget.language);
// ...
child: SingleChildScrollView(
  padding: const EdgeInsets.all(20),
  child: SelectionArea(
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (final p in passages)
          Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: Text.rich(TextSpan(children: [
              TextSpan(text: '${p.verse} ', style: const TextStyle(fontWeight: FontWeight.bold)),
              TextSpan(text: p.text),
              if (p.isFallback) TextSpan(text: '  [${p.language}]', style: const TextStyle(fontStyle: FontStyle.italic)),
            ]), style: TextStyle(fontSize: 18 * _textScale, height: 1.8, color: _getTextColor())),
          ),
      ],
    ),
  ),
),
```

The app bar title becomes `'${widget.book} ${widget.chapter}'`.

- [ ] **Step 6: Delete the legacy code and dependencies**

Run:

```powershell
git rm -r lib/database lib/search_intelligence
flutter pub remove sqflite dio
flutter analyze
```

Expected: `flutter analyze` reports no errors (the four legacy errors are gone). `lib/performance/lru_cache.dart` is unreferenced and may be removed in the same commit.

- [ ] **Step 7: Run all tests**

Run: `flutter test`
Expected: PASS for the widget and all `test/data`, `test/services` suites. The old `test/benchmark_test.dart` exercises deleted legacy utilities; remove it in this commit if it fails to compile.

- [ ] **Step 8: Commit**

```bash
git add -A lib test pubspec.yaml pubspec.lock
git commit -m "data: boot from the verified content release; remove legacy loaders and search UI"
```

---

### Task 10: Static data-source gate

**Status:** executed 2026-10-13; `tool/check_data_sources.py` reports the project clean.

**Files:**
- Create: `tool/check_data_sources.py`
- Test: `test/data_sources_gate_check.py`

**Interfaces:**
- Produces: `check(root: Path) -> list[str]` returning violation strings (empty = clean); CLI exit code 0 only when clean.

- [ ] **Step 1: Write the failing test**

`test/data_sources_gate_check.py`:

```python
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tool'))
from check_data_sources import check  # noqa: E402

# 1) a synthetic project that references legacy resources is flagged
bad = Path(tempfile.mkdtemp())
(bad / 'lib').mkdir()
(bad / 'lib' / 'x.dart').write_text("final p = 'assets/resources/db/verse-embeddings.db';\n", 'utf-8')
(bad / 'pubspec.yaml').write_text('flutter:\n  assets:\n    - assets/resources/\n', 'utf-8')
v = check(bad)
assert any('x.dart' in s for s in v), v
assert any('pubspec.yaml' in s for s in v), v

# 2) the real project is clean
assert check(ROOT) == [], check(ROOT)
print('data sources gate: OK')
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -I test/data_sources_gate_check.py`
Expected: FAIL (`ModuleNotFoundError: check_data_sources`).

- [ ] **Step 3: Implement**

`tool/check_data_sources.py`:

```python
"""Fail if app code or pubspec can reach a legacy data source.

  .venv\\Scripts\\python.exe -I tool/check_data_sources.py
"""
import re
import sys
from pathlib import Path

FORBIDDEN = [
    r'assets/resources', r'legacy-quarantine',
    r'verse-embeddings\.db', r'verse_embeddings\.db', r'verse-graph\.db', r'search-graph\.db',
    r'concept-embeddings\.db', r'user-data\.db', r'model_quantized\.onnx',
    r'github\.com/chainuser1/scicp', r'releases/download',
    r'package:sqflite', r'package:dio',
]
PATTERN = re.compile('|'.join(FORBIDDEN))


def check(root):
    root = Path(root)
    out = []
    files = list((root / 'lib').rglob('*.dart')) if (root / 'lib').exists() else []
    if (root / 'pubspec.yaml').exists():
        files.append(root / 'pubspec.yaml')
    for f in files:
        for n, line in enumerate(f.read_text('utf-8', errors='replace').splitlines(), 1):
            m = PATTERN.search(line)
            if m:
                out.append(f'{f.relative_to(root).as_posix()}:{n}: references "{m.group(0)}"')
    if (root / 'assets' / 'resources').exists():
        out.append('assets/resources still exists (move it to legacy-quarantine, Task 2)')
    return out


if __name__ == '__main__':
    problems = check(Path(__file__).resolve().parent.parent)
    print('\n'.join(problems) if problems else 'data sources: clean')
    sys.exit(1 if problems else 0)
```

- [ ] **Step 4: Run it**

Run: `.venv\Scripts\python.exe -I test/data_sources_gate_check.py`
Expected: `data sources gate: OK` (after Tasks 2 and 9; before them the second assertion fails and lists exactly what is left to do).

- [ ] **Step 5: Run the whole suite and commit**

Run, in order: `.venv\Scripts\python.exe -I test/legacy_disposition_check.py`, `.venv\Scripts\python.exe -I test/fixture_content_check.py`, `.venv\Scripts\python.exe -I test/build_kjv_content_db_check.py`, `.venv\Scripts\python.exe -I test/data_sources_gate_check.py`, `flutter analyze`, `flutter test`.
Expected: every command succeeds.

```bash
git add tool/check_data_sources.py test/data_sources_gate_check.py
git commit -m "data: add static gate against legacy data sources"
```

---

## Distribution and the in-app downloader (Task 11; design only, deferred by the owner)

**Status (2026-10-13):** host chosen (Hugging Face, D8); setting up the repository, publishing and the downloader are deliberately deferred. Nothing below is implemented. Until then the app installs from a local release directory through `ReleaseStore` (Task 8). D9 (rights review before public hosting) still gates the first public upload.

Direction from the owner (2026-10-13): upload the final databases to a release location and have the app download them. This replaces the removed legacy downloader with one that is verified, resumable and consented. The install side already exists: the downloader only has to fill a staging directory and call `ReleaseStore.installFromDirectory` (Task 8), which verifies size and SHA-256, copies into a versioned directory and flips `active.json` last.

**Measured download sizes** (zlib level 6 on the real artifacts, 2026-10-13; estimates for items not measured):

| Pack | Contents | Raw | Download (est.) |
|---|---|---|---|
| Reading (required) | `scriptures_genome.db` (KJV) 215 MB → **34 MB** compressed; `catalog.db` 0.2 MB → 0.1 MB | 215 MB | **~35 MB** |
| Search (optional) | INT8 encoder 0.57 GB (compresses ~76% on a 200 MB sample); tokenizer, head, dense/genome/sparse indexes ~0.2 GB (FP16 vectors compress ~92%); ColBERT pack 3.33 GB FP16 (**92%**, effectively incompressible) | ~4.1 GB | **~3.7 GB** with FP16 ColBERT; **~2.4 GB** if INT8 ColBERT passes its quality gate (not yet evaluated) |
| Questions (optional) | `questions_genome.db` | 286 MB | ~50 MB (not measured) |

**Design rules**
1. **One immutable, versioned origin.** Assets are content-addressed (file name includes the SHA-256) so a release can never be half-replaced. A small `manifest.json` at a stable URL points to the current release.
2. **Integrity is not authenticity.** Hashes catch corruption; the manifest must also carry a signature (Ed25519) verified against a public key embedded in the app, otherwise whoever controls the host controls the content (PLAN 9).
3. **No credentials in the app.** Therefore the host must be anonymously readable, which is why D9 gates publication.
4. **Manifest extension** (additive to the current shape): per file `url`, `bytes`, `sha256`, `group` (`reading|search|questions`), `compressed_bytes`; release-level `min_app_version`, `content_contract.verse_order_sha256` (already present), `signature`.
5. **Resumable, bounded, cancellable.** HTTP Range resume bound to the expected hash; free-space check including staging and rollback; per-file progress; unreadable partials are discarded, never activated.
6. **Consent and clarity.** First run shows the sizes above, "Reading only" vs "Reading + smart search", a Wi-Fi recommendation, and what stays offline afterwards. No download starts without a tap.
7. **Rollback.** Keep the previous release until the new one has opened successfully once (PLAN 9 step 7).
8. **Per-language splitting is later.** The content DB already compresses to 34 MB for five languages, so splitting is not worth its complexity yet.

**Tasks (to be written step by step when this is picked up; D9 must be cleared before publishing):** manifest schema + signer tool (`tool/sign_release.py`) and verification in Dart; `ReleaseDownloader` (Range, resume, hash-while-streaming) feeding `installFromDirectory`; pack-aware first-run screen; offline-after-install test with networking disabled; publish script that uploads assets and the signed manifest.

## Verification against the real artifacts (after Task 9)

These prove the clean layer on the real corpus. All but the last item are asserted by `test/integration/real_release_test.dart` (skipped automatically when the release is not built); passing 2026-10-13.

- [x] (Task 6, done; the shipped layout is now Task 6c) The derived v1 intermediate passed `PRAGMA integrity_check`, differs from the pinned base only in English text, English provenance and metadata, and the base file hash is unchanged.
- [x] (Task 6b, done) `catalog.db` is in the release directory; its manifest entry and `content_contract.verse_order_sha256` equal the retrieval config's `47a72c00…db0f`.
- [x] Install it through `ReleaseStore.installFromDirectory(..., include: requiredReleaseFiles)` (`scriptures_genome.db` and `catalog.db`); expect no `hash_mismatch`/`size_mismatch` and a non-null `active()`.
- [x] `ContentRepository.servedLanguages` equals `['cebuano', 'english', 'greek', 'spanish', 'tagalog']`; `getPassage(1, language: 'french')` and `'hebrew'` raise `unsupportedLanguage`.
- [x] `listBooks()` returns 87 books, first `Genesis`, last `Articles of Faith`, 41,995 verses in total.
- [x] `getPassage(1)` reads "In the beginning God created the heaven and the earth." with source `kjv`; `getPassage(39194)` is `Doctrine and Covenants 64:7` with source `lds`; no English passage reports `nrsvue` or `ylt_fallback`.
- [x] `getChapter('Psalms', 23, language: 'tagalog')` returns every verse with no fallback flags.
- [ ] Search/display policy: the retrieval bundle's `scripture_text.jsonl` still differs from the shipped English text (it is the NRSVue/YLT mix used to build the indexes), and `tool/verify_artifacts.py` reports that difference as informational, not as an error.

## Deferred (not in this plan)

- Study-aid and AI-summary pack readers (D3, D4): need the rights audit and a provenance UI.
- Switchable alternate English editions (YLT, Rotherham): would need an overlay or per-edition derived databases; not required while KJV is the single English text. Ilocano/Waray are excluded until the model is trained on them (D7).
- French/German/Hebrew: appear automatically if a later release marks them complete.
- Hugging Face repository, signed manifest, publish script and resumable in-app downloader (Task 11): deferred by the owner.
- Phrase-search FTS5 indexes (PLAN 6.4): built from the shipped (KJV) English text in a separate plan; Task 4's FTS5 availability test is its precondition.
- Deleting the quarantined legacy files: owner decision after the recovery copy is re-verified.

## Self-review

- **Spec coverage:** authoritative DBs (Tasks 4, 5), legacy disposition (Tasks 1, 2, Part A), KJV English text and provenance (Task 6, D1), serve-what-is-complete (Tasks 4, 5, 9, D5, D6), user data (Task 7), verified/atomic install (Task 8), no legacy loader (Tasks 9, 10), rights gating (Global Constraints, D3, D4, D7). No uncovered requirement found.
- **Placeholders:** none; the conditional instructions in Task 4 Step 4 are tied to specific, testable failures.
- **Type consistency:** `ContentException`/`ContentErrorKind` and `completeLanguages` (Task 4) are used unchanged in Tasks 5 and 9; `ContentRepository(content)` matches between Tasks 5 and 9; `ReleaseStore.active()/installFromDirectory` and `requiredReleaseFiles` match between Tasks 8 and 9; the manifest shape produced by Task 6 is the one Task 8 consumes.
- **Implementation status (2026-10-13):** Tasks 1, 2, 3 (generator + fixture), 4, 5, 6, 6b, 8, 9 and 10 are executed and pass: `flutter analyze` clean, 27 Flutter tests, 8 real-release integration tests, and the Python checks. Task 7 (`user.db`) is the only unexecuted task. Known gaps: the repository does not yet delegate book listing and alias resolution to `Catalog`; the Library screen does not yet group by volume; there is no import/install UI beyond the "not installed" screen; app-interface strings are English only.
