"""Build the compact runtime content database (schema v2) from the derived KJV database and the catalog.

v1 (`scriptures_genome.db`) repeats book/chapter/verse/reference/shortened in every language table, carries 95 MB of
568-d vectors that the engine reads from its own native files, ships three languages that are not served, and a
304k-row per-verse provenance table. v2 keeps only what the reader needs, with the catalog as the single structural
authority:

  content_meta(key, value)                         identity, contract, served languages
  text_<language>(verse_id INTEGER PRIMARY KEY, text TEXT NOT NULL)     one table per COMPLETE language
  text_provenance(language, first_verse_id, last_verse_id, source, quality_tier)   range table (a handful of rows)

Everything else (book, chapter, verse number, localized reference, short reference) is derived from catalog.db by
verse-id ranges. The build proves this: it reconstructs every v1 row (text, reference, shortened, book, chapter, verse)
for every served language from v2 + catalog and refuses to write unless all of them match.

  .venv\\Scripts\\python.exe -I tool/build_content_v2.py V1.db CATALOG.db OUT.db
"""
import argparse
import bisect
import hashlib
import sqlite3
import sys
from pathlib import Path

LANGS = ('english', 'spanish', 'tagalog', 'cebuano', 'greek', 'french', 'german', 'hebrew')  # SQL-safety allowlist
TOOL = 'tool/build_content_v2.py'


def _sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 22), b''):
            h.update(chunk)
    return h.hexdigest()


def _ro(path):
    return sqlite3.connect(f'file:{Path(path).as_posix()}?mode=ro', uri=True)


def provenance_ranges(v1, lang):
    """Collapse the per-verse source rows into consecutive (source, tier) runs."""
    runs = []
    for vid, src, tier in v1.execute('SELECT verse_id, source, quality_tier FROM scripture_text_sources WHERE lang = ? ORDER BY verse_id', (lang,)):
        if runs and runs[-1][2] == src and runs[-1][3] == tier and runs[-1][1] + 1 == vid:
            runs[-1][1] = vid
        else:
            runs.append([vid, vid, src, tier])
    return runs


