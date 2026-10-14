"""Fusion profile registry sanity: weights sum to 1, default/fallback exist, fallback needs no ColBERT."""
import json
from pathlib import Path

d = json.loads((Path(__file__).resolve().parent.parent / 'tool' / 'data' / 'fusion_profiles.json').read_text('utf-8'))
P = d['profiles']
for k, p in P.items():
    assert abs(sum(p[s] for s in d['signals']) - 1.0) < 1e-9, k
assert d['default'] == 'compass' and P[d['default']]['thread'] > 0
assert P[d['fallback_without_thread']]['thread'] == 0
assert P['chorus']['root'] == 0.30  # Experiment D reference unchanged
print('fusion profiles ok:', ', '.join(P))
