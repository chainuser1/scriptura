"""Golden requests and the reference's answers, replayed by engine/tests/trails_parity.rs.

  .venv\\Scripts\\python.exe -I tool/make_trail_goldens.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tool'))
from trails import Trails  # noqa: E402

RET = ROOT / 'generated-artifacts' / 'engine-pack' / 'retrieval'
TOPICS = ROOT / 'generated-artifacts' / 'topics-pack-v1' / 'topics.db'
T = Trails(RET, TOPICS if TOPICS.exists() else None)
COMFORT = [{'id': 'D18_emotion_comfort_consolation', 'weight': 1.0}, {'id': 'D05_emotion_tenderness', 'weight': 1.0},
           {'id': 'D08_emotion_peace_stillness', 'weight': 1.0}, {'id': 'D21_emotion_compassion_mercy', 'weight': 1.0}]
PEACE = [{'id': 'D08_emotion_peace_stillness', 'weight': 1.0}, {'id': 'O01_motion_static_meditative', 'weight': 1.0},
         {'id': 'M08_phenom_rest_physical', 'weight': 1.0}]


def base(seed, **kw):
    r = {'op': 'trail_next', 'k': 10, 'step': 0, 'seed': seed, 'extra_seeds': [], 'events': [], 'recent': [], 'moods': [],
         'mood_strength': 0.5, 'focus': 0.5, 'filter': None, 'language': 'english'}
    r.update(kw)
    return r


def ev(*pairs):
    return [{'verse_id': v, 'action': a} for v, a in pairs]


cases = []
for s in (26137, 1, 9120, 17000, 24000, 34000, 39000):
    cases.append(base({'verse_id': s}))
cases += [
    base({'verse_id': 26137}, events=ev((23171, 'shown'), (23171, 'like'), (25049, 'shown'), (25049, 'dislike'), (27000, 'shown'), (27000, 'skip')),
         recent=[23171, 25049, 27000], step=3),
    base({'verse_id': 26137}, moods=[COMFORT], mood_strength=1.0),
    base({'verse_id': 26137}, moods=[COMFORT, PEACE], mood_strength=0.7, focus=0.0),
    base({'verse_id': 26137}, focus=1.0, step=4),
    base({'verse_id': 34000}, filter=[[31103, 37706]]),
    base({'verse_id': 26137}, filter=[[41361, 41365]]),
    base({'verse_id': 26137}, extra_seeds=[{'verse_id': 9120}, {'verses': [26100, 26101, 26102]}]),
    base({'genome': [float(x) for x in T.V[T.row_of[17000]]]}),
]
out = []
for c in cases:
    out.append({'request': c, 'response': T.trail_next(c)})
explains = [{'request': {'op': 'explain', 'a': 26137, 'b': b, 'mood_genes': [g['id'] for g in COMFORT]},
             'response': T.explain({'op': 'explain', 'a': 26137, 'b': b, 'mood_genes': [g['id'] for g in COMFORT]})}
            for b in (37954, 22636, 29405)]
taste = {'request': {'op': 'taste', 'events': ev((26137, 'like'), (9120, 'dislike'), (17000, 'like'))}}
taste['response'] = T.taste(taste['request'])
(ROOT / 'test' / 'golden' / 'trails.json').write_text(json.dumps({'next': out, 'explain': explains, 'taste': taste}), 'utf-8')
print(len(out), 'next cases,', len(explains), 'explain cases ->', ROOT / 'test' / 'golden' / 'trails.json')
