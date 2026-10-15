"""Moods, starters and labels are consistent with the 568-gene schema."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
genes = [l.strip() for l in (ROOT / 'generated-artifacts/engine-pack/retrieval/gene_ids.txt').read_text('utf-8').splitlines() if l.strip()]
gene_set = set(genes)
moods = json.loads((ROOT / 'assets/trail_moods.json').read_text('utf-8'))['moods']
starters = json.loads((ROOT / 'assets/trail_starters.json').read_text('utf-8'))['starters']
labels = json.loads((ROOT / 'assets/genome_labels.json').read_text('utf-8'))

assert len(moods) == 10, len(moods)
ids = [m['id'] for m in moods]
assert len(set(ids)) == len(ids), 'duplicate mood ids'
for m in moods:
    assert m['label'] and m['blurb'], m['id']
    assert 3 <= len(m['genes']) <= 8, (m['id'], len(m['genes']))
    for g in m['genes']:
        assert g['id'] in gene_set, f"unknown gene {g['id']} in mood {m['id']}"
        assert 0 < g['weight'] <= 2, g
assert len(starters) == 8, len(starters)
for s in starters:
    assert s['mood'] in ids, s
    assert s['question'].strip().endswith('?'), s
    assert s['title'] and s['blurb'] and s['icon'], s
assert set(labels['genes']) == gene_set, 'every gene needs a label'
assert len(labels['families']) == 23 and set(labels['families']) == set('ABCDEFGHIJKLMNOPQRSTUVW')
assert all(v.strip() for v in labels['genes'].values())
print('trail data ok: 10 moods, 8 starters, 568 labels')
