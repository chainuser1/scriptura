"""Edge-case checks for the Experiment D reference fusion (docs/SEARCH_SPEC.md). No model needed: a
deterministic stub encoder stands in, the real corpus/head/index assets are loaded.

  .venv\\Scripts\\python.exe -I test/reference_edge_cases.py
"""
import sys
import zlib
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'tool'))
from reference_search import Searcher, zscore  # noqa: E402


class StubEncoder:
    def encode(self, texts, batch=16):
        out = []
        for t in texts:
            rng = np.random.default_rng(zlib.crc32(t.encode()))
            d = rng.normal(size=1024).astype(np.float32)
            d /= np.linalg.norm(d)
            sparse = {int(i): float(w) for i, w in zip(rng.integers(5, 250000, 6), rng.uniform(0.05, 0.5, 6))}
            c = rng.normal(size=(3 + len(t) % 7, 1024)).astype(np.float32)
            c /= np.linalg.norm(c, axis=1, keepdims=True)
            out.append((d, sparse, c))
        return out


def ids(r):
    return [x['verse_id'] for x in r['results']]


def main():
    # zscore edges: n=1 and constant arrays are zeros, non-finite is an error, ddof=1
    assert (zscore([3.0]) == 0).all() and (zscore([2.0, 2.0, 2.0]) == 0).all()
    assert abs(zscore([1.0, 2.0, 3.0]).std(ddof=1) - 1) < 1e-12
    try:
        zscore([1.0, float('nan')])
        raise AssertionError('non-finite must raise')
    except ValueError:
        pass

    s = Searcher(encoder=StubEncoder())
    all_ids = s.verse_ids.tolist()
    q = 'what is faith'

    full = s.search(q)
    assert full['status'] == 'ok' and full['eligible_passages'] == len(all_ids) and len(full['results']) == 20
    assert ids(s.search(q)) == ids(full), 'deterministic'
    assert ids(s.search(q, allowed_verse_ids=all_ids)) == ids(full), 'allow-all == unfiltered'
    assert ids(s.search(q, allowed_verse_ids=all_ids + [10**9])) == ids(full), 'unknown IDs ignored'

    none = s.search(q, allowed_verse_ids=[])
    assert none['status'] == 'no_eligible_passages' and none['results'] == [] and none['candidates'] == 0

    one = s.search(q, allowed_verse_ids=[all_ids[500]])
    assert one['candidates'] == 1 and ids(one) == [all_ids[500]] and one['results'][0]['score'] == 0.0

    few = set(all_ids[1000:1050])
    r = s.search(q, allowed_verse_ids=few)
    assert r['eligible_passages'] == 50 and r['candidates'] <= 50 and set(ids(r)) <= few and len(ids(r)) == 20

    big = set(all_ids[:3000])
    r = s.search(q, allowed_verse_ids=big)
    assert set(ids(r)) <= big and max(r['lane_sizes'].values()) <= 200 and r['candidates'] > 200
    assert [x['score'] for x in r['results']] == sorted((x['score'] for x in r['results']), reverse=True)
    print('reference edge cases: OK')


if __name__ == '__main__':
    main()