def build(v1_db, catalog_db, out_db):
    out_db = Path(out_db)
    if out_db.exists():
        raise FileExistsError(out_db)
    v1, cat = _ro(v1_db), _ro(catalog_db)
    meta1 = dict(v1.execute('SELECT key, value FROM database_metadata'))
    cmeta = dict(cat.execute('SELECT key, value FROM catalog_meta'))
    served = [l for l in cmeta['served_languages'].split(',') if l]
    cov = {r[0]: (r[1], r[2]) for r in v1.execute('SELECT language, table_name, complete FROM language_coverage')}
    for lang in served:
        if lang not in LANGS or lang not in cov or cov[lang][1] != 1:
            raise ValueError(f'{lang}: catalog serves it but the content database does not declare it complete')

    # structure from the catalog (the single authority)
    chapters = cat.execute('SELECT c.book_id, c.chapter, c.first_verse_id, c.last_verse_id FROM chapters c ORDER BY c.first_verse_id').fetchall()
    firsts = [c[2] for c in chapters]
    names = {l: dict(cat.execute(f'SELECT book_id, name FROM book_names_{l}')) for l in served}
    shorts = {l: dict(cat.execute(f'SELECT book_id, short_name FROM book_names_{l}')) for l in served}
    book_name_en = dict(cat.execute('SELECT book_id, canonical_name FROM books'))

    tmp = out_db.with_suffix(out_db.suffix + '.tmp')
    if tmp.exists():
        tmp.unlink()
    o = sqlite3.connect(tmp)
    o.execute('PRAGMA page_size = 4096')
    o.execute('PRAGMA journal_mode = DELETE')
    o.execute('CREATE TABLE content_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL) WITHOUT ROWID')
    o.execute('CREATE TABLE text_provenance (language TEXT NOT NULL, first_verse_id INTEGER NOT NULL, last_verse_id INTEGER NOT NULL, '
              'source TEXT NOT NULL, quality_tier TEXT NOT NULL, PRIMARY KEY (language, first_verse_id)) WITHOUT ROWID')
    counts = {}
    for lang in served:
        o.execute(f'CREATE TABLE text_{lang} (verse_id INTEGER PRIMARY KEY, text TEXT NOT NULL CHECK (length(trim(text)) > 0))')
        rows = v1.execute(f'SELECT verse_id, scripture_text FROM {cov[lang][0]} ORDER BY verse_id').fetchall()
        o.executemany(f'INSERT INTO text_{lang} VALUES (?, ?)', rows)
        counts[lang] = len(rows)
        o.executemany('INSERT INTO text_provenance VALUES (?,?,?,?,?)', [(lang, a, b, s, t) for a, b, s, t in provenance_ranges(v1, lang)])
    o.executemany('INSERT INTO content_meta VALUES (?,?)', sorted({
        'schema_version': '2', 'kind': 'content', 'application_release': meta1['application_release'],
        'english_text_edition': meta1.get('english_text_edition', ''), 'served_languages': ','.join(served),
        'verse_order_sha256': cmeta['verse_order_sha256'], 'verse_count': cmeta['verse_count'],
        'derived_from_sha256': _sha(v1_db), 'catalog_base_sha256': cmeta.get('base_db_sha256', ''), 'built_with': TOOL,
    }.items()))
    o.execute('PRAGMA user_version = 2')
    o.commit()
    o.execute('VACUUM')
    o.close()

    # equivalence proof: rebuild every v1 row from v2 + catalog and compare
    r = _ro(tmp)
    problems = []
    ranges = {}
    for lang_, a, b, src, tier in r.execute('SELECT language, first_verse_id, last_verse_id, source, quality_tier FROM text_provenance'):
        ranges.setdefault(lang_, []).append((a, b, src, tier))
    for lang in served:
        v2 = dict(r.execute(f'SELECT verse_id, text FROM text_{lang}'))
        n = 0
        for vid, text, ref, short, book, ch, vs in v1.execute(
                f'SELECT verse_id, scripture_text, reference, shortened, book, chapter, verse FROM {cov[lang][0]}'):
            i = bisect.bisect_right(firsts, vid) - 1
            bid, cn, lo, hi = chapters[i]
            n += 1
            ok = (lo <= vid <= hi and v2.get(vid) == text and cn == ch and vid - lo + 1 == vs and book == names[lang][bid]
                  and ref == f'{names[lang][bid]} {cn}:{vs}' and short == f'{shorts[lang][bid]} {cn}:{vs}')
            if not ok:
                problems.append((lang, vid))
        if n != counts[lang] or len(v2) != n:
            problems.append((lang, 'row count'))
        # provenance ranges must expand to exactly the per-verse rows of v1
        expanded = {}
        for a, b, src, tier in ranges.get(lang, []):
            for vid in range(a, b + 1):
                expanded[vid] = (src, tier)
        v1_prov = {vid: (src, tier) for vid, src, tier in
                   v1.execute('SELECT verse_id, source, quality_tier FROM scripture_text_sources WHERE lang = ?', (lang,))}
        if expanded != v1_prov:
            problems.append((lang, 'provenance'))
    r.close()
    v1.close()
    cat.close()
    if problems:
        tmp.unlink()
        raise ValueError(f'v2 is not equivalent to v1: {problems[:5]} ({len(problems)} problems)')
    tmp.replace(out_db)
    return {'bytes': out_db.stat().st_size, 'languages': counts}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('v1')
    ap.add_argument('catalog')
    ap.add_argument('out')
    a = ap.parse_args()
    r = build(a.v1, a.catalog, a.out)
    print(f"built {a.out}: {r['bytes'] / 1e6:.1f} MB, rows {r['languages']}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
