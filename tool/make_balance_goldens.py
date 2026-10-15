"""Golden requests and the reference's answers for volume balance, replayed by engine/tests/engine_e2e.rs.

  .venv\\Scripts\\python.exe -I tool/make_balance_goldens.py
"""
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tool'))
from similar_verses import SimilarVerses, TOPICS_DB  # noqa: E402
from trails import Trails  # noqa: E402
from volume_balance import STRENGTH, volume_ranges  # noqa: E402

OT, NT, BOM, DC, PGP = [(v['first'], v['last']) for v in volume_ranges()]
cat = sqlite3.connect(f'file:{(ROOT / "generated-artifacts/release/catalog.db").as_posix()}?mode=ro', uri=True)


def chapter(book, ch):
    return cat.execute('SELECT c.first_verse_id, c.last_verse_id FROM chapters c JOIN book_names_english b USING(book_id) '
                       'WHERE b.name = ? AND c.chapter = ?', (book, ch)).fetchone()


def book(name):
    return cat.execute('SELECT k.first_verse_id, k.last_verse_id FROM books k JOIN book_names_english b USING(book_id) '
                       'WHERE b.name = ?', (name,)).fetchone()


SCOPES = {
    'canon': None,
    'bible': [OT, NT],
    'ot_bom': [OT, BOM],
    'one_book': [book('Alma')],
    'two_small_parts': [chapter('Malachi', 4), chapter('Matthew', 1)],   # both parts have fewer than MIN_TOP top scores: unchanged
    'big_and_small': [book('Isaiah'), chapter('Matthew', 1)],             # the small part takes the mean offset
}
VERSES = [1, 9120, 17000, 23500, 26137, 30000, 34000, 37000, 39000, 41500]


def allowed_of(flt, ids):
    if flt is None:
        return None
    m = np.zeros(len(ids), dtype=bool)
    for lo, hi in flt:
        m |= (ids >= lo) & (ids <= hi)
    return ids[m]


sv = SimilarVerses()
similar = []
for v in VERSES:
    for name, flt in SCOPES.items():
        req = {'op': 'similar', 'verse_id': v, 'top_k': 10, 'volume_balance': STRENGTH}
        if flt is not None:
            req['filter'] = [list(r) for r in flt]
        similar.append({'scope': name, 'request': req,
                        'response': sv.similar_with_topics(v, 10, allowed_of(flt, sv.verse_ids), TOPICS_DB, volume_balance=STRENGTH)})
    req = {'op': 'similar', 'verse_id': v, 'top_k': 10, 'topics': False, 'volume_balance': STRENGTH}
    similar.append({'scope': 'canon_genome_only', 'request': req, 'response': sv.similar(v, 10, None, volume_balance=STRENGTH)})

tr = Trails(ROOT / 'generated-artifacts' / 'engine-pack' / 'retrieval', topics_db=TOPICS_DB)
trails = []
for v in VERSES[::2]:
    for name in ('canon', 'bible'):
        flt = SCOPES[name]
        req = {'op': 'trail_next', 'k': 10, 'step': 0, 'seed': {'verse_id': v}, 'extra_seeds': [], 'events': [], 'recent': [],
               'moods': [], 'mood_strength': 0.5, 'focus': 0.5, 'filter': [list(r) for r in flt] if flt else None,
               'language': 'english', 'volume_balance': STRENGTH}
        trails.append({'scope': name, 'request': req, 'response': tr.trail_next(req)})

out = ROOT / 'test' / 'golden' / 'volume_balance.json'
out.write_text(json.dumps({'strength': STRENGTH, 'similar': similar, 'trails': trails}), 'utf-8')
print(len(similar), 'similar and', len(trails), 'trail cases ->', out)
