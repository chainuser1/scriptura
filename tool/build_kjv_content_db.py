"""Build the clean content release: scriptures_genome.db with the English table's text switched to KJV (LDS edition).

  .venv\\Scripts\\python.exe -I tool/build_kjv_content_db.py BASE.db LEGACY_LDS.db OUT_DIR [--release ID]

Never modifies BASE or LEGACY. Writes OUT_DIR/scriptures_genome.db and OUT_DIR/manifest.json (same shape as
application_databases/manifest.json). Refuses to write when verse IDs or (book, chapter, verse) disagree, when any text
is empty, or when anything other than the intended columns differs between BASE and the result.

Changes (and only these):
  scriptures_english.scripture_text          <- KJV/LDS-edition text, all verses
  scripture_text_sources (lang='english')    <- source 'kjv' (Old/New Testament) or 'lds' (Book of Mormon, D&C, PGP)
  database_metadata                          <- + english_text_edition, derived_from_sha256, english_source_sha256, derived_with
The NRSVue/YLT text is NOT carried into the result (it stays only in the retrieval bundle used offline for indexes).
"""
import argparse
import hashlib
import json
import shutil
import sqlite3
import sys
from pathlib import Path

ALIASES = {'Song of Solomon': 'Song of Songs'}   # legacy book title -> corpus book name
BIBLE_VOLUMES = {1, 2}                            # Old Testament, New Testament
KNOWN_VOLUMES = {1, 2, 3, 4, 5}                   # + Book of Mormon, D&C, Pearl of Great Price
TOOL = 'tool/build_kjv_content_db.py'


def _sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 22), b''):
            h.update(chunk)
    return h.hexdigest()


def _ro(path):
    return sqlite3.connect(f'file:{Path(path).as_posix()}?mode=ro', uri=True)


