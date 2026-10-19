"""Frozen native inference inputs for docs/ANSWER_FOCUS_NEMOTRON_HELDOUT_PROTOCOL.md: Compass retrieval + native
BGE int8 scoring for the 24 fresh held-out questions, same procedure as answer_focus_calibration_infer.py's
test/calibration splits (full 200-candidate pool, no reuse of any prior grading).

  python -I tool/answer_focus_nemotron_heldout_infer.py run
No fitting, automatic grading, application mutations or downloads.
"""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tool'))
import answer_focus_wide_pool as wide

OUT = ROOT / 'local-benchmarks/answer-focus-nemotron-heldout'
QUESTIONS = ROOT / 'tool/answer_focus_nemotron_heldout_questions.json'


def questions():
    rows = wide.read(QUESTIONS)['queries']
    assert len({r['id'] for r in rows}) == len(rows) == 26
    assert len({r['query'].strip().casefold() for r in rows}) == len(rows), 'Duplicate questions'
    assert sum(r['kind'] == 'answerable' for r in rows) == 22
    assert sum(r['kind'] == 'absent' for r in rows) == 4
    return rows


def identity():
    paths = [Path(__file__), QUESTIONS, ROOT / 'docs/ANSWER_FOCUS_NEMOTRON_HELDOUT_PROTOCOL.md',
             ROOT / 'tool/answer_focus_wide_pool.py', ROOT / 'tool/reranker_stage2.py',
             ROOT / 'engine/target/release/scripture_engine.dll',
             wide.GEN / 'answer-focus-int8-v1/model.onnx', wide.GEN / 'answer-focus-int8-v1/tokenizer.json',
             wide.GEN / 'engine-pack/manifest.json', wide.GEN / 'colbert-pack-v1/manifest.json',
             wide.GEN / 'release/content.db', wide.GEN / 'release/catalog.db']
    return {'sha256': {str(p.relative_to(ROOT)): wide.digest(p) for p in paths},
            'candidate_depth': 200, 'backend': 'native_cpu_int8_single_pair'}


def infer():
    ident = identity()
    if (OUT / 'identity.json').exists():
        assert wide.read(OUT / 'identity.json') == ident, 'Input drift; do not mix runs'
    wide.write(OUT / 'identity.json', ident)
    qs = questions()
    corpus = wide.Corpus()
    native = wide.Native()
    try:
        for i, q in enumerate(qs):
            path = OUT / 'queries' / (q['id'] + '.json')
            if path.exists() and wide.read(path)['complete']:
                print(f"cached {i+1}/{len(qs)} {q['id']}", flush=True)
                continue
            r = native.request(op='semantic', query=q['query'], language=q['language'], profile='compass', top_k=200)
            ids = [h['verse_id'] for h in r['hits']]
            assert len(ids) == 200 and len(set(ids)) == 200
            texts = [corpus.text(v, q['language']) for v in ids]
            text_hash = hashlib.sha256(json.dumps(texts, ensure_ascii=False).encode()).hexdigest()
            labels = [None] * 200
            if path.exists():
                row = wide.read(path)
                assert row['candidates'] == ids and row['text_sha256'] == text_hash
            else:
                row = {**q, 'candidates': ids, 'compass': [h['score'] for h in r['hits']],
                       'reranker': [None] * 200, 'grades': labels, 'complete': False,
                       'text_sha256': text_hash, 'batches': []}
            remaining = [j for j in range(200) if row['reranker'][j] is None]
            for start in range(0, len(remaining), 10):
                js = remaining[start:start + 10]
                t = time.perf_counter()
                got = native.request(op='focus', query=q['query'], texts=[texts[j] for j in js])
                assert got['device'] == 'cpu' and len(got['scores']) == len(js)
                assert np.isfinite(got['scores']).all()
                for j, score in zip(js, got['scores']):
                    row['reranker'][j] = score
                row['batches'].append({'indices': js, 'seconds': time.perf_counter() - t})
                wide.write(path, row)
            row['complete'] = all(x is not None for x in row['reranker'])
            assert row['complete']
            wide.write(path, row)
            print(f"{i+1}/{len(qs)} {q['id']}: 200 scored", flush=True)
    finally:
        native.close()


def rows():
    qs = questions()
    result = [wide.read(OUT / 'queries' / (q['id'] + '.json')) for q in qs]
    assert all(r['complete'] for r in result), 'Inference incomplete'
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=('run',))
    p.parse_args()
    infer()
