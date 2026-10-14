"""Checks for the engine reference capabilities: phrase search, reference parsing, similar verses, identity.
Fixture section always runs; the real-data section runs when the local release is built.

  .venv\\Scripts\\python.exe -I test/engine_capabilities_check.py [--update-golden]
"""
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tool'))
import build_catalog_db  # noqa: E402
import config_identity as ci  # noqa: E402
import phrase_search as ps  # noqa: E402
import reference_parser as rp  # noqa: E402
import similar_verses as sv  # noqa: E402

UPDATE = '--update-golden' in sys.argv
FIXTURE = ROOT / 'test' / 'fixtures' / 'content_mini.db'
RELEASE_DIR = ROOT / 'generated-artifacts' / 'release'
RELEASE = RELEASE_DIR / 'content.db'
CATALOG = RELEASE_DIR / 'catalog.db'
PHRASE_DB = RELEASE_DIR / 'phrase-index.db'
GOLDEN = ROOT / 'test' / 'golden' / 'engine_capabilities.json'
tmp = Path(tempfile.mkdtemp())


def raises(code, fn, *a, **k):
    try:
        fn(*a, **k)
    except ps.PhraseError as e:
        assert e.code == code, (e.code, code)
        return
    raise AssertionError(f'expected PhraseError({code})')


# ---- phrase search on the synthetic fixture ------------------------------------------------------------------------
built = ps.build_index(FIXTURE, tmp / 'phrase.db')
assert dict(built) == {'english': 8, 'spanish': 8, 'greek': 8}, built        # french is 5/8: not indexed
db = sqlite3.connect(tmp / 'phrase.db')
S = lambda phrase, lang='english', **k: ps.search(db, phrase, lang, **k)  # noqa: E731

assert S('synthetic english passage 3')['verse_ids'] == [3]
assert S('english passage')['total'] == 8 and S('english passage', top_k=3)['verse_ids'] == [1, 2, 3]
assert S('english passage', top_k=3)['truncated'] is True
assert S('passage english')['total'] == 0                      # consecutive and in order
assert S('SYNTHETIC English')['total'] == 8                    # case-insensitive
assert S('english AND passage')['total'] == 0                  # operator WORDS are searched as words
assert S('passage*')['total'] == 8 and S('^synthetic')['total'] == 8   # operator CHARACTERS are plain punctuation
assert S('english -passage')['total'] == 8 and S('english NEAR passage')['total'] == 0
assert S('"synthetic"')['total'] == 8                          # embedded quotes do not break the query
assert S('sintético', 'spanish')['total'] == 8                 # accents preserved...
assert S('sintetico', 'spanish')['total'] == 0                 # ...so the unaccented form does not match
assert S('¿cómo estás?', 'spanish')['total'] == 8              # punctuation outside words is ignored
assert S('Σύνθετο κείμενο 2', 'greek')['verse_ids'] == [2]
assert S('english passage', allowed_verse_ids={2, 4, 99})['verse_ids'] == [2, 4]
raises('invalid_input', S, '')
raises('invalid_input', S, '   ')
raises('invalid_input', S, '?!...')
raises('unsupported_language', S, 'passage', 'french')         # partial language is not served
raises('unsupported_language', S, 'passage', 'klingon')
# NFD input matches NFC text
import unicodedata  # noqa: E402
assert S(unicodedata.normalize('NFD', 'sintético'), 'spanish')['total'] == 8

# ---- reference parsing on a synthetic catalog -----------------------------------------------------------------------
def legacy_lds(path):
    c = sqlite3.connect(path)
    c.executescript('''CREATE TABLE volumes(id INTEGER PRIMARY KEY, volume_title TEXT, volume_short_title TEXT);
        CREATE TABLE books(id INTEGER PRIMARY KEY, volume_id INTEGER, book_title TEXT, book_long_title TEXT);''')
    c.execute("INSERT INTO volumes VALUES (1,'Old Testament','OT'),(3,'Book of Mormon','BoM')")
    c.execute("INSERT INTO books VALUES (1,1,'Alpha Book','Long A'),(2,3,'Beta Book','Long B')")
    c.commit()
    c.close()


legacy_lds(tmp / 'lds.db')
build_catalog_db.build(FIXTURE, tmp / 'catalog.db', tmp / 'lds.db', {}, {}, {'aliases': {'alpha': 'Alpha Book', 'ab': 'Alpha Book'}})
cat = rp.Catalog(tmp / 'catalog.db')
P = lambda t, lang='english': rp.parse(cat, t, lang)  # noqa: E731

