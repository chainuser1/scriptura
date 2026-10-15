"""Checks for the volume balance reference (tool/volume_balance.py).

  .venv\\Scripts\\python.exe -I test/volume_balance_check.py
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'tool'))
from volume_balance import balance  # noqa: E402

rng = np.random.default_rng(1)
vol = np.repeat([0, 1, 2], [300, 200, 100])
s = rng.random(600)
s[vol == 0] += 0.5                                     # volume 0 scores high everywhere
allr = np.ones(600, bool)

assert np.array_equal(balance(s, vol, allr, 0.0), s), 'strength 0 must change nothing'
assert np.array_equal(balance(s, vol, vol == 1, 0.5), s), 'one volume in scope must change nothing'

b = balance(s, vol, allr, 1.0, top_frac=0.05, min_top=5)     # full strength: the baselines are equalised
assert (vol[np.argsort(-b)[:30]] == 0).mean() < 0.8 <= (vol[np.argsort(-s)[:30]] == 0).mean(), 'the inflated volume must lose share'
assert np.array_equal(np.argsort(-s[vol == 0]), np.argsort(-b[vol == 0])), 'order inside a volume must be kept'

small = allr.copy()
small[vol == 2] = False
small[np.flatnonzero(vol == 2)[:5]] = True             # volume 2 touched by only five verses
d = s - balance(s, vol, small, 0.5, top_frac=0.05, min_top=5)
assert abs(d[np.flatnonzero(vol == 2)[0]] - np.mean([d[0], d[300]])) < 1e-12, 'a small part takes the mean offset'

# a part whose top fraction is fewer than MIN_TOP scores is not judged by its own best match (review finding 3)
mid = allr.copy(); mid[vol == 2] = False; mid[np.flatnonzero(vol == 2)[:80]] = True     # 80 rows: ceil(0.005*80) = 1 < 5
d = s - balance(s, vol, mid, 0.5, top_frac=0.005, min_top=5)
assert abs(d[np.flatnonzero(vol == 2)[0]] - np.mean([d[0], d[300]])) < 1e-12, 'a part with too few top scores takes the mean offset'

# sparse lanes: zero (no evidence) stays zero, and evidence never drops below no evidence (review finding 2)
t = np.where(rng.random(600) < 0.2, rng.random(600), 0.0)
t[vol == 0] *= 3
bt = balance(t, vol, allr, 0.75, top_frac=0.05, min_top=5, positive_only=True)
assert np.array_equal(bt[t == 0], t[t == 0]), 'rows without evidence must stay 0'
assert (bt[t > 0] >= 0).all(), 'a row with evidence must never fall below a row without'

print('volume balance check: ok')
