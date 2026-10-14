"""Checks for tool/build_catalog_db.py on the synthetic fixture.
Run: .venv\\Scripts\\python.exe -I test/build_catalog_db_check.py
"""
import hashlib
import shutil
import sqlite3
import struct
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tool'))
from build_catalog_db import alias_variants, build  # noqa: E402

BASE = ROOT / 'test' / 'fixtures' / 'content_mini.db'
tmp = Path(tempfile.mkdtemp())

# --- alias variant rules --------------------------------------------------------------------------------------------
assert alias_variants('Gén.') == {'gén', 'gen'}
assert alias_variants('1 Jn') == {'1 jn', '1jn'}
assert alias_variants('Song of Solomon') == {'song of solomon'}   # a typed alias is kept as typed (resolved via the alias maps)
assert alias_variants('D&C') == {'d&c'} and alias_variants('Joseph Smith—History') == {'joseph smith--history'}
assert 'ησαΐας' in alias_variants('Ησαΐας') and 'ησαιας' in alias_variants('Ησαΐας')


def legacy_lds(path, swap=False, same_volume=False):
    c = sqlite3.connect(path)
    c.executescript('''CREATE TABLE volumes(id INTEGER PRIMARY KEY, volume_title TEXT, volume_short_title TEXT);
        CREATE TABLE books(id INTEGER PRIMARY KEY, volume_id INTEGER, book_title TEXT, book_long_title TEXT);''')
    c.execute("INSERT INTO volumes VALUES (1,'Old Testament','OT'),(3,'Book of Mormon','BoM')")
    a, b = ('Beta Book', 'Alpha Book') if swap else ('Alpha Book', 'Beta Book')
    c.execute('INSERT INTO books VALUES (1,1,?,?),(2,?,?,?)', (a, 'The Long Alpha', 1 if same_volume else 3, b, 'The Long Beta'))
    c.commit()
    c.close()


def legacy_es(path, titles=('Libro Alfa', 'Libro Beta')):
    c = sqlite3.connect(path)
    c.executescript('''CREATE TABLE volumes(id INTEGER PRIMARY KEY, volume_title TEXT, volume_short_title TEXT);
        CREATE TABLE books(id INTEGER PRIMARY KEY, volume_id INTEGER, book_title TEXT, book_long_title TEXT);''')
    c.execute("INSERT INTO volumes VALUES (1,'Santa Biblia','Esp.'),(3,'Libro de Mormón','LM')")
    c.execute('INSERT INTO books VALUES (1,1,?,?),(2,3,?,?)', (titles[0], 'El Libro Largo Alfa', titles[1], 'El Libro Largo Beta'))
    c.commit()
    c.close()


lds, es = tmp / 'lds.db', tmp / 'es.db'
legacy_lds(lds)
legacy_es(es)
manual = {
    'volumes': {'ot': {'spanish': {'name': 'Antiguo Testamento', 'citation': 'https://example.test/ot'}}},
    'aliases': {'english': {'beta': 'Alpha Book'}},   # collides with Beta Book's short name 'Beta' -> must be dropped
}
aliases_en = {'aliases': {'alpha': 'Alpha Book', 'ab': 'Alpha Book'}}

out = tmp / 'catalog.db'
r = build(BASE, out, lds, {'spanish': es}, manual, aliases_en)
assert r['books'] == 2 and r['chapters'] == 3 and r['volumes'] == 2
assert r['languages'] == ['english', 'spanish', 'greek'], r['languages']   # french is 5/8: not catalogued
c = sqlite3.connect(out)
q = lambda sql, *a: c.execute(sql, a).fetchall()  # noqa: E731

# structure is pure verse-id ranges and covers 1..8 exactly once
assert q('select book_id, first_verse_id, last_verse_id, chapter_count, verse_count from books order by 1') == \
    [(1, 1, 5, 2, 5), (2, 6, 8, 1, 3)]
assert q('select book_id, chapter, first_verse_id, last_verse_id from chapters order by 1, 2') == \
    [(1, 1, 1, 3), (1, 2, 4, 5), (2, 1, 6, 8)]
assert q('select volume_id, key, first_verse_id, last_verse_id from volumes order by 1') == [(1, 'ot', 1, 5), (3, 'bom', 6, 8)]

