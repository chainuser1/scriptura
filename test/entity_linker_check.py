"""Gated person linking decisions (needs the quarantined legacy verse-tags.db; skipped when absent)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'tool'))
from entity_linker import LEGACY_DB, PeopleIndex  # noqa: E402

CASES = [(c['query'], c['status'], c['first']) for c in json.loads((Path(__file__).resolve().parent / 'golden' / 'entity_link_cases.json').read_text('utf-8'))]

if not LEGACY_DB.exists():
    print('skipped: legacy verse-tags.db not present')
    sys.exit(0)
idx = PeopleIndex()
bad = []
for q, status, eid in CASES:
    r = idx.link(q)
    if r['status'] != status or (eid and r['candidates'][:1] != [eid]):
        bad.append((q, r))
assert not idx.link('Who is Jesus Christ?')['filter'], 'generic people must never filter'
assert not bad, '\n'.join(f'{q!r}: {r}' for q, r in bad)
print(f'entity linker ok: {len(CASES)} cases')

PACK = Path(__file__).resolve().parent.parent / 'generated-artifacts' / 'entities-pack-v1' / 'entities.db'
if PACK.exists():
    places = PeopleIndex(PACK, export=True)
    PCASES = json.loads((Path(__file__).resolve().parent / 'golden' / 'entity_place_cases.json').read_text('utf-8'))
    pbad = [(c['query'], r) for c in PCASES for r in [places.link(c['query'])]
            if r['status'] != c['status'] or (c['first'] and r['candidates'][:1] != [c['first']])]
    assert not pbad, chr(10).join(f'{q!r}: {r}' for q, r in pbad)
    print(f'place linker ok: {len(PCASES)} cases')
