"""Checks for tool/build_kjv_content_db.py on the synthetic fixture (no scripture text involved).
Run: .venv\\Scripts\\python.exe -I test/build_kjv_content_db_check.py
"""
import hashlib
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tool'))
from build_kjv_content_db import build  # noqa: E402

BASE = ROOT / 'test' / 'fixtures' / 'content_mini.db'
tmp = Path(tempfile.mkdtemp())


def legacy(path, prefix, drop=(), book_alias=None):
    c = sqlite3.connect(path)
    c.executescript('''CREATE TABLE books(id INTEGER PRIMARY KEY, volume_id INTEGER, book_title TEXT);
        CREATE TABLE chapters(id INTEGER PRIMARY KEY, book_id INTEGER, chapter_number INTEGER);
        CREATE TABLE verses(id INTEGER PRIMARY KEY, chapter_id INTEGER, verse_number INTEGER, scripture_text TEXT);''')
    c.execute('INSERT INTO books VALUES (1, 1, ?), (2, 3, ?)', (book_alias or 'Alpha Book', 'Beta Book'))  # OT, Book of Mormon
    c.execute('INSERT INTO chapters VALUES (1,1,1),(2,1,2),(3,2,1)')
    for ch, ids in {1: [1, 2, 3], 2: [4, 5], 3: [6, 7, 8]}.items():
        for n, vid in enumerate(ids, 1):
            if vid not in drop:
                c.execute('INSERT INTO verses VALUES (?,?,?,?)', (vid, ch, n, f'{prefix} {vid}'))
    c.commit()
    c.close()


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


good = tmp / 'legacy_good.db'
legacy(good, 'KJV text')
base_sha = sha(BASE)
out = tmp / 'release'
r = build(BASE, good, out)

assert sha(BASE) == base_sha, 'the base database must never be modified'
assert r['release'] == 'fixture-v1+kjv' and r['rows'] == 8 and r['sources'] == {'kjv': 5, 'lds': 3}, r

c = sqlite3.connect(out / 'scriptures_genome.db')
assert c.execute('select scripture_text from scriptures_english where verse_id = 3').fetchone()[0] == 'KJV text 3'
assert c.execute('select count(*) from scriptures_english where scripture_text like ?', ('KJV text%',)).fetchone()[0] == 8
# NRSVue/synthetic base English text must not survive in the shipped English table
assert c.execute("select count(*) from scriptures_english where scripture_text like 'Synthetic%'").fetchone()[0] == 0
# other languages and vectors are byte-for-byte what the base had
b = sqlite3.connect(f'file:{BASE.as_posix()}?mode=ro', uri=True)
for t in ('scriptures_spanish', 'scriptures_greek', 'scriptures_french', 'scripture_vectors', 'language_coverage'):
    assert b.execute(f'select * from {t} order by 1').fetchall() == c.execute(f'select * from {t} order by 1').fetchall(), t
# provenance: Old Testament -> kjv, Book of Mormon -> lds, other languages untouched
src = dict(c.execute("select verse_id, source from scripture_text_sources where lang = 'english'"))
assert [src[i] for i in range(1, 9)] == ['kjv'] * 5 + ['lds'] * 3, src
assert c.execute("select source from scripture_text_sources where lang = 'spanish' and verse_id = 1").fetchone()[0] == 'synthetic_es'
meta = dict(c.execute('select key, value from database_metadata'))
assert meta['english_text_edition'] == 'kjv-lds' and meta['derived_from_sha256'] == base_sha and meta['application_release'] == 'fixture-v1+kjv'
assert c.execute('pragma integrity_check').fetchone()[0] == 'ok'
import json  # noqa: E402
m = json.loads((out / 'manifest.json').read_text('utf-8'))
assert m['files']['scriptures_genome.db']['sha256'] == sha(out / 'scriptures_genome.db')

# the Song of Solomon naming difference is accepted only as the known alias
legacy(tmp / 'legacy_alias.db', 'K', book_alias='Alpha Book')
for bad, why in ((tmp / 'legacy_holey.db', 'verse ids'), (tmp / 'legacy_ref.db', 'reference')):
    if bad.name == 'legacy_holey.db':
        legacy(bad, 'X', drop={4})
    else:
        legacy(bad, 'X', book_alias='Wrong Book')
    dest = tmp / ('out_' + bad.stem)
    try:
        build(BASE, bad, dest)
        raise AssertionError(f'{bad.name} must be refused')
    except ValueError as e:
        assert why in str(e).lower(), e
    assert not dest.exists(), 'no partial release may be left behind'

try:
    build(BASE, good, out)
    raise AssertionError('must refuse an existing output directory')
except FileExistsError:
    pass
print('build_kjv_content_db: OK')
