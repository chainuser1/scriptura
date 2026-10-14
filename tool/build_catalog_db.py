"""Build catalog.db: volumes/books/chapters as verse-ID ranges, plus per-language names and aliases.

  .venv\\Scripts\\python.exe -I tool/build_catalog_db.py BASE.db OUT.db --legacy-lds LDS.db \\
      [--legacy-lang spanish=PATH ...] [--manual tool/data/catalog_manual.json] \\
      [--aliases tool/data/book_aliases_en.json] [--release-dir DIR]

Structure comes from the application database (verse IDs are contiguous per book and chapter). Names/short names are
read from each COMPLETE language's own table; volume grouping and long titles come from the legacy KJV/LDS database
(and the legacy per-language databases only where their book titles match the application DB at the same index).
Per-language tables use the same fixed allowlist as scriptures_<language>. Ambiguous aliases are dropped and recorded.
"""
import argparse
import hashlib
import json
import re
import shutil
import sqlite3
import struct
import sys
import unicodedata
from pathlib import Path

LANGS = ('english', 'spanish', 'tagalog', 'cebuano', 'greek', 'french', 'german', 'hebrew')  # SQL-safety allowlist
VOLUME_KEYS = {1: 'ot', 2: 'nt', 3: 'bom', 4: 'dc', 5: 'pgp'}
LEGACY_TITLE_ALIASES = {'song of solomon': 'song of songs'}
TOOL = 'tool/build_catalog_db.py'


def _sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 22), b''):
            h.update(chunk)
    return h.hexdigest()


def _ro(path):
    return sqlite3.connect(f'file:{Path(path).as_posix()}?mode=ro', uri=True)


def fold(s):
    s = unicodedata.normalize('NFC', s).lower().replace('—', '--').replace('’', "'")
    return re.sub(r'\s+', ' ', s).strip()


def norm_title(s):
    """Title comparison key: folds the one known legacy rename (Song of Solomon -> Song of Songs)."""
    s = fold(s)
    return LEGACY_TITLE_ALIASES.get(s, s)