# only complete languages get tables
tabs = {t for (t,) in q("select name from sqlite_master where type='table'")}
assert 'book_names_spanish' in tabs and 'book_names_greek' in tabs and 'book_names_french' not in tabs
assert q('select language, book_names, volume_names, complete from catalog_coverage order by 1') == \
    [('english', 2, 2, 1), ('greek', 2, 2, 1), ('spanish', 2, 2, 1)]

# volume labels: manual (cited) > legacy localized > single-book rule > English fallback (flagged)
assert q("select name, source, citation from volume_names_spanish where volume_id = 1") == \
    [('Antiguo Testamento', 'manual', 'https://example.test/ot')]
assert q("select name, source from volume_names_spanish where volume_id = 3")[0][1] in ('legacy_spanish', 'application_db')
# single-book volume: the book's own localized name is authoritative (D&C in the real data)
assert q("select name, source from volume_names_greek where volume_id = 1") == [('Βιβλίο Άλφα', 'application_db')]
assert q("select fallback_labels from catalog_coverage where language = 'greek'") == [(0,)]

# multi-book volume with no manual or localized label falls back to English and is flagged
legacy_lds(tmp / 'lds_one_volume.db', same_volume=True)
r2 = build(BASE, tmp / 'catalog2.db', tmp / 'lds_one_volume.db', {}, {}, {})
c2 = sqlite3.connect(tmp / 'catalog2.db')
assert c2.execute("select name, source from volume_names_greek where volume_id = 1").fetchall() == [('Old Testament', 'fallback_en')]
assert c2.execute("select fallback_labels from catalog_coverage where language = 'greek'").fetchall() == [(1,)]
assert c2.execute("select count(*) from volumes").fetchone()[0] == 1

# long titles only where the legacy title matched at the same index
assert q('select long_name, long_source from book_names_english where book_id = 1') == [('The Long Alpha', 'legacy_lds')]
assert q('select long_name, long_source from book_names_spanish where book_id = 1') == [('El Libro Largo Alfa', 'legacy_spanish')]

# aliases: names, short names, legacy and manual; ambiguous ones are dropped and recorded
al = dict(q('select alias, book_id from book_aliases_english'))
assert al['alpha book'] == 1 and al['alpha'] == 1 and al['ab'] == 1 and al['beta book'] == 2
assert 'beta' not in al
assert q("select language, alias, book_ids from alias_conflicts") == [('english', 'beta', '1,2')]

# contract + provenance
ids = list(range(1, 9))
meta = dict(q('select key, value from catalog_meta'))
assert meta['verse_order_sha256'] == hashlib.sha256(struct.pack('<8q', *ids)).hexdigest()
assert meta['served_languages'] == 'english,spanish,greek' and meta['verse_count'] == '8'
assert len(meta['base_db_sha256']) == 64 and meta['schema_version'] == '1'
assert q('pragma integrity_check') == [('ok',)]

# refusals: legacy books out of order, non-contiguous book in the base, existing output
legacy_lds(tmp / 'lds_swapped.db', swap=True)
for bad, why in ((tmp / 'lds_swapped.db', 'legacy lds book'),):
    try:
        build(BASE, tmp / 'x1.db', bad, {}, {}, {})
        raise AssertionError('must refuse mismatching legacy order')
    except ValueError as e:
        assert why in str(e), e
    assert not (tmp / 'x1.db').exists()

broken = tmp / 'base_broken.db'
shutil.copyfile(BASE, broken)
w = sqlite3.connect(broken)
w.execute("UPDATE scriptures_english SET book = 'Beta Book', chapter = 1, verse = 99 WHERE verse_id = 4")
w.commit()
w.close()
try:
    build(broken, tmp / 'x2.db', lds, {}, {}, {})
    raise AssertionError('must refuse a non-contiguous book')
except ValueError as e:
    assert 'contiguous' in str(e), e
assert not (tmp / 'x2.db').exists()

try:
    build(BASE, out, lds, {}, {}, {})
    raise AssertionError('must refuse an existing output file')
except FileExistsError:
    pass

# an unknown alias target in the data file is an error, not a silent drop
try:
    build(BASE, tmp / 'x3.db', lds, {}, {}, {'aliases': {'zz': 'No Such Book'}})
    raise AssertionError('unknown alias target must be refused')
except ValueError as e:
    assert 'unknown book' in str(e), e
print('build_catalog_db: OK')
