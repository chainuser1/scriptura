"""Captures keyword concentration for the candidates already lane-scored by answer_focus_richer_inputs_infer.py, per
docs/ANSWER_FOCUS_KEYWORD_CONCENTRATION_PROTOCOL.md. Re-requests `semantic` with `lanes: true, concentration: true`
for the identical query/profile/top_k, and verifies the returned candidate IDs match before trusting the alignment.

  python -I tool/answer_focus_concentration_infer.py train|calibration|test
"""
import argparse
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tool'))
import answer_focus_calibration_infer as cal  # noqa: E402
import answer_focus_richer_inputs_infer as rich  # noqa: E402
import answer_focus_wide_pool as wide  # noqa: E402

OUT = ROOT / 'local-benchmarks/answer-focus-concentration'


def identity():
    paths = [Path(__file__), ROOT / 'docs/ANSWER_FOCUS_KEYWORD_CONCENTRATION_PROTOCOL.md',
             ROOT / 'engine/target/release/scripture_engine.dll', rich.OUT / 'identity.json']
    return {'sha256': {str(p.relative_to(ROOT)): wide.digest(p) for p in paths}}


def run(split):
    ident = identity()
    if (OUT / 'identity.json').exists():
        assert wide.read(OUT / 'identity.json') == ident, 'Input drift; do not mix runs'
    wide.write(OUT / 'identity.json', ident)
    native = wide.Native()
    try:
        rows = rich.rows(split)
        for i, r in enumerate(rows):
            path = OUT / 'queries' / split / (r['id'] + '.json')
            if path.exists() and wide.read(path)['complete']:
                print(f'cached {split} {i + 1}/{len(rows)} {r["id"]}', flush=True)
                continue
            got = native.request(op='semantic', query=r['query'], language=r['language'], profile='compass',
                                 top_k=len(r['candidates']), lanes=True, concentration=True)
            got_ids = [h['verse_id'] for h in got['hits']]
            assert got_ids == r['candidates'], (r['id'], 'candidate order drifted since the lane-capture run')
            concentration = [h['lanes']['concentration'] for h in got['hits']]
            assert np.isfinite(concentration).all() and all(0.0 <= c <= 1.0 for c in concentration), r['id']
            wide.write(path, {'id': r['id'], 'query': r['query'], 'language': r['language'], 'split': split,
                              'kind': r['kind'], 'candidates': r['candidates'], 'concentration': concentration,
                              'complete': True})
            print(f'{split} {i + 1}/{len(rows)} {r["id"]}: {len(concentration)} concentration values captured', flush=True)
    finally:
        native.close()


def rows(split):
    rich_rows = {r['id']: r for r in rich.rows(split)}
    out = []
    for p in sorted((OUT / 'queries' / split).glob('*.json')):
        conc_row = wide.read(p)
        assert conc_row['complete']
        r = rich_rows[conc_row['id']]
        assert conc_row['candidates'] == r['candidates'], (conc_row['id'], 'candidate list mismatch between runs')
        out.append({**r, 'concentration': conc_row['concentration']})
    assert len(out) == len(rich_rows), f'{split}: expected {len(rich_rows)} rows, have {len(out)}'
    return out


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('split', choices=('train', 'calibration', 'test'))
    run(p.parse_args().split)