r = P('Alpha Book 1:2')
assert (r['status'], r['kind'], r['first_verse_id'], r['last_verse_id'], r['chapter'], r['verse']) == ('ok', 'verse', 2, 2, 1, 2)
r = P('  ALPHA   Book 1 : 2 ')
assert r['status'] == 'ok' and r['first_verse_id'] == 2
assert (P('alpha 2:1-2')['first_verse_id'], P('alpha 2:1-2')['last_verse_id'], P('alpha 2:1-2')['kind']) == (4, 5, 'range')
assert (P('Alpha 1:3-2:1')['first_verse_id'], P('Alpha 1:3-2:1')['last_verse_id']) == (3, 4)          # across chapters
assert (P('Alpha 1.2')['first_verse_id'], P('Alpha 1,2')['first_verse_id']) == (2, 2)                  # separators
assert (P('Alpha 1–2')['kind'], P('Alpha 1–2')['first_verse_id'], P('Alpha 1–2')['last_verse_id']) == ('chapters', 1, 5)
assert P('Alpha 1–3')['status'] == 'out_of_range'
assert (P('Beta Book')['kind'], P('Beta Book')['first_verse_id'], P('Beta Book')['last_verse_id']) == ('book', 6, 8)
assert (P('Beta Book 1')['kind'], P('Beta Book 1')['first_verse_id'], P('Beta Book 1')['last_verse_id']) == ('chapter', 6, 8)
assert P('Alpha Book 3')['status'] == 'out_of_range' and 'chapters' in P('Alpha Book 3')['reason']
assert P('Alpha Book 1:9')['status'] == 'out_of_range'
assert P('Alpha Book 2:2-1')['status'] == 'out_of_range'
assert P('Alpha Book 1:1-2:9')['status'] == 'out_of_range'
assert P('nonsense 3:16')['status'] == 'not_a_reference'
assert P('what is faith')['status'] == 'not_a_reference'
assert P('')['status'] == 'not_a_reference'
assert P('Alpha Book')['book_id'] == 1 and P('Alpha Book')['matched_language'] == 'english'

# tier order and ambiguity (stub catalog with colliding aliases across non-active languages)
stub = rp.Catalog.__new__(rp.Catalog)
stub.languages = ['english', 'spanish', 'greek']
stub.books = {1: {'name': 'A', 'first': 1, 'last': 3, 'chapters': 1}, 2: {'name': 'B', 'first': 4, 'last': 6, 'chapters': 1},
              3: {'name': 'C', 'first': 7, 'last': 9, 'chapters': 1}}
stub.chapters = {(1, 1): (1, 3), (2, 1): (4, 6), (3, 1): (7, 9)}
stub.aliases = {'english': {'x': 1, 'only en': 3}, 'spanish': {'x': 2, 'sp': 2}, 'greek': {'x': 3, 'sp': 3}}
assert rp.parse(stub, 'x 1:1', 'spanish')['book_id'] == 2          # active language wins
assert rp.parse(stub, 'x 1:1', 'greek')['book_id'] == 3
assert rp.parse(stub, 'only en 1:2', 'spanish')['book_id'] == 3    # then English
amb = rp.parse(stub, 'sp 1:1', 'english')                          # English has no 'sp'; spanish and greek disagree
assert amb['status'] == 'ambiguous' and [c['book_id'] for c in amb['candidates']] == [2, 3], amb

# ---- configuration identity ------------------------------------------------------------------------------------------
base = {'base_model_revision': 'r', 'tokenizer_sha256': 't', 'encoder': {'graph_sha256': 'g'}, 'head_sha256': 'h',
        'index': {'dense_sha256': 'd'}, 'fusion': ci.FUSION, 'candidate_language': 'english', 'filter_sha256': None}
cid = ci.configuration_id(base)
assert cid == ci.configuration_id(dict(reversed(list(base.items()))))                       # key order independent
assert cid != ci.configuration_id({**base, 'encoder': {'graph_sha256': 'g2'}})              # encoder change
assert cid != ci.configuration_id({**base, 'fusion': {**ci.FUSION, 'lane_k': 100}})         # fusion change
assert cid != ci.configuration_id(base, mode='phrase')                                      # mode change
assert ci.filter_hash([3, 1, 2, 2]) == ci.filter_hash([1, 2, 3]) and ci.filter_hash(None) is None
assert ci.filter_hash([1, 2]) != ci.filter_hash([1, 2, 3])
k = ci.cache_key('What is faith?', cid)
assert k == ci.cache_key('What is faith?', cid) and k != ci.cache_key('what is faith?', cid)     # exact query
assert k != ci.cache_key('What is faith?', cid, top_k=10) and k != ci.cache_key('What is faith?', cid, filter_sha='f')
print('fixture capabilities: OK')

# ---- real data -------------------------------------------------------------------------------------------------------
if not (RELEASE.exists() and CATALOG.exists() and PHRASE_DB.exists()):
    print('real-data section skipped (release not built)')
    sys.exit(0)

snapshot = {}
real = rp.Catalog(CATALOG)
content = sqlite3.connect(f'file:{RELEASE.as_posix()}?mode=ro', uri=True)