def _digest(conn, table, skip_cols=()):
    cols = [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")') if r[1] not in skip_cols]
    sel = ', '.join(f'"{c}"' for c in cols)
    h = hashlib.sha256()
    n = 0
    for row in conn.execute(f'SELECT {sel} FROM "{table}" ORDER BY 1, 2' if len(cols) > 1 else f'SELECT {sel} FROM "{table}" ORDER BY 1'):
        h.update(repr(row).encode('utf-8'))
        n += 1
    return n, h.hexdigest()


def build(base_db, legacy_db, out_dir, release=None):
    out_dir = Path(out_dir)
    if out_dir.exists():
        raise FileExistsError(out_dir)
    base, legacy = _ro(base_db), _ro(legacy_db)

    rows = legacy.execute(
        'SELECT v.id, b.book_title, c.chapter_number, v.verse_number, v.scripture_text, b.volume_id '
        'FROM verses v JOIN chapters c ON c.id = v.chapter_id JOIN books b ON b.id = c.book_id ORDER BY v.id').fetchall()
    ref = {v: (b, c, vs) for v, b, c, vs in base.execute('SELECT verse_id, book, chapter, verse FROM scriptures_english')}
    if {r[0] for r in rows} != set(ref):
        raise ValueError(f'verse ids differ from base: legacy={len(rows)} base={len(ref)}')
    for vid, book, ch, vs, text, vol in rows:
        if not str(text).strip():
            raise ValueError(f'empty KJV text for verse id {vid}')
        if vol not in KNOWN_VOLUMES:
            raise ValueError(f'unknown volume_id {vol} for verse id {vid}')
        if ref[vid] != (ALIASES.get(book, book), ch, vs):
            raise ValueError(f'reference disagrees with base at verse id {vid}: legacy={(book, ch, vs)} base={ref[vid]}')

    app_release = dict(base.execute('SELECT key, value FROM database_metadata'))['application_release']
    release = release or f'{app_release}+kjv'
    base_sha, src_sha = _sha(base_db), _sha(legacy_db)

    out_dir.mkdir(parents=True)
    try:
        dest = out_dir / 'scriptures_genome.db'
        shutil.copyfile(base_db, dest)
        c = sqlite3.connect(dest)
        c.execute('PRAGMA journal_mode = DELETE')
        with c:
            c.executemany('UPDATE scriptures_english SET scripture_text = ? WHERE verse_id = ?',
                          [(text, vid) for vid, _b, _c, _v, text, _vol in rows])
            c.executemany("UPDATE scripture_text_sources SET source = ? WHERE verse_id = ? AND lang = 'english'",
                          [('kjv' if vol in BIBLE_VOLUMES else 'lds', vid) for vid, _b, _c, _v, _t, vol in rows])
            c.executemany('INSERT OR REPLACE INTO database_metadata VALUES (?, ?)', [
                ('application_release', release), ('english_text_edition', 'kjv-lds'),
                ('derived_from_sha256', base_sha), ('english_source_sha256', src_sha), ('derived_with', TOOL)])
        c.execute('VACUUM')
        c.close()

        # Self-check: nothing but the intended columns/rows may differ from BASE.
        r = _ro(dest)
        problems = []
        for (t,) in base.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
            if t == 'scriptures_english':
                if _digest(base, t, ('scripture_text',)) != _digest(r, t, ('scripture_text',)):
                    problems.append('scriptures_english: columns other than scripture_text changed')
            elif t == 'scripture_text_sources':
                a = _digest(base, t, ('source',)) if False else None  # source legitimately differs for english rows only
                other_b = base.execute("SELECT verse_id, lang, source, quality_tier FROM scripture_text_sources WHERE lang != 'english' ORDER BY 1, 2").fetchall()
                other_r = r.execute("SELECT verse_id, lang, source, quality_tier FROM scripture_text_sources WHERE lang != 'english' ORDER BY 1, 2").fetchall()
                if other_b != other_r:
                    problems.append('scripture_text_sources: non-English rows changed')
                tiers_b = base.execute("SELECT verse_id, quality_tier FROM scripture_text_sources WHERE lang = 'english' ORDER BY 1").fetchall()
                tiers_r = r.execute("SELECT verse_id, quality_tier FROM scripture_text_sources WHERE lang = 'english' ORDER BY 1").fetchall()
                if tiers_b != tiers_r:
                    problems.append('scripture_text_sources: english quality tiers changed')
            elif t == 'database_metadata':
                bm, rm = dict(base.execute('SELECT key, value FROM database_metadata')), dict(r.execute('SELECT key, value FROM database_metadata'))
                changed = {k for k in bm if rm.get(k) != bm[k]}
                if changed - {'application_release'}:
                    problems.append(f'database_metadata: unexpected changes {sorted(changed)}')
            elif _digest(base, t) != _digest(r, t):
                problems.append(f'{t}: content changed')
        if r.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            problems.append('integrity_check failed')
        r.close()
        if problems:
            raise ValueError('self-check failed: ' + '; '.join(problems))

        manifest = {'release': release, 'files': {'scriptures_genome.db': {'bytes': dest.stat().st_size, 'sha256': _sha(dest)}},
                    'english_text_edition': 'kjv-lds', 'derived_from_sha256': base_sha, 'english_source_sha256': src_sha}
        (out_dir / 'manifest.json').write_text(json.dumps(manifest, indent=1), 'utf-8')
    except BaseException:
        shutil.rmtree(out_dir, ignore_errors=True)  # never leave a partial release behind
        raise
    counts = {}
    for _v, _b, _c, _vs, _t, vol in rows:
        k = 'kjv' if vol in BIBLE_VOLUMES else 'lds'
        counts[k] = counts.get(k, 0) + 1
    return {'release': release, 'rows': len(rows), 'sources': counts, 'manifest': manifest}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('base')
    ap.add_argument('legacy')
    ap.add_argument('out_dir')
    ap.add_argument('--release', default=None)
    a = ap.parse_args()
    r = build(a.base, a.legacy, a.out_dir, a.release)
    print(f"built {r['release']}: {r['rows']} English passages switched to KJV/LDS text, sources {r['sources']} -> {a.out_dir}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
