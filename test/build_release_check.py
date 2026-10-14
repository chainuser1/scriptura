"""Checks for tool/build_content_v2.py and tool/build_release.py on the synthetic fixtures.
Run: .venv\\Scripts\\python.exe -I test/build_release_check.py
"""
import hashlib
import json
import shutil
import sqlite3
import struct
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tool'))
import build_content_v2 as v2  # noqa: E402
import build_release as br  # noqa: E402

FIX = ROOT / 'test' / 'fixtures'
V1, CATALOG = FIX / 'content_mini.db', FIX / 'catalog_mini.db'
tmp = Path(tempfile.mkdtemp())


def ro(p):
    return sqlite3.connect(f'file:{Path(p).as_posix()}?mode=ro', uri=True)


# ---- build_content_v2 ------------------------------------------------------------------------------------------------
out = tmp / 'content.db'
r = v2.build(V1, CATALOG, out)
assert r['languages'] == {'english': 8, 'spanish': 8, 'greek': 8}, r         # french is 5/8: not carried over
c = ro(out)
tables = {t for (t,) in c.execute("select name from sqlite_master where type='table'")}
assert tables == {'content_meta', 'text_provenance', 'text_english', 'text_spanish', 'text_greek'}, tables
assert [x[1] for x in c.execute('pragma table_info(text_spanish)')] == ['verse_id', 'text']       # no derived columns
meta = dict(c.execute('select key, value from content_meta'))
assert meta['schema_version'] == '2' and meta['kind'] == 'content' and meta['served_languages'] == 'english,spanish,greek'
assert meta['verse_order_sha256'] == hashlib.sha256(struct.pack('<8q', *range(1, 9))).hexdigest()
assert c.execute('select count(*) from text_provenance').fetchone()[0] == 3                        # one run per language
assert c.execute('pragma user_version').fetchone()[0] == 2
assert c.execute('pragma integrity_check').fetchone()[0] == 'ok'
assert c.execute('select text from text_spanish where verse_id = 2').fetchone()[0] == 'Pasaje sintético 2: ¿cómo estás?'

# refuses when v2 would not be equivalent to v1 (a localized reference that the catalog cannot reproduce)
bad = tmp / 'v1_tampered.db'
shutil.copyfile(V1, bad)
w = sqlite3.connect(bad)
w.execute("UPDATE scriptures_spanish SET reference = 'Otro Libro 1:1' WHERE verse_id = 1")
w.commit()
w.close()
try:
    v2.build(bad, CATALOG, tmp / 'x.db')
    raise AssertionError('tampered v1 must be refused')
except ValueError as e:
    assert 'not equivalent' in str(e), e
assert not (tmp / 'x.db').exists() and not (tmp / 'x.db.tmp').exists()
try:
    v2.build(V1, CATALOG, out)
    raise AssertionError('must refuse an existing output')
except FileExistsError:
    pass

# ---- build_release ----------------------------------------------------------------------------------------------------
lds = tmp / 'lds.db'
l = sqlite3.connect(lds)
l.executescript('''CREATE TABLE volumes(id INTEGER PRIMARY KEY, volume_title TEXT, volume_short_title TEXT);
    CREATE TABLE books(id INTEGER PRIMARY KEY, volume_id INTEGER, book_title TEXT, book_long_title TEXT);''')
l.execute("INSERT INTO volumes VALUES (1,'Old Testament','OT'),(3,'Book of Mormon','BoM')")
l.execute("INSERT INTO books VALUES (1,1,'Alpha Book','Long A'),(2,3,'Beta Book','Long B')")
l.commit()
l.close()
# the KJV build needs verse ids and (book, chapter, verse) to match: give it a legacy text DB for the 8 verses
kjv = tmp / 'kjv_src.db'
k = sqlite3.connect(kjv)
k.executescript('''CREATE TABLE books(id INTEGER PRIMARY KEY, volume_id INTEGER, book_title TEXT, book_long_title TEXT);
    CREATE TABLE chapters(id INTEGER PRIMARY KEY, book_id INTEGER, chapter_number INTEGER);
    CREATE TABLE verses(id INTEGER PRIMARY KEY, chapter_id INTEGER, verse_number INTEGER, scripture_text TEXT);
    CREATE TABLE volumes(id INTEGER PRIMARY KEY, volume_title TEXT, volume_short_title TEXT);''')
k.execute("INSERT INTO volumes VALUES (1,'Old Testament','OT'),(3,'Book of Mormon','BoM')")
k.execute("INSERT INTO books VALUES (1,1,'Alpha Book','Long A'),(2,3,'Beta Book','Long B')")
k.execute('INSERT INTO chapters VALUES (1,1,1),(2,1,2),(3,2,1)')
for ch, ids in {1: [1, 2, 3], 2: [4, 5], 3: [6, 7, 8]}.items():
    for n, vid in enumerate(ids, 1):
        k.execute('INSERT INTO verses VALUES (?,?,?,?)', (vid, ch, n, f'KJV text {vid}'))
k.commit()
k.close()

rel = tmp / 'release'
m = br.build_release(V1, kjv, {}, rel, manual={}, aliases={'aliases': {}})
assert set(m['files']) == {'content.db', 'catalog.db', 'phrase-index.db'}
for name, e in m['files'].items():
    p = rel / name
    assert p.stat().st_size == e['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest() == e['sha256'], name
assert m['content_contract']['verse_order_sha256'] == meta['verse_order_sha256']
assert m['served_languages'] == ['english', 'spanish', 'greek'] and m['rows'] == {'english': 8, 'spanish': 8, 'greek': 8}
final = ro(rel / 'content.db')
assert final.execute('select text from text_english where verse_id = 3').fetchone()[0] == 'KJV text 3'        # KJV switched in
assert dict(final.execute("select key, value from content_meta"))['english_text_edition'] == 'kjv-lds'
assert [r[0] for r in final.execute("select source from text_provenance where language='english' order by first_verse_id")] == ['kjv', 'lds']
pi = ro(rel / 'phrase-index.db')
assert [r[0] for r in pi.execute('select rowid from phrase_english where phrase_english match \'"kjv text 3"\'')] == [3]
assert not (tmp / 'release.work').exists(), 'work directory must be cleaned up'
try:
    br.build_release(V1, kjv, {}, rel, manual={}, aliases={'aliases': {}})
    raise AssertionError('must refuse an existing release directory')
except FileExistsError:
    pass
print('build_release: OK')