# 1) every reference string in every served language round-trips to its own verse id
cat_db = sqlite3.connect(f'file:{CATALOG.as_posix()}?mode=ro', uri=True)
chapters = cat_db.execute('SELECT book_id, chapter, first_verse_id, last_verse_id FROM chapters ORDER BY first_verse_id').fetchall()
import bisect  # noqa: E402
firsts = [c[2] for c in chapters]
fails = {}
for lang in real.languages:
    names = dict(cat_db.execute(f'SELECT book_id, name FROM book_names_{lang}'))
    bad = []
    for (vid,) in content.execute(f'SELECT verse_id FROM text_{lang} ORDER BY verse_id'):
        bid, ch, lo, hi = chapters[bisect.bisect_right(firsts, vid) - 1]
        ref = f'{names[bid]} {ch}:{vid - lo + 1}'
        r = rp.parse(real, ref, lang)
        if not (r['status'] == 'ok' and r['kind'] == 'verse' and r['first_verse_id'] == vid):
            bad.append((vid, ref, r.get('status')))
    fails[lang] = bad
    print(f'  reference round trip {lang}: {41995 - len(bad)}/41995', bad[:3] if bad else '')
assert all(not b for b in fails.values()), {k: v[:5] for k, v in fails.items() if v}

# 2) known references
RP = lambda t, lang='english': rp.parse(real, t, lang)  # noqa: E731
assert RP('John 3:16')['first_verse_id'] == 26137
assert RP('D&C 64:7')['first_verse_id'] == 39194
assert RP('Doctrine and Covenants 64:7')['first_verse_id'] == 39194
assert RP('Psalm 23')['kind'] == 'chapter' and RP('Psalm 23')['book'] == 'Psalms'
assert RP('Song of Solomon 2:1')['book'] == 'Song of Songs'
assert RP('Salmos 23:1', 'spanish')['book'] == 'Psalms'
assert RP('Juan 3:16', 'tagalog')['first_verse_id'] == RP('John 3:16')['first_verse_id']
assert RP('John 3:16', 'spanish')['matched_language'] == 'english'          # falls back to English aliases
assert RP('John 22')['status'] == 'out_of_range'
assert RP('Jn 3:16-18')['last_verse_id'] - RP('Jn 3:16-18')['first_verse_id'] == 2
assert RP('Alma 32-34')['kind'] == 'chapters'
assert RP('1 Nephi 3:7')['kind'] == 'verse' and RP('1 Nephi 3:7')['book'] == '1 Nephi'
assert RP('how do I forgive')['status'] == 'not_a_reference'

# 3) phrase search on the real KJV text
rdb = sqlite3.connect(f'file:{PHRASE_DB.as_posix()}?mode=ro', uri=True)
RS = lambda p, lang='english', **k: ps.search(rdb, p, lang, **k)  # noqa: E731
shepherd = RS('The Lord is my shepherd')
assert RP('Psalm 23:1')['first_verse_id'] in shepherd['verse_ids']
beginning = RS('in the beginning')
assert 1 in beginning['verse_ids'] and beginning['total'] >= 3
assert RS('Lord  IS my   SHEPHERD')['verse_ids'] == shepherd['verse_ids']      # case and spacing
assert RS('shepherd my is Lord')['total'] == 0

# 4) similar verses
if sv.BUNDLE.exists():
    sim = sv.SimilarVerses()
    jn = RP('John 3:16')['first_verse_id']
    top = sim.similar(jn, 10)
    assert len(top) == 10 and jn not in [t['verse_id'] for t in top]
    sc = [t['score'] for t in top]
    assert sc == sorted(sc, reverse=True)
    assert top == sim.similar(jn, 10)                                           # deterministic
    only = {RP('John 3:1')['first_verse_id'], RP('Romans 5:8')['first_verse_id'], jn}
    assert {t['verse_id'] for t in sim.similar(jn, 10, allowed_verse_ids=only)} <= only - {jn}
    snapshot['similar'] = {str(v): [t['verse_id'] for t in sim.similar(v, 10)] for v in (1, jn, 39194)}

snapshot['phrase'] = {p: RS(p, top_k=20) for p in ('in the beginning', 'the Lord is my shepherd', 'faith hope charity', 'love one another')}
snapshot['phrase_es'] = {p: RS(p, 'spanish', top_k=20) for p in ('el Señor es mi pastor', 'en el principio')}
snapshot['reference'] = {f'{lang}|{t}': RP(t, lang) for lang, t in (
    ('english', 'John 3:16'), ('english', 'Jn 3:16-18'), ('english', 'D&C 64:7'), ('english', 'Psalm 23'),
    ('english', 'Song of Solomon 2:1'), ('english', 'Alma 32-34'), ('english', 'John 22'), ('english', 'forgiveness'),
    ('spanish', 'Salmos 23:1'), ('spanish', 'Juan 3:16'), ('tagalog', 'Juan 3:16'), ('greek', 'Γένεσις 1:1'))}
snapshot['catalog_contract'] = real.meta['verse_order_sha256']

if UPDATE or not GOLDEN.exists():
    GOLDEN.write_text(json.dumps(snapshot, indent=1, ensure_ascii=False, sort_keys=True), 'utf-8')
    print('golden written:', GOLDEN)
else:
    expected = json.loads(GOLDEN.read_text('utf-8'))
    got = json.loads(json.dumps(snapshot, ensure_ascii=False, sort_keys=True))
    for k in expected:
        assert expected[k] == got[k], f'golden mismatch in section {k}'
    print('golden matches')
print('engine capabilities: OK')
