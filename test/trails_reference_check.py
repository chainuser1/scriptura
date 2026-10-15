"""Properties of the Trails reference (the behaviour the Rust port must reproduce)."""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tool'))
from trails import Trails  # noqa: E402

RET = ROOT / 'generated-artifacts' / 'engine-pack' / 'retrieval'
TOPICS = ROOT / 'generated-artifacts' / 'topics-pack-v1' / 'topics.db'
T = Trails(RET, TOPICS if TOPICS.exists() else None)
SEEDS = [26137, 1, 9120, 17000, 24000, 30000, 34000, 37000, 39000, 41500]


def batch(seed, events=(), **kw):
    req = {'op': 'trail_next', 'k': 10, 'step': len(events), 'seed': {'verse_id': seed}, 'events': list(events),
           'recent': [e['verse_id'] for e in events][-5:], 'moods': [], 'mood_strength': 0.5, 'focus': 0.5, 'filter': None}
    req.update(kw)
    return T.trail_next(req)


def ids(r):
    return [h['verse_id'] for h in r['hits']]


for s in SEEDS:
    a = batch(s)
    assert len(ids(a)) == 10 and len(set(ids(a))) == 10, 'a batch has 10 distinct verses'
    assert s not in ids(a), 'the seed is never offered'
    assert ids(a) == ids(batch(s)), 'deterministic'

# no repeats across feedback, likes steer, dislikes remove neighbours
seed = 26137
ev, seen = [], {seed}
for round_ in range(6):
    r = batch(seed, ev)
    for h in r['hits'][:3]:
        assert h['verse_id'] not in seen, 'never repeats'
        seen.add(h['verse_id'])
        ev.append({'verse_id': h['verse_id'], 'action': 'shown'})
    first = r['hits'][0]['verse_id']
    ev.append({'verse_id': first, 'action': 'like' if round_ % 2 == 0 else 'dislike'})
V = T.V
disliked = [e['verse_id'] for e in ev if e['action'] == 'dislike']
after = ids(batch(seed, ev))
for d in disliked:
    for u in after:
        assert float(V[T.row_of[u]] @ V[T.row_of[d]]) < 0.90, 'near neighbours of a dislike never appear'

liked = batch(seed, [{'verse_id': 28000, 'action': 'like'}] * 1)
plain = batch(seed)
lv = V[T.row_of[28000]]
mean_cos = lambda r: float(np.mean([V[T.row_of[u]] @ lv for u in ids(r)]))  # noqa: E731
assert mean_cos(liked) > mean_cos(plain), 'a like moves the next batch toward the liked verse'

# moods raise the mean cosine to the mood vector
mood = [{'id': 'D18_emotion_comfort_consolation', 'weight': 1.0}, {'id': 'D05_emotion_tenderness', 'weight': 1.0},
        {'id': 'D08_emotion_peace_stillness', 'weight': 1.0}, {'id': 'D21_emotion_compassion_mercy', 'weight': 1.0}]
m = T.mood_vector([mood])
wins = 0
for s in SEEDS:
    with_m = np.mean([V[T.row_of[u]] @ m for u in ids(batch(s, moods=[mood], mood_strength=1.0))])
    without = np.mean([V[T.row_of[u]] @ m for u in ids(batch(s))])
    wins += with_m > without
assert wins >= 9, f'a mood should help on nearly every seed ({wins}/10)'

# volume is a hard filter
bom = [[31103, 37706]]
for s in SEEDS[:4]:
    assert all(31103 <= u <= 37706 for u in ids(batch(s, filter=bom))), 'filter is hard'

# explain: shares are non-negative and sum to at most 1; ids exist
e = T.explain({'op': 'explain', 'a': 26137, 'b': ids(batch(26137))[0], 'mood_genes': []})
assert 0 <= sum(f['share'] for f in e['families']) <= 1.0 + 1e-9 and all(f['share'] >= 0 for f in e['families'])
# taste: only positive scores, sorted
t = T.taste({'op': 'taste', 'events': [{'verse_id': 26137, 'action': 'like'}, {'verse_id': 9120, 'action': 'dislike'}]})
assert t['families'] == sorted(t['families'], key=lambda f: -f['score']) and all(f['score'] > 0 for f in t['families'])
# small filter widens instead of failing
tiny = batch(26137, filter=[[41361, 41365]], k=10)
assert len(tiny['hits']) <= 5 and tiny['widened'] >= 0
print('trails reference ok')
