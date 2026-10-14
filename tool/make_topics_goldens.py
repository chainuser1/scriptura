"""Golden cases for the topic lane: the Python reference's fused similar-verses lists, replayed by the Rust tests.

  .venv\\Scripts\\python.exe -I tool/make_topics_goldens.py
"""
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tool'))
from similar_verses import SimilarVerses, TOPICS_DB  # noqa: E402


def main():
    sv = SimilarVerses(ROOT / 'generated-artifacts' / 'engine-pack' / 'retrieval')
    c = sqlite3.connect(f'file:{TOPICS_DB.as_posix()}?mode=ro', uri=True)
    with_topics = sorted({r[0] for r in c.execute('SELECT DISTINCT verse_id FROM posting')})
    without = [int(v) for v in sv.verse_ids if int(v) not in set(with_topics)][:2000:400]
    pick = [with_topics[i] for i in np.linspace(0, len(with_topics) - 1, 14).astype(int)]
    cases = []
    for v in pick + without:
        cases.append({'verse_id': int(v), 'top_k': 10, 'filter': None,
                      'ids': [h['verse_id'] for h in sv.similar_with_topics(v, 10)],
                      'genome_only': [h['verse_id'] for h in sv.similar(v, 10)]})
    flt = [[26100, 26300]]
    allowed = [int(x) for x in sv.verse_ids if 26100 <= x <= 26300]
    cases.append({'verse_id': 26137, 'top_k': 10, 'filter': flt, 'ids': [h['verse_id'] for h in sv.similar_with_topics(26137, 10, allowed)],
                  'genome_only': [h['verse_id'] for h in sv.similar(26137, 10, allowed)]})
    out = ROOT / 'test' / 'golden' / 'topics_similar.json'
    out.write_text(json.dumps({'weight': float(sv._topic_meta['weight']), 'cases': cases}, indent=1), 'utf-8')
    changed = sum(1 for c_ in cases if c_['ids'] != c_['genome_only'])
    print(f'{len(cases)} cases ({changed} differ from genome-only) -> {out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
