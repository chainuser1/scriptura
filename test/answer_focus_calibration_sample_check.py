"""Checks for the rank-band sampling in tool/answer_focus_calibration_run.py (no real inference files needed).
Run: .venv\\Scripts\\python.exe -I test/answer_focus_calibration_sample_check.py
"""
import sys
import copy
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'tool'))
import answer_focus_calibration_run as run  # noqa: E402

# ---- rank_band_sample: 5 per band (1-10, 11-50, 51-200) per question, every item gets a nonzero inclusion probability
candidates = list(range(1, 201))  # a stand-in for 200 ranked verse ids, rank == index+1
sample = run.rank_band_sample(candidates, seed=0)
assert len(sample) == 15, len(sample)  # 3 bands x 5

bands = {'1-10': (1, 10), '11-50': (11, 50), '51-200': (51, 200)}
by_band = {name: [s for s in sample if lo <= s['rank'] <= hi] for name, (lo, hi) in bands.items()}
for name, items in by_band.items():
    assert len(items) == 5, (name, len(items))
    assert len({it['candidate'] for it in items}) == 5, f'{name}: sampled without replacement means no duplicates'
    for it in items:
        assert 0 < it['inclusion_probability'] <= 1
        assert it['band'] == name

# different seeds give different samples (not a fixed/hardcoded selection)
sample2 = run.rank_band_sample(candidates, seed=1)
assert {s['candidate'] for s in sample} != {s['candidate'] for s in sample2}

# same seed is reproducible
sample3 = run.rank_band_sample(candidates, seed=0)
assert [s['candidate'] for s in sample] == [s['candidate'] for s in sample3]

# a short candidate list (fewer than 10) still returns what's available for the 1-10 band, not a crash
short = list(range(1, 4))
sample_short = run.rank_band_sample(short, seed=0)
assert all(s['rank'] <= 3 for s in sample_short)
assert len(sample_short) == len(short)  # every item in a too-short band is included, not sampled 5 from 3

# Deliberately opposite Compass and BGE orders: sampling must use the learned order.
row = {'candidates': list(range(200)), 'compass': list(range(200, 0, -1)),
       'reranker': list(range(200))}
scaler = run.fit.Scaler(0., 1., 0., 1.)
model = run.fit.MonotonicLogistic(0., 1., 0.)
order = run.learned_order(row, scaler, model)
assert order == list(range(199, -1, -1))
learned_sample = run.rank_band_sample([row['candidates'][i] for i in order], seed=0)
assert all(s['candidate'] >= 190 for s in learned_sample if s['band'] == '1-10')
assert np.isclose(sum(1/s['inclusion_probability'] for s in learned_sample), 200)

sheet = [{'item': 'a'}, {'item': 'b'}]
valid = {'reviewer': 'test fixture', 'review_type': 'synthetic', 'items': [
    {'item': 'a', 'grade': 0, 'reason': 'fixture'}, {'item': 'b', 'grade': 2, 'reason': 'fixture'}]}
assert len(run.validate_decisions(sheet, valid)) == 2
for bad_items in (valid['items'][:1], valid['items'] + [valid['items'][0]],
                  valid['items'] + [{'item': 'extra', 'grade': 0, 'reason': 'fixture'}],
                  [{'item': 'a', 'grade': None, 'reason': ''}, valid['items'][1]],
                  [{'item': 'a', 'grade': True, 'reason': 'fixture'}, valid['items'][1]]):
    bad = copy.deepcopy(valid)
    bad['items'] = bad_items
    try:
        run.validate_decisions(sheet, bad)
    except AssertionError:
        pass
    else:
        raise AssertionError('Invalid review accepted')

with tempfile.TemporaryDirectory(dir=run.ROOT / 'local-benchmarks') as tmp:
    path = Path(tmp) / 'packet.json'
    path.write_text('original', encoding='utf-8')
    hashes = run.manifest([path])
    run.verify(hashes)
    path.write_text('changed', encoding='utf-8')
    try:
        run.verify(hashes)
    except AssertionError:
        pass
    else:
        raise AssertionError('Stale packet accepted')

print('answer_focus_calibration_sample: all checks passed')