def strip_marks(s):
    return unicodedata.normalize('NFC', ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn'))


def alias_variants(text):
    """Typing variants of one name: case/period/space folded, accent-stripped, and '1 jn' -> '1jn'."""
    base = fold(text).replace('.', '')  # typed aliases keep what the user types; no legacy-title folding
    base = re.sub(r'\s+', ' ', base).strip()
    out = {base, strip_marks(base)}
    for v in list(out):
        out.add(re.sub(r'^(\d)\s+', r'\1', v))
    return {v for v in out if v}


def verse_order_sha256(ids):
    return hashlib.sha256(struct.pack(f'<{len(ids)}q', *ids)).hexdigest()


def _structure(base):
    rows = base.execute('SELECT verse_id, book, chapter, verse FROM scriptures_english ORDER BY verse_id').fetchall()
    books, seen = [], set()
    for vid, book, ch, _v in rows:
        if not books or books[-1]['name'] != book:
            if book in seen:
                raise ValueError(f'book "{book}" is not contiguous in verse-id order (verse {vid})')
            seen.add(book)
            books.append({'name': book, 'first': vid, 'last': vid, 'chapters': {}})
        b = books[-1]
        if vid != b['last'] and vid != b['last'] + 1:
            raise ValueError(f'verse ids are not contiguous inside "{book}" at {vid}')
        b['last'] = vid
        c = b['chapters'].setdefault(ch, [vid, vid])
        if vid > c[1] + 1:
            raise ValueError(f'chapter {book} {ch} is not contiguous at {vid}')
        c[1] = vid
    for b in books:
        nums = sorted(b['chapters'])
        if nums != list(range(1, len(nums) + 1)):
            raise ValueError(f'chapters of "{b["name"]}" are not 1..n: {nums[:6]}')
    ids = [r[0] for r in rows]
    if len(ids) != len(set(ids)):
        raise ValueError('duplicate verse ids')
    return books, ids


def _language_names(base, lang, books):
    """name + short_name per book (by English ID range) from the language's own table."""
    rows = base.execute(f'SELECT verse_id, book, shortened FROM scriptures_{lang} ORDER BY verse_id').fetchall()
    by_id = {r[0]: (r[1], re.sub(r'\s+\d+:\d+$', '', r[2])) for r in rows}
    out = []
    for b in books:
        names, shorts = set(), set()
        for vid in range(b['first'], b['last'] + 1):
            if vid not in by_id:
                raise ValueError(f'{lang}: missing verse {vid} in range of {b["name"]}')
            names.add(by_id[vid][0])
            shorts.add(by_id[vid][1])
        if len(names) != 1 or len(shorts) != 1:
            raise ValueError(f'{lang}: "{b["name"]}" has inconsistent names {sorted(names)} / {sorted(shorts)}')
        out.append((names.pop(), shorts.pop()))
    if len(rows) != sum(b['last'] - b['first'] + 1 for b in books):
        raise ValueError(f'{lang}: verse count differs from English')
    return out


def build(base_db, out_path, legacy_lds, legacy_lang_dbs=None, manual=None, aliases_en=None):
    legacy_lang_dbs, manual, aliases_en = legacy_lang_dbs or {}, manual or {}, aliases_en or {}
    out_path = Path(out_path)
    if out_path.exists():
        raise FileExistsError(out_path)
    base = _ro(base_db)
    books, ids = _structure(base)

    cov = {r[0]: (r[1], r[2]) for r in base.execute('SELECT language, table_name, complete FROM language_coverage')}
    tables = {r[0] for r in base.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    served = [l for l in LANGS if l in cov and cov[l][1] == 1 and cov[l][0] in tables]
    if 'english' not in served:
        raise ValueError('english must be complete')

    # volume per book from the legacy LDS database, matched by index AND validated by title
    lds = _ro(legacy_lds)
    lb = lds.execute('SELECT id, volume_id, book_title, book_long_title FROM books ORDER BY id').fetchall()
    if len(lb) != len(books):
        raise ValueError(f'legacy lds has {len(lb)} books, application has {len(books)}')
    for i, (b, row) in enumerate(zip(books, lb)):
        if norm_title(row[2]) != norm_title(b['name']):
            raise ValueError(f'legacy lds book {i + 1} "{row[2]}" != application "{b["name"]}"')
        if row[1] not in VOLUME_KEYS:
            raise ValueError(f'unknown legacy volume id {row[1]}')
        b['volume'] = row[1]
        b['long_en'] = row[3]
    vols = []
    for b in books:
        if not vols or vols[-1]['id'] != b['volume']:
            if any(v['id'] == b['volume'] for v in vols):
                raise ValueError(f'volume {b["volume"]} is not contiguous')
            vols.append({'id': b['volume'], 'first': b['first'], 'last': b['last'], 'books': 0})
        vols[-1]['last'] = b['last']
        vols[-1]['books'] += 1
    lds_vols = {r[0]: (r[1], r[2]) for r in lds.execute('SELECT id, volume_title, volume_short_title FROM volumes')}

    # per-language names
    names = {lang: _language_names(base, lang, books) for lang in served}
    longs = {'english': [(b['long_en'], 'legacy_lds') for b in books]}
    legacy_volumes = {}
    for lang, path in legacy_lang_dbs.items():
        if lang not in served or lang == 'english':
            continue
        c = _ro(path)
        titles = c.execute('SELECT book_title, book_long_title FROM books ORDER BY id').fetchall()
        longs[lang] = [(t[1], f'legacy_{lang}') if i < len(titles) and norm_title(titles[i][0]) == norm_title(names[lang][i][0])
                       else (None, None) for i, t in enumerate(titles[:len(books)])] if len(titles) == len(books) else []
        legacy_volumes[lang] = {r[0]: (r[1], r[2]) for r in c.execute('SELECT id, volume_title, volume_short_title FROM volumes')}

    vkeys = {v['id']: VOLUME_KEYS[v['id']] for v in vols}
    vol_names = {}  # (lang, vid) -> (name, short, source, citation)
    for lang in served:
        for v in vols:
            key = vkeys[v['id']]
            en_name, en_short = lds_vols[v['id']]
            if lang == 'english':
                vol_names[(lang, v['id'])] = (en_name, en_short, 'legacy_lds', None)
                continue
            man = manual.get('volumes', {}).get(key, {}).get(lang)
            leg = legacy_volumes.get(lang, {}).get(v['id'])
            if man:
                vol_names[(lang, v['id'])] = (man['name'], man.get('short_name'), 'manual', man.get('citation'))
            elif v['books'] == 1:  # single-book volume: the book's own localized name is authoritative
                idx = next(i for i, b in enumerate(books) if b['volume'] == v['id'])
                vol_names[(lang, v['id'])] = (names[lang][idx][0], names[lang][idx][1], 'application_db', None)
            elif leg and norm_title(leg[0]) != norm_title(en_name):
                vol_names[(lang, v['id'])] = (leg[0], leg[1], f'legacy_{lang}', None)
            else:
                vol_names[(lang, v['id'])] = (en_name, en_short, 'fallback_en', None)

    # aliases per language
    alias_map, conflicts = {}, []
    for lang in served:
        m = {}
        for i, (name, short) in enumerate(names[lang]):
            for text in (name, short):
                for a in alias_variants(text):
                    m.setdefault(a, set()).add(i + 1)
        if lang == 'english':
            by_name = {norm_title(b['name']): i + 1 for i, b in enumerate(books)}
            for src in (aliases_en.get('aliases', aliases_en), manual.get('aliases', {}).get('english', {})):
                for alias, target in src.items():
                    if alias.startswith('_'):
                        continue
                    bid = by_name.get(norm_title(target))
                    if bid is None:
                        raise ValueError(f'alias "{alias}" targets unknown book "{target}"')
                    for a in alias_variants(alias):
                        m.setdefault(a, set()).add(bid)
        canonical = {a for i, (name, _s) in enumerate(names[lang]) for a in alias_variants(name)}
        keep = {}
        for a, bs in m.items():
            if len(bs) > 1:
                if a in canonical:
                    raise ValueError(f'{lang}: canonical name "{a}" is ambiguous: {sorted(bs)}')
                conflicts.append((lang, a, sorted(bs)))
            else:
                keep[a] = next(iter(bs))
        alias_map[lang] = keep

    # checks
    if sum(len(b['chapters']) for b in books) < len(books):
        raise ValueError('chapter count looks wrong')
    for lang in served:
        ns = [n for n, _s in names[lang]]
        if len(set(ns)) != len(ns) or not all(n.strip() for n in ns):
            raise ValueError(f'{lang}: book names are not unique and non-empty')

    tmp = out_path.with_suffix(out_path.suffix + '.tmp')
    if tmp.exists():
        tmp.unlink()
    c = sqlite3.connect(tmp)
    c.executescript('''
        CREATE TABLE catalog_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL) WITHOUT ROWID;
        CREATE TABLE volumes (volume_id INTEGER PRIMARY KEY, key TEXT NOT NULL UNIQUE, sort_order INTEGER NOT NULL,
            first_verse_id INTEGER NOT NULL, last_verse_id INTEGER NOT NULL, book_count INTEGER NOT NULL);
        CREATE TABLE books (book_id INTEGER PRIMARY KEY, volume_id INTEGER NOT NULL REFERENCES volumes(volume_id),
            canonical_name TEXT NOT NULL UNIQUE, sort_order INTEGER NOT NULL, first_verse_id INTEGER NOT NULL,
            last_verse_id INTEGER NOT NULL, chapter_count INTEGER NOT NULL, verse_count INTEGER NOT NULL);
        CREATE TABLE chapters (book_id INTEGER NOT NULL REFERENCES books(book_id), chapter INTEGER NOT NULL,
            first_verse_id INTEGER NOT NULL, last_verse_id INTEGER NOT NULL, PRIMARY KEY (book_id, chapter)) WITHOUT ROWID;
        CREATE TABLE catalog_coverage (language TEXT PRIMARY KEY, book_names INTEGER NOT NULL, volume_names INTEGER NOT NULL,
            aliases INTEGER NOT NULL, fallback_labels INTEGER NOT NULL, complete INTEGER NOT NULL) WITHOUT ROWID;
        CREATE TABLE alias_conflicts (language TEXT NOT NULL, alias TEXT NOT NULL, book_ids TEXT NOT NULL);
    ''')
    for i, v in enumerate(vols, 1):
        c.execute('INSERT INTO volumes VALUES (?,?,?,?,?,?)', (v['id'], vkeys[v['id']], i, v['first'], v['last'], v['books']))
    for i, b in enumerate(books, 1):
        c.execute('INSERT INTO books VALUES (?,?,?,?,?,?,?,?)',
                  (i, b['volume'], b['name'], i, b['first'], b['last'], len(b['chapters']), b['last'] - b['first'] + 1))
        for ch, (lo, hi) in sorted(b['chapters'].items()):
            c.execute('INSERT INTO chapters VALUES (?,?,?,?)', (i, ch, lo, hi))
    for lang in served:
        assert lang in LANGS  # table names come from the allowlist only
        c.execute(f'CREATE TABLE volume_names_{lang} (volume_id INTEGER PRIMARY KEY REFERENCES volumes(volume_id), '
                  'name TEXT NOT NULL, short_name TEXT, source TEXT NOT NULL, citation TEXT)')
        c.execute(f'CREATE TABLE book_names_{lang} (book_id INTEGER PRIMARY KEY REFERENCES books(book_id), '
                  'name TEXT NOT NULL UNIQUE, short_name TEXT NOT NULL, long_name TEXT, source TEXT NOT NULL, long_source TEXT)')
        c.execute(f'CREATE TABLE book_aliases_{lang} (alias TEXT PRIMARY KEY, book_id INTEGER NOT NULL REFERENCES books(book_id)) WITHOUT ROWID')
        fallbacks = 0
        for v in vols:
            n, s, src, cit = vol_names[(lang, v['id'])]
            fallbacks += src == 'fallback_en'
            c.execute(f'INSERT INTO volume_names_{lang} VALUES (?,?,?,?,?)', (v['id'], n, s, src, cit))
        lg = longs.get(lang, [])
        for i, (n, s) in enumerate(names[lang]):
            ln, ls = lg[i] if i < len(lg) else (None, None)
            c.execute(f'INSERT INTO book_names_{lang} VALUES (?,?,?,?,?,?)', (i + 1, n, s, ln or None, 'application_db', ls if ln else None))
        c.executemany(f'INSERT INTO book_aliases_{lang} VALUES (?,?)', sorted(alias_map[lang].items()))
        c.execute('INSERT INTO catalog_coverage VALUES (?,?,?,?,?,1)',
                  (lang, len(names[lang]), len(vols), len(alias_map[lang]), fallbacks))
    c.executemany('INSERT INTO alias_conflicts VALUES (?,?,?)', [(l, a, ','.join(map(str, b))) for l, a, b in conflicts])
    meta = {
        'schema_version': '1', 'built_with': TOOL, 'verse_count': str(len(ids)),
        'verse_order_sha256': verse_order_sha256(ids), 'base_db_file': Path(base_db).name, 'base_db_sha256': _sha(base_db),
        'legacy_lds_sha256': _sha(legacy_lds), 'served_languages': ','.join(served),
        'license_note': 'Names/labels only. Manual labels cite churchofjesuschrist.org pages in volume_names_<language>.citation.',
    }
    c.executemany('INSERT INTO catalog_meta VALUES (?,?)', sorted(meta.items()))
    c.commit()
    if c.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
        raise ValueError('catalog integrity_check failed')
    c.execute('VACUUM')
    c.close()
    base.close()
    lds.close()
    tmp.replace(out_path)
    return {'books': len(books), 'chapters': sum(len(b['chapters']) for b in books), 'volumes': len(vols),
            'languages': served, 'conflicts': conflicts, 'verse_order_sha256': meta['verse_order_sha256'],
            'aliases': {l: len(alias_map[l]) for l in served}}


def add_to_release(release_dir, catalog_path, contract):
    release_dir = Path(release_dir)
    mpath = release_dir / 'manifest.json'
    m = json.loads(mpath.read_text('utf-8'))
    dst = release_dir / 'catalog.db'
    shutil.copyfile(catalog_path, dst)
    m['files']['catalog.db'] = {'bytes': dst.stat().st_size, 'sha256': _sha(dst)}
    m['content_contract'] = {'verse_order_sha256': contract}
    mpath.write_text(json.dumps(m, indent=1), 'utf-8')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('base')
    ap.add_argument('out')
    ap.add_argument('--legacy-lds', required=True)
    ap.add_argument('--legacy-lang', action='append', default=[], help='language=path (repeatable)')
    root = Path(__file__).resolve().parent / 'data'
    ap.add_argument('--manual', default=str(root / 'catalog_manual.json'))
    ap.add_argument('--aliases', default=str(root / 'book_aliases_en.json'))
    ap.add_argument('--release-dir', default=None)
    a = ap.parse_args()
    lang_dbs = dict(x.split('=', 1) for x in a.legacy_lang)
    manual = json.loads(Path(a.manual).read_text('utf-8'))
    aliases = json.loads(Path(a.aliases).read_text('utf-8'))
    r = build(a.base, a.out, a.legacy_lds, lang_dbs, manual, aliases)
    print(f"catalog: {r['books']} books, {r['chapters']} chapters, {r['volumes']} volumes, languages {r['languages']}, "
          f"aliases {r['aliases']}, dropped ambiguous aliases: {len(r['conflicts'])}")
    if a.release_dir:
        add_to_release(a.release_dir, a.out, r['verse_order_sha256'])
        print('added catalog.db to', a.release_dir)
    return 0


if __name__ == '__main__':
    sys.exit(main())
