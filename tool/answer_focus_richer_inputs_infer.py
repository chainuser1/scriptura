"""Captures the 4 raw lane scores (dense, sparse, colbert, genome) for the candidates already scored by
answer_focus_calibration_infer.py, per docs/ANSWER_FOCUS_RICHER_INPUTS_PROTOCOL.md. Reuses the existing BGE logits
and labels unchanged; re-requests `semantic` with `lanes: true` for the identical query/profile/top_k that produced
each split's candidate list, and verifies the returned candidate IDs match before trusting the alignment.

  python -I tool/answer_focus_richer_inputs_infer.py train|calibration|test
"""
import argparse
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tool'))
import answer_focus_calibration_infer as cal  # noqa: E402
import answer_focus_wide_pool as wide  # noqa: E402

OUT = ROOT / 'local-benchmarks/answer-focus-richer-inputs'


def identity():
    paths = [Path(__file__), ROOT / 'docs/ANSWER_FOCUS_RICHER_INPUTS_PROTOCOL.md',
             ROOT / 'engine/target/release/scripture_engine.dll', cal.OUT / 'identity.json']
    return {'sha256': {str(p.relative_to(ROOT)): wide.digest(p) for p in paths}}


def run(split):
    ident = identity()
    if (OUT / 'identity.json').exists():
        assert wide.read(OUT / 'identity.json') == ident, 'Input drift; do not mix runs'
    wide.write(OUT / 'identity.json', ident)
    native = wide.Native()
    try:
        rows = cal.rows(split)
        for i, r in enumerate(rows):
            path = OUT / 'queries' / split / (r['id'] + '.json')
            if path.exists() and wide.read(path)['complete']:
                print(f'cached {split} {i + 1}/{len(rows)} {r["id"]}', flush=True)
                continue
            # All three splits were originally scored at top_k=200 (answer_focus_calibration_infer.py); train's
            # candidates are also 200 long, only a historical subset of them is labeled. Request the same depth so
            # the candidate list returned here is the same one already scored, not a different selection.
            got = native.request(op='semantic', query=r['query'], language=r['language'], profile='compass',
                                 top_k=len(r['candidates']), lanes=True)
            got_ids = [h['verse_id'] for h in got['hits']]
            assert got_ids == r['candidates'], (r['id'], 'candidate order drifted since the original inference run')
            lanes = [[h['lanes']['dense'], h['lanes']['sparse'], h['lanes']['colbert'], h['lanes']['genome']]
                    for h in got['hits']]
            assert all(np.isfinite(lanes).all(axis=0).all() for lanes in [np.array(lanes)])
            wide.write(path, {'id': r['id'], 'query': r['query'], 'language': r['language'], 'split': split,
                              'kind': r['kind'], 'candidates': r['candidates'], 'lanes': lanes, 'complete': True})
            print(f'{split} {i + 1}/{len(rows)} {r["id"]}: {len(lanes)} lane rows captured', flush=True)
    finally:
        native.close()


def rows(split):
    cal_rows = {r['id']: r for r in cal.rows(split)}
    out = []
    for p in sorted((OUT / 'queries' / split).glob('*.json')):
        lane_row = wide.read(p)
        assert lane_row['complete']
        c = cal_rows[lane_row['id']]
        assert lane_row['candidates'] == c['candidates'], (lane_row['id'], 'candidate list mismatch between runs')
        out.append({**c, 'lanes': lane_row['lanes']})
    assert len(out) == len(cal_rows), f'{split}: expected {len(cal_rows)} rows, have {len(out)}'
    return out


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('split', choices=('train', 'calibration', 'test'))
    run(p.parse_args().split)
