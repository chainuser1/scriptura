"""Generate the synthetic test fixtures (PLAN 12.3): synthetic text, real schemas.

  test/fixtures/content_mini.db      v1-shaped derived content database (input of build_kjv/build_catalog/v2 checks)
  test/fixtures/content_v2_mini.db   schema v2 runtime content database built from it
  test/fixtures/catalog_mini.db      catalog built from it (english, spanish, greek complete; french 5/8 not served)

Book names differ per language on purpose so localization is actually exercised.
"""
import sqlite3
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_catalog_db  # noqa: E402
import build_content_v2  # noqa: E402

FIX = HERE.parent / 'test' / 'fixtures'
OUT = FIX / 'content_mini.db'

# (english canonical name, {language: (name, short name)}, verses per chapter)
BOOKS = [
    ('Alpha Book', {'english': ('Alpha Book', 'Alpha'), 'spanish': ('Libro Alfa', 'Alfa'),
                    'greek': ('Βιβλίο Άλφα', 'Άλφα'), 'french': ('Livre Alpha', 'Alpha')}, [3, 2]),
    ('Beta Book', {'english': ('Beta Book', 'Beta'), 'spanish': ('Libro Beta', 'Beta'),
                   'greek': ('Βιβλίο Βήτα', 'Βήτα'), 'french': ('Livre Bêta', 'Bêta')}, [3]),
]

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
    for bi, (_en, names, chapters) in enumerate(BOOKS):
        for ch, n in enumerate(chapters, 1):
            for v in range(1, n + 1):
                vid += 1
                yield vid, bi, names, ch, v


def build_v1():
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
        for vid, bi, names, ch, v in verses():
            if vid > limit:
                continue
            name, short = names[lang]
            c.execute(f'INSERT INTO scriptures_{lang} VALUES (?,?,?,?,?,?,?)',
                      (vid, mk(vid), f'{name} {ch}:{v}', f'{short} {ch}:{v}', name, ch, v))
            c.execute('INSERT INTO scripture_text_sources VALUES (?,?,?,?)', (vid, lang, source, 'core'))
        c.execute('INSERT INTO language_coverage VALUES (?,?,?,?,?,?)',
                  (lang, f'scriptures_{lang}', limit, 8, int(limit == 8), 'english'))
    c.commit()
    c.execute('VACUUM')
    c.close()


def build_derived():
    tmp = Path(tempfile.mkdtemp())
    lds = tmp / 'lds.db'
    c = sqlite3.connect(lds)
    c.executescript('''CREATE TABLE volumes(id INTEGER PRIMARY KEY, volume_title TEXT, volume_short_title TEXT);
        CREATE TABLE books(id INTEGER PRIMARY KEY, volume_id INTEGER, book_title TEXT, book_long_title TEXT);''')
    c.execute("INSERT INTO volumes VALUES (1,'Old Testament','OT'),(3,'Book of Mormon','BoM')")
    c.execute("INSERT INTO books VALUES (1,1,'Alpha Book','The Long Alpha'),(2,3,'Beta Book','The Long Beta')")
    c.commit()
    c.close()
    for p in (FIX / 'catalog_mini.db', FIX / 'content_v2_mini.db'):
        if p.exists():
            p.unlink()
    build_catalog_db.build(OUT, FIX / 'catalog_mini.db', lds, {}, {}, {'aliases': {'alpha': 'Alpha Book'}})
    build_content_v2.build(OUT, FIX / 'catalog_mini.db', FIX / 'content_v2_mini.db')


def main():
    build_v1()
    build_derived()
    for n in ('content_mini.db', 'content_v2_mini.db', 'catalog_mini.db'):
        print('wrote', FIX / n, (FIX / n).stat().st_size, 'bytes')


if __name__ == '__main__':
    main()
